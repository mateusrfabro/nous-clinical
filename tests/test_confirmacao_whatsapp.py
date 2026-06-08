"""Confirmação pública de consulta via link assinado (WhatsApp 1-clique)."""
from app import db
from app.models import Agendamento
from app.services.tokens import gerar_token_confirmacao, ler_token_confirmacao


def test_token_roundtrip(app):
    t = gerar_token_confirmacao(42)
    assert ler_token_confirmacao(t) == 42


def test_token_invalido_retorna_none(app):
    assert ler_token_confirmacao("nao-e-um-token") is None


def test_confirmacao_publica_sem_login(client):
    # Rota é pública: não redireciona pro login.
    ag = Agendamento.query.first()
    token = gerar_token_confirmacao(ag.id)
    r = client.get(f"/agenda/confirmar/{token}")
    assert r.status_code == 200
    assert "Confirmar".encode() in r.data


def test_confirmacao_muda_status(client):
    ag = Agendamento.query.first()
    assert ag.status == Agendamento.STATUS_AGENDADO
    token = gerar_token_confirmacao(ag.id)
    r = client.post(f"/agenda/confirmar/{token}")
    assert r.status_code == 200
    assert "confirmada".encode() in r.data.lower()
    assert db.session.get(Agendamento, ag.id).status == Agendamento.STATUS_CONFIRMADO


def test_confirmacao_token_invalido_400(client):
    r = client.get("/agenda/confirmar/token-falso-123")
    assert r.status_code == 400


def test_confirmacao_consulta_cancelada(client):
    ag = Agendamento.query.first()
    ag.status = Agendamento.STATUS_CANCELADO
    db.session.commit()
    token = gerar_token_confirmacao(ag.id)
    r = client.post(f"/agenda/confirmar/{token}")
    assert r.status_code == 200
    # não confirma uma consulta cancelada
    assert db.session.get(Agendamento, ag.id).status == Agendamento.STATUS_CANCELADO
