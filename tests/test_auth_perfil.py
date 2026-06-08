"""Fluxos reais de autenticação, perfil e visibilidade por papel.

Complementa test_smoke (que injeta sessão): aqui o login passa pelo FORM real
(/login com email+senha), cobrindo logout, troca de senha, edição de perfil e
o menu lateral por papel (admin / recepcao / profissional).
"""
from app.models import Usuario
from app.services.passwords import check_senha


# ---- Login / logout via formulário ----

def test_login_form_sucesso(client):
    r = client.post("/login", data={"email": "admin@test.com", "senha": "testpass"},
                    follow_redirects=True)
    assert r.status_code == 200
    # Caiu no app shell (sidebar) já autenticado.
    assert b'href="/painel"' in r.data
    assert client.get("/painel").status_code == 200


def test_login_senha_errada(client):
    r = client.post("/login", data={"email": "admin@test.com", "senha": "errada"},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "incorret".encode() in r.data.lower()
    # Não autenticou: /painel redireciona pro login.
    assert client.get("/painel").status_code in (301, 302)


def test_logout(client):
    client.post("/login", data={"email": "recepcao@test.com", "senha": "testpass"})
    assert client.get("/painel").status_code == 200
    r = client.post("/logout")
    assert r.status_code in (301, 302)
    assert client.get("/painel").status_code in (301, 302)


# ---- Visibilidade do menu lateral por papel (bate com o gating das rotas) ----

def test_sidebar_admin_ve_tudo(client_admin):
    h = client_admin.get("/painel").data
    for href in [b'href="/agenda/"', b'href="/pacientes/"',
                 b'href="/financeiro/"', b'href="/profissionais/"']:
        assert href in h


def test_sidebar_recepcao_sem_profissionais(client_recepcao):
    h = client_recepcao.get("/painel").data
    assert b'href="/pacientes/"' in h
    assert b'href="/financeiro/"' in h
    assert b'href="/profissionais/"' not in h


def test_sidebar_profissional_minimo(client_prof):
    h = client_prof.get("/painel").data
    assert b'href="/agenda/"' in h
    assert b'href="/pacientes/"' in h          # médico agora vê seus pacientes
    assert b'href="/financeiro/"' not in h
    assert b'href="/profissionais/"' not in h
    assert b'href="/relatorios/"' not in h     # relatórios = admin


# ---- Gating real das rotas (profissional bloqueado) ----

def test_profissional_bloqueado_em_areas_restritas(client_prof):
    # Pacientes agora é liberado (limitado aos seus); o resto continua bloqueado.
    assert client_prof.get("/pacientes/").status_code == 200
    assert client_prof.get("/financeiro/").status_code in (301, 302)
    assert client_prof.get("/profissionais/").status_code in (301, 302)
    assert client_prof.get("/relatorios/").status_code in (301, 302)


# ---- Perfil ----

def test_perfil_renderiza(client_admin):
    r = client_admin.get("/perfil/")
    assert r.status_code == 200
    assert "perfil".encode() in r.data.lower()


def test_perfil_edita_dados(client_admin):
    r = client_admin.post("/perfil/", data={
        "nome_responsavel": "Admin Editado", "telefone": "(43) 90000-0000",
    }, follow_redirects=True)
    assert r.status_code == 200
    u = Usuario.query.filter_by(email="admin@test.com").first()
    assert u.nome_responsavel == "Admin Editado"
    assert u.telefone == "(43) 90000-0000"


def test_trocar_senha_sucesso(client_prof):
    r = client_prof.post("/perfil/senha", data={
        "senha_atual": "testpass", "senha_nova": "novasenha123",
        "senha_confirma": "novasenha123",
    }, follow_redirects=True)
    assert r.status_code == 200
    u = Usuario.query.filter_by(email="prof@test.com").first()
    ok, _ = check_senha("novasenha123", u.senha_hash)
    assert ok


def test_trocar_senha_atual_errada_nao_altera(client_prof):
    antes = Usuario.query.filter_by(email="prof@test.com").first().senha_hash
    r = client_prof.post("/perfil/senha", data={
        "senha_atual": "ERRADA", "senha_nova": "novasenha123",
        "senha_confirma": "novasenha123",
    }, follow_redirects=True)
    assert r.status_code == 200
    depois = Usuario.query.filter_by(email="prof@test.com").first().senha_hash
    assert antes == depois
