"""3º lote do sócio — correções/evoluções (homologação).

Cobre: campo Origem obrigatório no cadastro ("Como conheceu a clínica?"),
origem='Site' no agendamento online, e (futuro) os novos relatórios.
"""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.models import Paciente, Profissional

CPF_VALIDO = "529.982.247-25"
_BR = ZoneInfo("America/Sao_Paulo")


def _proximo_dia_util():
    d = datetime.now(_BR).date() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.isoformat()


# ---- Campo Origem (item 5) ----

def test_paciente_exige_origem(client_admin):
    antes = Paciente.query.count()
    client_admin.post("/pacientes/novo", data={
        "nome_completo": "Sem Origem", "cpf": CPF_VALIDO,
        "data_nascimento": "1990-05-10", "telefone": "(43) 90000-0000",
    }, follow_redirects=True)
    assert Paciente.query.count() == antes          # sem origem não cria


def test_paciente_salva_origem(client_admin):
    client_admin.post("/pacientes/novo", data={
        "nome_completo": "Com Origem", "cpf": CPF_VALIDO,
        "data_nascimento": "1990-05-10", "telefone": "(43) 90000-0000",
        "origem": "Instagram",
    }, follow_redirects=True)
    p = Paciente.query.filter_by(nome_completo="Com Origem").first()
    assert p is not None and p.origem == "Instagram"


def test_origem_invalida_rejeitada(client_admin):
    antes = Paciente.query.count()
    client_admin.post("/pacientes/novo", data={
        "nome_completo": "Origem Falsa", "cpf": CPF_VALIDO,
        "data_nascimento": "1990-05-10", "telefone": "(43) 90000-0000",
        "origem": "TikTokPirata",
    }, follow_redirects=True)
    assert Paciente.query.count() == antes          # origem fora da lista não cria


def test_agendamento_online_marca_origem_site(client):
    prof = Profissional.query.first()
    client.post("/agenda/agendar", data={
        "profissional_id": prof.id, "dia": _proximo_dia_util(), "hora": "08:00",
        "nome": "Veio do Site", "telefone": "(43) 90000-2222",
        "cpf": CPF_VALIDO, "data_nascimento": "1990-05-10",
    }, follow_redirects=True)
    p = Paciente.query.filter_by(nome_completo="Veio do Site").first()
    assert p is not None and p.origem == "Site"


def test_form_paciente_mostra_origem(client_admin):
    r = client_admin.get("/pacientes/novo")
    assert r.status_code == 200
    assert "Como conheceu".encode() in r.data
    assert b'name="origem"' in r.data


# ---- Relatório de Auditoria CSV (item 3.7) ----

def test_auditoria_export_csv(client_admin):
    # gera alguma ação auditável primeiro
    client_admin.post("/pacientes/novo", data={
        "nome_completo": "Audit CSV", "cpf": CPF_VALIDO,
        "data_nascimento": "1990-05-10", "telefone": "(43) 90000-0000",
        "origem": "Site",
    }, follow_redirects=True)
    r = client_admin.get("/auditoria/export.csv")
    assert r.status_code == 200
    assert r.mimetype == "text/csv"
    assert "Ação;Módulo".encode("utf-8") in r.data       # cabeçalho
    assert b"paciente" in r.data                          # modulo do log


def test_auditoria_export_so_admin(client_recepcao):
    r = client_recepcao.get("/auditoria/export.csv")
    assert r.status_code in (301, 302)                    # admin_required
