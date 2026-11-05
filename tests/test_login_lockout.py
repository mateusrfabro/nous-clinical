"""Lockout por-conta + alerta de login de novo IP (SEG-AUTH custo-zero)."""
from app import db
from app.models import Usuario


def _fail(client, n=1):
    for _ in range(n):
        client.post("/login", data={"email": "admin@test.com", "senha": "errada"})


def test_lockout_apos_5_falhas(app, client):
    _fail(client, 5)
    u = Usuario.query.filter_by(email="admin@test.com").first()
    assert u.bloqueado_ate is not None            # conta travada
    # senha CORRETA agora é recusada enquanto bloqueado
    r = client.post("/login", data={"email": "admin@test.com", "senha": "testpass"},
                    follow_redirects=True)
    assert "bloquead" in r.get_data(as_text=True).lower()


def test_login_ok_zera_contador(app, client):
    _fail(client, 3)
    u = Usuario.query.filter_by(email="admin@test.com").first()
    assert u.tentativas_falhas == 3
    client.post("/login", data={"email": "admin@test.com", "senha": "testpass"})
    db.session.refresh(u)
    assert u.tentativas_falhas == 0 and u.bloqueado_ate is None


def test_alerta_login_de_ip_novo(app, client, monkeypatch):
    chamadas = []
    monkeypatch.setattr("app.routes.auth.enviar_email",
                        lambda *a, **k: chamadas.append(a) or True)
    # 1º login (define o IP; sem alerta pois não havia anterior)
    client.post("/login", data={"email": "admin@test.com", "senha": "testpass"})
    assert chamadas == []
    client.post("/logout")
    # 2º login de um IP diferente -> dispara o alerta
    client.post("/login", data={"email": "admin@test.com", "senha": "testpass"},
                headers={"X-Forwarded-For": "203.0.113.9"})
    assert len(chamadas) == 1
