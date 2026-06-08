"""Motor de lembretes (comando/endpoint agnóstico) — idempotência e envio."""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app import db
from app.models import Profissional, Paciente, Agendamento
from app.services.lembretes import enviar_lembretes

_BR = ZoneInfo("America/Sao_Paulo")


def _consulta_amanha(email="paciente@ex.com"):
    prof = db.session.execute(db.select(Profissional)).scalars().first()
    pac = Paciente(nome_completo="Lembrete Teste", telefone="(43) 90000-0000",
                   email=email)
    db.session.add(pac)
    db.session.flush()
    alvo = datetime.now(_BR).date() + timedelta(days=1)
    ini = datetime.combine(alvo, time(10, 0), tzinfo=_BR).astimezone(timezone.utc)
    ag = Agendamento(paciente_id=pac.id, profissional_id=prof.id, inicio=ini,
                     fim=ini + timedelta(minutes=30),
                     status=Agendamento.STATUS_AGENDADO)
    db.session.add(ag)
    db.session.commit()
    return ag, alvo


def test_envia_email_e_marca(app, monkeypatch):
    chamadas = []
    monkeypatch.setattr("app.services.lembretes.smtp_configurado", lambda: True)
    monkeypatch.setattr("app.services.lembretes.enviar_email",
                        lambda *a, **k: chamadas.append(a) or True)
    ag, alvo = _consulta_amanha()
    r = enviar_lembretes(alvo)
    assert r["enviados"] == 1
    assert db.session.get(Agendamento, ag.id).lembrete_enviado_em is not None
    # idempotente: 2ª rodada não reenvia
    r2 = enviar_lembretes(alvo)
    assert r2["total"] == 0
    assert len(chamadas) == 1


def test_sem_canal_marca_para_nao_reprocessar(app):
    # Sem SMTP e/ou sem e-mail -> conta como sem_canal e marca.
    ag, alvo = _consulta_amanha(email=None)
    r = enviar_lembretes(alvo)
    assert r["sem_canal"] == 1
    assert db.session.get(Agendamento, ag.id).lembrete_enviado_em is not None


def test_cancelada_nao_recebe_lembrete(app, monkeypatch):
    monkeypatch.setattr("app.services.lembretes.smtp_configurado", lambda: True)
    monkeypatch.setattr("app.services.lembretes.enviar_email", lambda *a, **k: True)
    ag, alvo = _consulta_amanha()
    ag.status = Agendamento.STATUS_CANCELADO
    db.session.commit()
    r = enviar_lembretes(alvo)
    assert r["total"] == 0


# ---- endpoint /tarefas/lembretes ----

def test_endpoint_404_sem_token(client):
    assert client.post("/tarefas/lembretes").status_code == 404


def test_endpoint_403_token_errado(client, app):
    app.config["TAREFAS_TOKEN"] = "segredo"
    assert client.post("/tarefas/lembretes?key=errado").status_code == 403
    app.config["TAREFAS_TOKEN"] = ""


def test_endpoint_ok_com_token(client, app):
    app.config["TAREFAS_TOKEN"] = "segredo"
    r = client.post("/tarefas/lembretes?key=segredo")
    assert r.status_code == 200
    assert "total" in r.get_json()
    app.config["TAREFAS_TOKEN"] = ""
