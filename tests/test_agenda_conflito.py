"""Bloqueio de conflito de horário na agenda (mesmo profissional/intervalo)."""
from datetime import timezone
from zoneinfo import ZoneInfo

from app.models import Paciente, Profissional, Agendamento

_BR = ZoneInfo("America/Sao_Paulo")


def _slot_existente_br():
    ag = Agendamento.query.first()
    ini = ag.inicio
    # SQLite descarta tzinfo: trata o horário guardado como UTC (igual ao app).
    if ini.tzinfo is None:
        ini = ini.replace(tzinfo=timezone.utc)
    local = ini.astimezone(_BR)
    return ag, local.date().isoformat(), local.strftime("%H:%M")


def test_bloqueia_conflito_mesmo_profissional(client_recepcao):
    pac = Paciente.query.first()
    ag, dia, hora = _slot_existente_br()
    prof_id = ag.profissional_id
    antes = Agendamento.query.count()

    r = client_recepcao.post("/agenda/novo", data={
        "paciente_id": pac.id, "profissional_id": prof_id,
        "dia": dia, "hora": hora, "duracao_min": "30",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "Conflito".encode() in r.data
    assert Agendamento.query.count() == antes  # não criou


def test_permite_horario_livre(client_recepcao):
    pac = Paciente.query.first()
    ag, dia, hora = _slot_existente_br()
    h, m = map(int, hora.split(":"))
    livre = f"{(h + 2) % 24:02d}:{m:02d}"  # 2h depois -> sem sobreposição
    antes = Agendamento.query.count()

    r = client_recepcao.post("/agenda/novo", data={
        "paciente_id": pac.id, "profissional_id": ag.profissional_id,
        "dia": dia, "hora": livre, "duracao_min": "30",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert Agendamento.query.count() == antes + 1


def test_cancelada_nao_bloqueia(client_recepcao, app):
    from app import db
    pac = Paciente.query.first()
    ag, dia, hora = _slot_existente_br()
    ag.status = Agendamento.STATUS_CANCELADO
    db.session.commit()
    antes = Agendamento.query.count()

    r = client_recepcao.post("/agenda/novo", data={
        "paciente_id": pac.id, "profissional_id": ag.profissional_id,
        "dia": dia, "hora": hora, "duracao_min": "30",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert Agendamento.query.count() == antes + 1  # criou, pois a outra está cancelada


def test_outro_profissional_nao_conflita(client_recepcao, app):
    from app import db
    from app.services.passwords import hash_senha
    from app.models import Usuario
    pac = Paciente.query.first()
    ag, dia, hora = _slot_existente_br()
    # cria 2º profissional
    u = Usuario(email="prof2@test.com", senha_hash=hash_senha("x"),
                nome_responsavel="Dra. Dois", tipo="profissional")
    db.session.add(u)
    db.session.flush()
    p2 = Profissional(usuario_id=u.id, nome="Dra. Dois", especialidade="Geral")
    db.session.add(p2)
    db.session.commit()
    antes = Agendamento.query.count()

    r = client_recepcao.post("/agenda/novo", data={
        "paciente_id": pac.id, "profissional_id": p2.id,
        "dia": dia, "hora": hora, "duracao_min": "30",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert Agendamento.query.count() == antes + 1  # mesmo horário, outro profissional
