"""Agendamento online público (portal do paciente) + correções da auditoria."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import db
from app.models import Profissional, Paciente, Agendamento

_BR = ZoneInfo("America/Sao_Paulo")


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
    }, follow_redirects=True)
    assert Agendamento.query.count() == antes


def test_online_fim_de_semana_sem_slots(client):
    prof = Profissional.query.first()
    r = client.get(f"/agenda/agendar?profissional_id={prof.id}&dia={_proximo_sabado()}")
    assert b"slot-grid" not in r.data


def test_online_telefone_invalido(client):
    prof = Profissional.query.first()
    antes = Agendamento.query.count()
    client.post("/agenda/agendar", data={
        "profissional_id": prof.id, "dia": _proximo_dia_util(), "hora": "08:00",
        "nome": "Tel Curto", "telefone": "123",
    }, follow_redirects=True)
    assert Agendamento.query.count() == antes
