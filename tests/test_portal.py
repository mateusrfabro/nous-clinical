"""Portal público por clínica (/c/<slug>): login branded, agendamento escopado,
logo e cor públicos. Fecha o gap multi-tenant do agendamento online."""
from datetime import datetime, timedelta, timezone
from io import BytesIO

from app import db
from app.models import Clinica, Usuario, Profissional, Agendamento
from app.services.passwords import hash_senha

_PNG_1x1 = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00'
            b'\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')


def _amanha():
    return (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()


def _clinica_b_com_prof(slug="b-portal"):
    cb = Clinica(nome="Clínica B Portal", slug=slug)
    db.session.add(cb)
    db.session.flush()
    ub = Usuario(email=f"{slug}@p.com", senha_hash=hash_senha("x"),
                 nome_responsavel="Prof B Portal", tipo="profissional",
                 clinica_id=cb.id)
    db.session.add(ub)
    db.session.flush()
    pb = Profissional(usuario_id=ub.id, nome="Prof B Portal", clinica_id=cb.id)
    db.session.add(pb)
    db.session.commit()
    return cb, pb


# ---- Login com a marca da clínica ----

def test_portal_login_mostra_marca_da_clinica(client):
    r = client.get("/c/teste")
    assert r.status_code == 200
    assert "Clínica Teste".encode() in r.data       # nome no painel de marca
    assert b'tema-' in r.data                         # body tematizado


def test_portal_slug_inexistente_404(client):
    assert client.get("/c/nao-existe").status_code == 404


def test_portal_slug_inativo_404(client):
    c = Clinica.query.filter_by(slug="teste").first()
    c.ativo = False
    db.session.commit()
    assert client.get("/c/teste").status_code == 404


# ---- Agendamento escopado à clínica do slug ----

def test_portal_agendar_lista_so_a_clinica(client):
    _clinica_b_com_prof()
    r = client.get("/c/teste/agendar")
    assert r.status_code == 200
    assert b"Dr. Teste" in r.data                 # profissional da clínica teste
    assert b"Prof B Portal" not in r.data         # NÃO vaza o da clínica B


def test_portal_agendar_rejeita_prof_de_outra_clinica(client):
    cb, pb = _clinica_b_com_prof()
    antes = Agendamento.query.filter_by(profissional_id=pb.id).count()
    client.post("/c/teste/agendar", data={
        "profissional_id": pb.id, "dia": _amanha(), "hora": "09:00",
        "nome": "Fulano Teste", "telefone": "11999990000",
    }, follow_redirects=True)
    # profissional da clínica B não pode ser agendado pelo portal da clínica teste
    assert Agendamento.query.filter_by(profissional_id=pb.id).count() == antes


def test_agendar_generico_multiclinica_redireciona(client):
    # 2 clínicas ativas + sem slug -> não faz pooling, manda pro login.
    _clinica_b_com_prof()
    r = client.get("/agenda/agendar", follow_redirects=False)
    assert r.status_code in (301, 302)


# ---- Logo e cor públicos (brand assets) ----

def test_portal_logo_publico(client_admin, client):
    # admin sobe a logo da clínica teste...
    client_admin.post("/configuracoes/logo",
                      data={"logo": (BytesIO(_PNG_1x1), "logo.png")},
                      content_type="multipart/form-data", follow_redirects=True)
    # ...e ela é servida publicamente no portal (sem login)
    r = client.get("/c/teste/logo")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("image/")


def test_portal_logo_404_sem_logo(client):
    assert client.get("/c/teste/logo").status_code == 404


def test_portal_tema_css_publico(client_admin, client):
    client_admin.post("/configuracoes/cor", data={"cor": "#8E44AD"},
                      follow_redirects=True)
    r = client.get("/c/teste/tema.css")
    assert r.status_code == 200
    assert r.mimetype == "text/css"
    assert b"#8e44ad" in r.data


# ---- Favicon por clínica ----

def test_favicon_portal_publico(client):
    r = client.get("/c/teste/favicon.svg")
    assert r.status_code == 200
    assert r.mimetype == "image/svg+xml"
    assert b"<svg" in r.data and b">C</text>" in r.data   # inicial de "Clínica Teste"


def test_favicon_autenticado(client_admin):
    r = client_admin.get("/configuracoes/favicon.svg")
    assert r.status_code == 200
    assert r.mimetype == "image/svg+xml"


def test_favicon_default_plataforma(client):
    # página pública sem clínica aponta pro favicon padrão estático
    assert b"/static/favicon.svg" in client.get("/login").data


# ---- Slug público + QR ----

def test_admin_define_slug(client_admin):
    client_admin.post("/configuracoes/slug",
                      data={"slug": "Minha Clínica!"}, follow_redirects=True)
    c = Clinica.query.filter_by(nome="Clínica Teste").first()
    assert c.slug and all(ch.isalnum() or ch == "-" for ch in c.slug)
    assert c.slug.startswith("minha")


def test_slug_duplicado_rejeitado(client_admin):
    cb = Clinica(nome="Outra", slug="ocupado")
    db.session.add(cb)
    db.session.commit()
    c = Clinica.query.filter_by(slug="teste").first()
    client_admin.post("/configuracoes/slug",
                      data={"slug": "ocupado"}, follow_redirects=True)
    assert db.session.get(Clinica, c.id).slug == "teste"   # não trocou


def test_qr_agendamento_svg(client_admin):
    r = client_admin.get("/configuracoes/qr-agendamento.svg")
    assert r.status_code == 200
    assert r.mimetype == "image/svg+xml"
    assert b"<svg" in r.data


def test_qr_sem_slug_404(client_admin):
    c = Clinica.query.filter_by(slug="teste").first()
    c.slug = None
    db.session.commit()
    assert client_admin.get("/configuracoes/qr-agendamento.svg").status_code == 404


def test_slug_so_admin(client_recepcao):
    assert client_recepcao.post("/configuracoes/slug",
                                data={"slug": "x"}).status_code in (301, 302)
