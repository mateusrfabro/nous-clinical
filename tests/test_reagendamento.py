"""Reagendamento (editar consulta) + lembrete WhatsApp na agenda."""
from datetime import timezone, timedelta
from zoneinfo import ZoneInfo

from app import db
from app.models import Agendamento

_BR = ZoneInfo("America/Sao_Paulo")


def _utc(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _hora_br(dt):
    return _utc(dt).astimezone(_BR).strftime("%H:%M")


def _ag_br(ag):
    local = _utc(ag.inicio).astimezone(_BR)
    return local.date().isoformat(), local.strftime("%H:%M")


def test_editar_gating(client_prof):
    ag = Agendamento.query.first()
    assert client_prof.get(f"/agenda/{ag.id}/editar").status_code in (301, 302)


def test_reagenda_para_horario_livre(client_recepcao):
    ag = Agendamento.query.first()
    dia, hora = _ag_br(ag)
    novo_h = f"{(int(hora[:2]) + 3) % 24:02d}:00"
    r = client_recepcao.post(f"/agenda/{ag.id}/editar", data={
        "profissional_id": ag.profissional_id, "dia": dia, "hora": novo_h,
    }, follow_redirects=True)
    assert r.status_code == 200
    ag2 = db.session.get(Agendamento, ag.id)
    assert _hora_br(ag2.inicio) == novo_h


def test_reagenda_conflito_bloqueia(client_recepcao):
    ag = Agendamento.query.first()
    dia, hora = _ag_br(ag)
    # cria 2ª consulta às +2h pro mesmo profissional
    outro_ini = ag.inicio + timedelta(hours=2)
    db.session.add(Agendamento(
        paciente_id=ag.paciente_id, profissional_id=ag.profissional_id,
        inicio=outro_ini, fim=outro_ini + timedelta(minutes=30),
        status=Agendamento.STATUS_AGENDADO))
    db.session.commit()
    # tenta mover a 1ª pro horário da 2ª -> conflito
    alvo = _hora_br(_utc(ag.inicio) + timedelta(hours=2))
    r = client_recepcao.post(f"/agenda/{ag.id}/editar", data={
        "profissional_id": ag.profissional_id, "dia": dia, "hora": alvo,
    }, follow_redirects=True)
    assert b"Conflito" in r.data


def test_lembrete_whatsapp_na_agenda(client_recepcao):
    ag = Agendamento.query.first()
    ag.paciente.telefone = "(43) 98888-1234"
    db.session.commit()
    dia, _ = _ag_br(ag)
    h = client_recepcao.get(f"/agenda/?dia={dia}").data
    assert b"Lembrete" in h
    assert b"wa.me/5543988881234" in h
