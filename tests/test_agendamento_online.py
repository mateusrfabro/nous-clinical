"""Agendamento online público (portal do paciente)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.models import Profissional, Paciente, Agendamento

_BR = ZoneInfo("America/Sao_Paulo")


def _amanha():
    return (datetime.now(_BR).date() + timedelta(days=1)).isoformat()


def test_portal_publico_sem_login(client):
    r = client.get("/agenda/agendar")
    assert r.status_code == 200
    assert "Agendar consulta".encode() in r.data


def test_portal_mostra_slots(client):
    prof = Profissional.query.first()
    r = client.get(f"/agenda/agendar?profissional_id={prof.id}&dia={_amanha()}")
    assert r.status_code == 200
    assert b"slot-grid" in r.data            # há horários livres amanhã


def test_portal_cria_consulta_e_paciente(client):
    prof = Profissional.query.first()
    antes = Agendamento.query.count()
    r = client.post("/agenda/agendar", data={
        "profissional_id": prof.id, "dia": _amanha(), "hora": "08:00",
        "nome": "Paciente Online", "telefone": "(43) 90000-2222",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "solicitada".encode() in r.data.lower()
    assert Agendamento.query.count() == antes + 1
    assert Paciente.query.filter_by(nome_completo="Paciente Online").first()


def test_portal_rejeita_data_passada(client):
    prof = Profissional.query.first()
    antes = Agendamento.query.count()
    r = client.post("/agenda/agendar", data={
        "profissional_id": prof.id, "dia": "2020-01-01", "hora": "08:00",
        "nome": "X", "telefone": "(43) 90000-3333",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert Agendamento.query.count() == antes    # nada criado
