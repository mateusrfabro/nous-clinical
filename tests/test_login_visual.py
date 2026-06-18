"""Login redesenhado (entrada imersiva): garante que os elementos do novo
visual continuam presentes e que o fluxo/contrato com o Flask segue intacto."""


def test_login_tem_elementos_do_redesign(client):
    r = client.get("/login")
    assert r.status_code == 200
    d = r.data
    assert b'id="auth-net"' in d                 # canvas da rede de nós
    assert b"auth-net.js" in d                    # JS externo (CSP-safe)
    assert b'data-toggle-senha="senha"' in d      # botão mostrar/ocultar senha
    assert "Entrar na plataforma".encode() in d   # CTA
    assert b'name="email"' in d and b'name="senha"' in d
    assert b"csrf_token" in d                      # form Flask preservado


def test_login_erro_mantem_classe_invalida(client):
    # credenciais erradas -> renderiza com .is-invalid (contrato erro_login)
    r = client.post("/login", data={"email": "x@y.com", "senha": "errada"},
                    follow_redirects=True)
    assert r.status_code == 200
    assert b"is-invalid" in r.data
