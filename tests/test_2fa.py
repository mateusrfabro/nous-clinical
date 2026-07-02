"""2FA por TOTP — serviço (RFC 6238), enrollment e 2ª etapa no login."""
import time

from app import db
from app.models import Usuario
from app.services import totp
from app.services.cripto import cifrar


def _codigo_atual(secret):
    return totp._codigo(secret, int(time.time() // 30))


# ---------------- serviço (unit) ----------------

def test_totp_verifica_codigo_valido_e_rejeita_invalido():
    s = totp.gerar_secret()
    assert totp.verificar(s, _codigo_atual(s))
    assert not totp.verificar(s, "12345")     # tamanho errado
    assert not totp.verificar(s, "abcdef")    # não-dígito
    # fora da janela de tolerância (100 períodos à frente)
    assert not totp.verificar(s, totp._codigo(s, int(time.time() // 30) + 100))


def test_recuperacao_uso_unico():
    codigos = totp.gerar_recuperacao(3)
    blob = totp.serializar_recuperacao(codigos)
    novo = totp.consumir_recuperacao(codigos[0], blob)
    assert novo is not None                                  # consumiu
    assert totp.consumir_recuperacao(codigos[0], novo) is None   # não serve 2x
    assert totp.consumir_recuperacao("nao-existe", blob) is None


# ---------------- enrollment ----------------

def test_enrollment_ativa_2fa(client_admin, app):
    assert client_admin.get("/perfil/2fa").status_code == 200
    with client_admin.session_transaction() as s:
        secret = s["2fa_pending_secret"]
    r = client_admin.post("/perfil/2fa/ativar",
                          data={"codigo": _codigo_atual(secret)},
                          follow_redirects=True)
    assert r.status_code == 200
    u = Usuario.query.filter_by(email="admin@test.com").first()
    assert u.totp_ativado and u.totp_secret and u.totp_recovery


# ---------------- 2ª etapa no login ----------------

def _ativa_2fa_no_admin(secret, recovery=None):
    u = Usuario.query.filter_by(email="admin@test.com").first()
    u.totp_secret = cifrar(secret)
    u.totp_ativado = True
    if recovery is not None:
        u.totp_recovery = totp.serializar_recuperacao(recovery)
    db.session.commit()


def test_login_com_2fa_exige_codigo(app, client):
    secret = totp.gerar_secret()
    _ativa_2fa_no_admin(secret)
    # senha certa NÃO loga direto — redireciona pra 2ª etapa
    r = client.post("/login", data={"email": "admin@test.com", "senha": "testpass"})
    assert r.status_code == 302 and "/login/2fa" in r.headers["Location"]
    # ainda não autenticado: página protegida barra
    assert client.get("/perfil/").status_code in (302, 401)
    # código errado não passa
    r = client.post("/login/2fa", data={"codigo": "000001"}, follow_redirects=True)
    assert "inválido" in r.get_data(as_text=True).lower()
    # código certo completa o login
    client.post("/login/2fa", data={"codigo": _codigo_atual(secret)},
                follow_redirects=True)
    assert client.get("/perfil/").status_code == 200


def test_login_2fa_aceita_codigo_de_recuperacao(app, client):
    secret = totp.gerar_secret()
    codigos = totp.gerar_recuperacao()
    _ativa_2fa_no_admin(secret, recovery=codigos)
    client.post("/login", data={"email": "admin@test.com", "senha": "testpass"})
    client.post("/login/2fa", data={"codigo": codigos[0]}, follow_redirects=True)
    assert client.get("/perfil/").status_code == 200


def test_verificar_contador_casa_periodo_atual():
    s = totp.gerar_secret()
    t = int(time.time() // 30)
    assert totp.verificar_contador(s, totp._codigo(s, t)) == t
    assert totp.verificar_contador(s, "000000") in (None, t)  # só casa se bater
    assert totp.verificar_contador(s, "abc") is None


def test_login_2fa_bloqueia_replay(app, client):
    # Um código de TOTP interceptado NÃO pode ser reapresentado dentro da janela.
    secret = totp.gerar_secret()
    _ativa_2fa_no_admin(secret)
    codigo = _codigo_atual(secret)
    client.post("/login", data={"email": "admin@test.com", "senha": "testpass"})
    client.post("/login/2fa", data={"codigo": codigo}, follow_redirects=True)
    assert client.get("/perfil/").status_code == 200
    # logout e nova tentativa REUSANDO o mesmo código -> replay recusado
    client.post("/logout")
    client.post("/login", data={"email": "admin@test.com", "senha": "testpass"})
    r = client.post("/login/2fa", data={"codigo": codigo}, follow_redirects=True)
    assert "inválido" in r.get_data(as_text=True).lower()
    assert client.get("/perfil/").status_code in (302, 401)   # não logou
