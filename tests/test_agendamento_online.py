"""Agendamento online público (portal do paciente) + correções da auditoria."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import db
from app.models import Profissional, Paciente, Agendamento, Clinica

_BR = ZoneInfo("America/Sao_Paulo")
# CPF válido + nascimento agora exigidos no agendamento online (req. do sócio).
CPF_VALIDO = "529.982.247-25"
NASC = "1990-05-10"


def _proximo_dia_util():
    d = datetime.now(_BR).date() + timedelta(days=1)
    while d.weekday() >= 5:        # pula sáb/dom
        d += timedelta(days=1)
    return d.isoformat()


def _proximo_sabado():
    d = datetime.now(_BR).date() + timedelta(days=1)
    while d.weekday() != 5:
        d += timedelta(days=1)
    return d.isoformat()


def test_portal_publico_sem_login(client):
    r = client.get("/agenda/agendar")
    assert r.status_code == 200
    assert "Agendar consulta".encode() in r.data


def test_portal_mostra_slots(client):
    prof = Profissional.query.first()
    r = client.get(f"/agenda/agendar?profissional_id={prof.id}&dia={_proximo_dia_util()}")
    assert r.status_code == 200
    assert b"slot-grid" in r.data


def test_portal_cria_consulta_e_paciente(client):
    prof = Profissional.query.first()
    antes = Agendamento.query.count()
    r = client.post("/agenda/agendar", data={
        "profissional_id": prof.id, "dia": _proximo_dia_util(), "hora": "08:00",
        "nome": "Paciente Online", "telefone": "(43) 90000-2222",
        "cpf": CPF_VALIDO, "data_nascimento": NASC,
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "solicitada".encode() in r.data.lower()
    assert Agendamento.query.count() == antes + 1
    assert Paciente.query.filter_by(nome_completo="Paciente Online").first()


def test_portal_rejeita_data_passada(client):
    prof = Profissional.query.first()
    antes = Agendamento.query.count()
    client.post("/agenda/agendar", data={
        "profissional_id": prof.id, "dia": "2020-01-01", "hora": "08:00",
        "nome": "Nome Valido", "telefone": "(43) 90000-3333",
        "cpf": CPF_VALIDO, "data_nascimento": NASC,
    }, follow_redirects=True)
    assert Agendamento.query.count() == antes


# ---- correções da auditoria ----

def test_online_nao_vaza_nem_sequestra_por_telefone(client):
    pac = Paciente(nome_completo="Maria Vitima Real", telefone="11999990000")
    db.session.add(pac)
    db.session.commit()
    prof = Profissional.query.first()
    r = client.post("/agenda/agendar", data={
        "profissional_id": prof.id, "dia": _proximo_dia_util(), "hora": "08:00",
        "nome": "Pessoa Nova", "telefone": "(11) 99999-0000",
        "cpf": CPF_VALIDO, "data_nascimento": NASC,
    }, follow_redirects=True)
    assert r.status_code == 200
    assert b"Maria Vitima Real" not in r.data          # não ecoa cadastro alheio
    assert Paciente.query.filter_by(nome_completo="Pessoa Nova").count() == 1


def test_online_honeypot_bloqueia(client):
    prof = Profissional.query.first()
    antes = Agendamento.query.count()
    client.post("/agenda/agendar", data={
        "profissional_id": prof.id, "dia": _proximo_dia_util(), "hora": "08:00",
        "nome": "Bot Spam", "telefone": "11988887777", "website": "http://spam",
    }, follow_redirects=True)
    assert Agendamento.query.count() == antes


def test_online_hora_fora_dos_slots(client):
    prof = Profissional.query.first()
    antes = Agendamento.query.count()
    client.post("/agenda/agendar", data={
        "profissional_id": prof.id, "dia": _proximo_dia_util(), "hora": "03:00",
        "nome": "Fora Hora", "telefone": "11955554444",
        "cpf": CPF_VALIDO, "data_nascimento": NASC,
    }, follow_redirects=True)
    assert Agendamento.query.count() == antes


def test_online_fim_de_semana_sem_slots(client):
    prof = Profissional.query.first()
    r = client.get(f"/agenda/agendar?profissional_id={prof.id}&dia={_proximo_sabado()}")
    assert b"slot-grid" not in r.data


def test_online_convenio_forjado_e_descartado(client):
    # Convênio fora da lista controlada da clínica (POST forjado) vira None.
    from app.models import Convenio
    prof = Profissional.query.first()
    db.session.add(Convenio(nome="Unimed", clinica_id=prof.clinica_id))
    db.session.commit()
    client.post("/agenda/agendar", data={
        "profissional_id": prof.id, "dia": _proximo_dia_util(), "hora": "08:00",
        "nome": "Conv Forjado", "telefone": "(43) 90000-8888",
        "cpf": CPF_VALIDO, "data_nascimento": NASC, "convenio": "ConvenioPirata",
    }, follow_redirects=True)
    p = Paciente.query.filter_by(nome_completo="Conv Forjado").first()
    assert p is not None and p.convenio is None      # forjado descartado


def test_online_telefone_invalido(client):
    prof = Profissional.query.first()
    antes = Agendamento.query.count()
    client.post("/agenda/agendar", data={
        "profissional_id": prof.id, "dia": _proximo_dia_util(), "hora": "08:00",
        "nome": "Tel Curto", "telefone": "123",
        "cpf": CPF_VALIDO, "data_nascimento": NASC,
    }, follow_redirects=True)
    assert Agendamento.query.count() == antes


# ---- Gate: agendamento online por clínica (default OFF) ----

def _desliga_online():
    c = Clinica.query.filter_by(slug="teste").first()
    c.agendamento_online_ativo = False
    db.session.commit()
    return c


def test_online_desligado_nao_mostra_slots(client):
    _desliga_online()
    prof = Profissional.query.first()
    # Nem por clinica_id explícito a clínica desligada expõe profissionais/slots.
    r = client.get(f"/agenda/agendar?clinica_id={prof.clinica_id}"
                   f"&profissional_id={prof.id}&dia={_proximo_dia_util()}")
    assert r.status_code == 200
    assert b"slot-grid" not in r.data
    assert b"Nenhuma cl" in r.data           # "Nenhuma clínica disponível..."


def test_online_desligado_rejeita_post(client):
    _desliga_online()
    prof = Profissional.query.first()
    antes = Agendamento.query.count()
    r = client.post("/agenda/agendar", data={
        "clinica_id": prof.clinica_id,
        "profissional_id": prof.id, "dia": _proximo_dia_util(), "hora": "08:00",
        "nome": "Nao Deve Marcar", "telefone": "(43) 90000-1111",
        "cpf": CPF_VALIDO, "data_nascimento": NASC,
    }, follow_redirects=True)
    assert r.status_code == 200
    assert Agendamento.query.count() == antes


def test_admin_liga_desliga_online(client_admin):
    c = _desliga_online()
    client_admin.post("/configuracoes/agendamento-online",
                      data={"ativar": "1"}, follow_redirects=True)
    assert db.session.get(Clinica, c.id).agendamento_online_ativo is True
    client_admin.post("/configuracoes/agendamento-online",
                      data={"ativar": "0"}, follow_redirects=True)
    assert db.session.get(Clinica, c.id).agendamento_online_ativo is False


def test_toggle_online_so_admin(client_recepcao):
    assert client_recepcao.post("/configuracoes/agendamento-online",
                                data={"ativar": "1"}).status_code in (301, 302)
