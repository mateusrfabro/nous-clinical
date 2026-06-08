"""Smoke + autorizacao basica do Nous Clinical."""
from app.models import Paciente
from app.services.passwords import check_senha


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.get_json()["status"] == "ok"


def test_index_publico(client):
    assert client.get("/").status_code == 200


def test_login_page(client):
    assert client.get("/login").status_code == 200


def test_dashboard_exige_login(client):
    # Sem login -> redireciona pro login.
    r = client.get("/painel")
    assert r.status_code in (301, 302)
    assert "/login" in r.headers["Location"]


def test_dashboard_logado(client_admin):
    assert client_admin.get("/painel").status_code == 200


def test_agenda_logado(client_prof):
    assert client_prof.get("/agenda/").status_code == 200


def test_pacientes_acesso_recepcao(client_recepcao):
    assert client_recepcao.get("/pacientes/").status_code == 200


def test_pacientes_acesso_profissional(client_prof):
    # Profissional agora ACESSA a tela de pacientes (limitada aos seus).
    r = client_prof.get("/pacientes/", follow_redirects=False)
    assert r.status_code == 200


def test_profissionais_so_admin(client_recepcao):
    r = client_recepcao.get("/profissionais/", follow_redirects=False)
    assert r.status_code in (301, 302)


def test_criar_paciente(client_admin, app):
    r = client_admin.post("/pacientes/novo", data={
        "nome_completo": "Novo Paciente", "telefone": "(43) 90000-0000",
        "cpf": "529.982.247-25", "data_nascimento": "1990-05-10",
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert Paciente.query.filter_by(nome_completo="Novo Paciente").first()


def test_senha_argon2_roundtrip():
    h = __import__("app.services.passwords", fromlist=["hash_senha"]).hash_senha("segredo123")
    ok, _ = check_senha("segredo123", h)
    assert ok
    bad, _ = check_senha("errada", h)
    assert not bad