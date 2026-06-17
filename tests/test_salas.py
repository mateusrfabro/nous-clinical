"""Salas / consultórios (RF-03): cadastro controlado + conflito de sala
(impede duas consultas na mesma sala no mesmo horário)."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app import db
from app.models import Sala, Usuario, Profissional, Paciente, Agendamento
from app.services.passwords import hash_senha

_BR = ZoneInfo("America/Sao_Paulo")


def _amanha():
    return datetime.now(_BR).date() + timedelta(days=1)


def _segundo_profissional():
    u = Usuario(email="p2@test.com", senha_hash=hash_senha("x12345678"),
                nome_responsavel="P2", tipo="profissional")
    db.session.add(u)
    db.session.flush()
    prof = Profissional(usuario_id=u.id, nome="Dr. Dois",
                        especialidade="Clínica Geral")
    db.session.add(prof)
    db.session.flush()
    return prof


# ---------- Cadastro de salas ----------

def test_admin_cadastra_sala(client_admin):
    antes = Sala.query.count()
    client_admin.post("/procedimentos/adicionar", data={
        "tipo": "sala", "nome": "Consultório 1",
    }, follow_redirects=True)
    assert Sala.query.count() == antes + 1
    assert Sala.query.filter_by(nome="Consultório 1").first() is not None


def test_sala_duplicada_rejeitada(client_admin):
    client_admin.post("/procedimentos/adicionar",
                      data={"tipo": "sala", "nome": "Sala X"},
                      follow_redirects=True)
    client_admin.post("/procedimentos/adicionar",
                      data={"tipo": "sala", "nome": "Sala X"},
                      follow_redirects=True)
    assert Sala.query.filter_by(nome="Sala X").count() == 1


def test_sala_toggle(client_admin):
    client_admin.post("/procedimentos/adicionar",
                      data={"tipo": "sala", "nome": "Sala Toggle"},
                      follow_redirects=True)
    s = Sala.query.filter_by(nome="Sala Toggle").first()
    assert s.ativo is True
    client_admin.post(f"/procedimentos/salas/{s.id}/toggle",
                      follow_redirects=True)
    assert db.session.get(Sala, s.id).ativo is False


def test_agendamento_form_mostra_select_de_salas(client_admin):
    db.session.add(Sala(nome="Sala Select"))
    db.session.commit()
    r = client_admin.get("/agenda/novo")
    assert r.status_code == 200
    assert b'name="sala"' in r.data
    assert b"Sala Select" in r.data


# ---------- Conflito de sala (RF-03) ----------

def _ocupa_sala(prof, sala_nome, dia, hora):
    pac = Paciente.query.first()
    ini = datetime.combine(dia, hora, tzinfo=_BR).astimezone(timezone.utc)
    db.session.add(Agendamento(
        paciente_id=pac.id, profissional_id=prof.id, inicio=ini,
        fim=ini + timedelta(minutes=30),
        status=Agendamento.STATUS_AGENDADO, sala=sala_nome))
    db.session.commit()


def test_conflito_sala_bloqueia_mesmo_outro_profissional(client_admin):
    db.session.add(Sala(nome="Sala A"))
    prof1 = Profissional.query.first()
    prof2 = _segundo_profissional()
    db.session.commit()
    dia = _amanha()
    _ocupa_sala(prof1, "Sala A", dia, time(10, 0))   # prof1 ocupa a Sala A

    pac = Paciente.query.first()
    antes = Agendamento.query.count()
    r = client_admin.post("/agenda/novo", data={
        "paciente_id": pac.id, "profissional_id": prof2.id,
        "dia": dia.isoformat(), "hora": "10:00", "duracao_min": "30",
        "sala": "Sala A",          # mesma sala, outro profissional, mesmo horário
    }, follow_redirects=True)
    assert b"Sala ocupada" in r.data
    assert Agendamento.query.count() == antes      # não criou


def test_sala_diferente_nao_conflita(client_admin):
    db.session.add_all([Sala(nome="Sala A"), Sala(nome="Sala B")])
    prof1 = Profissional.query.first()
    prof2 = _segundo_profissional()
    db.session.commit()
    dia = _amanha()
    _ocupa_sala(prof1, "Sala A", dia, time(10, 0))

    pac = Paciente.query.first()
    antes = Agendamento.query.count()
    r = client_admin.post("/agenda/novo", data={
        "paciente_id": pac.id, "profissional_id": prof2.id,
        "dia": dia.isoformat(), "hora": "10:00", "duracao_min": "30",
        "sala": "Sala B",          # sala diferente -> ok
    }, follow_redirects=True)
    assert r.status_code == 200
    assert Agendamento.query.count() == antes + 1


def test_sala_cancelada_nao_conflita(client_admin):
    db.session.add(Sala(nome="Sala A"))
    prof1 = Profissional.query.first()
    prof2 = _segundo_profissional()
    db.session.commit()
    dia = _amanha()
    pac = Paciente.query.first()
    ini = datetime.combine(dia, time(10, 0), tzinfo=_BR).astimezone(timezone.utc)
    db.session.add(Agendamento(
        paciente_id=pac.id, profissional_id=prof1.id, inicio=ini,
        fim=ini + timedelta(minutes=30),
        status=Agendamento.STATUS_CANCELADO, sala="Sala A"))   # cancelada
    db.session.commit()
    antes = Agendamento.query.count()
    client_admin.post("/agenda/novo", data={
        "paciente_id": pac.id, "profissional_id": prof2.id,
        "dia": dia.isoformat(), "hora": "10:00", "duracao_min": "30",
        "sala": "Sala A",
    }, follow_redirects=True)
    assert Agendamento.query.count() == antes + 1      # cancelada não ocupa
