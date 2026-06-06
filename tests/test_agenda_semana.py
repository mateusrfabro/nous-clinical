"""Agenda em grade semanal: render, posicionamento por data-* e gating."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app import db
from app.models import Agendamento

_BR = ZoneInfo("America/Sao_Paulo")


def test_semana_profissional_acessa(client_prof):
    assert client_prof.get("/agenda/semana").status_code == 200


def test_semana_renderiza_grade(client_admin):
    r = client_admin.get("/agenda/semana")
    assert r.status_code == 200
    assert b"week-body" in r.data
    assert b"week-col" in r.data


def test_semana_posiciona_evento(client_admin):
    ag = Agendamento.query.first()
    nome = ag.paciente.nome_completo
    hoje = datetime.now(_BR).date()
    ini = datetime.combine(hoje, time(10, 0), tzinfo=_BR).astimezone(timezone.utc)
    ag.inicio = ini
    ag.fim = ini + timedelta(minutes=30)
    db.session.commit()

    r = client_admin.get("/agenda/semana")
    assert r.status_code == 200
    assert b"ag-event" in r.data
    assert nome.encode() in r.data
    # posicionamento via data-* (CSP-safe), não style inline.
    assert b"data-top=" in r.data
    assert b"data-accent=" in r.data
