"""White-label por clínica: escolha de tema (admin) + classe no <body> + logo."""
from io import BytesIO

from app import db
from app.models import Clinica

# PNG 1x1 transparente válido (pra testar upload sem depender do Pillow).
_PNG_1x1 = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00'
            b'\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')


def test_aparencia_so_admin(client_recepcao, client_prof):
    assert client_recepcao.get("/configuracoes/aparencia").status_code in (301, 302)
    assert client_prof.get("/configuracoes/aparencia").status_code in (301, 302)


def test_admin_ve_seletor(client_admin):
    r = client_admin.get("/configuracoes/aparencia")
    assert r.status_code == 200
    assert b"tema-indigo" in r.data          # opção do seletor
    assert b"Apar" in r.data


def test_admin_salva_tema(client_admin):
    r = client_admin.post("/configuracoes/aparencia",
                          data={"tema": "violeta"}, follow_redirects=True)
    assert r.status_code == 200
    c = Clinica.query.filter_by(slug="teste").first()
    assert c.tema == "violeta"


def test_salvar_tema_remove_cor_personalizada(client_admin):
    # "Ultima acao vence": salvar um tema limpa a cor personalizada que antes
    # sobrescrevia a primaria (senao o tema "nao aplica").
    c = Clinica.query.filter_by(slug="teste").first()
    c.cor_primaria = "#0ea5a9"
    db.session.commit()
    cid = c.id
    client_admin.post("/configuracoes/aparencia",
                      data={"tema": "ambar"}, follow_redirects=True)
    c = db.session.get(Clinica, cid)
    assert c.tema == "ambar"
    assert c.cor_primaria is None          # cor removida -> tema aplica


def test_tema_invalido_rejeitado(client_admin):
    c = Clinica.query.filter_by(slug="teste").first()
    antes = c.tema
    client_admin.post("/configuracoes/aparencia",
                      data={"tema": "hacker"}, follow_redirects=True)
    assert db.session.get(Clinica, c.id).tema == antes


def test_body_recebe_classe_do_tema(client_admin):
    c = Clinica.query.filter_by(slug="teste").first()
    c.tema = "petroleo"
    db.session.commit()
    r = client_admin.get("/agenda/")
    assert b'class="app tema-petroleo"' in r.data


# ---- Logo (white-label v2a) ----

def test_upload_logo_e_render(client_admin):
    r = client_admin.post("/configuracoes/logo",
                          data={"logo": (BytesIO(_PNG_1x1), "logo.png")},
                          content_type="multipart/form-data",
                          follow_redirects=True)
    assert r.status_code == 200
    c = Clinica.query.filter_by(slug="teste").first()
    assert c.logo_key is not None and c.logo_mime == "image/png"
    # serve a imagem
    img = client_admin.get(f"/configuracoes/logo/{c.id}")
    assert img.status_code == 200
    assert img.headers["Content-Type"].startswith("image/")
    # app shell passa a mostrar a logo (não o wordmark)
    pg = client_admin.get("/agenda/")
    assert b"brand-logo" in pg.data


def test_logo_rejeita_svg(client_admin):
    client_admin.post("/configuracoes/logo",
                      data={"logo": (BytesIO(b"<svg/>"), "x.svg")},
                      content_type="multipart/form-data", follow_redirects=True)
    c = Clinica.query.filter_by(slug="teste").first()
    assert c.logo_key is None              # SVG bloqueado (anti-XSS)


def test_logo_upload_so_admin(client_recepcao):
    r = client_recepcao.post("/configuracoes/logo",
                             data={"logo": (BytesIO(_PNG_1x1), "l.png")},
                             content_type="multipart/form-data")
    assert r.status_code in (301, 302)


def test_logo_servir_isolado_entre_clinicas(client_admin):
    cb = Clinica(nome="Outra Logo", slug="outra-logo")
    db.session.add(cb)
    db.session.commit()
    # admin da clínica "teste" não acessa a rota de logo de outra clínica
    assert client_admin.get(f"/configuracoes/logo/{cb.id}").status_code in (403, 404)


def test_remover_logo(client_admin):
    client_admin.post("/configuracoes/logo",
                      data={"logo": (BytesIO(_PNG_1x1), "logo.png")},
                      content_type="multipart/form-data", follow_redirects=True)
    client_admin.post("/configuracoes/logo/remover", follow_redirects=True)
    c = Clinica.query.filter_by(slug="teste").first()
    assert c.logo_key is None


# ---- Cor de marca livre (white-label v2b) ----

def test_salva_cor_e_serve_tema_css(client_admin):
    r = client_admin.post("/configuracoes/cor",
                          data={"cor": "#8E44AD"}, follow_redirects=True)
    assert r.status_code == 200
    c = Clinica.query.filter_by(slug="teste").first()
    assert c.cor_primaria == "#8e44ad"
    # /tema.css reflete a cor e é servido como text/css
    css = client_admin.get("/configuracoes/tema.css")
    assert css.mimetype == "text/css"
    assert b"#8e44ad" in css.data
    assert b"--brand-primary-rgb: 142, 68, 173" in css.data
    # o <link> do tema.css entra no <head>
    pg = client_admin.get("/agenda/")
    assert b"configuracoes/tema.css" in pg.data or b"tema.css" in pg.data


def test_cor_invalida_rejeitada(client_admin):
    client_admin.post("/configuracoes/cor", data={"cor": "roxo"},
                      follow_redirects=True)
    c = Clinica.query.filter_by(slug="teste").first()
    assert c.cor_primaria is None


def test_remove_cor(client_admin):
    client_admin.post("/configuracoes/cor", data={"cor": "#123456"},
                      follow_redirects=True)
    client_admin.post("/configuracoes/cor/remover", follow_redirects=True)
    c = Clinica.query.filter_by(slug="teste").first()
    assert c.cor_primaria is None
    # sem cor, o tema.css volta vazio
    assert client_admin.get("/configuracoes/tema.css").data.strip() == b""


def test_cor_so_admin(client_recepcao):
    assert client_recepcao.post("/configuracoes/cor",
                                data={"cor": "#000000"}).status_code in (301, 302)


def test_contraste_automatico():
    from app.services.cores import texto_sobre, hex_to_rgb, css_para_cor
    # cor clara -> texto navy; cor escura -> texto off-white
    assert texto_sobre(hex_to_rgb("#FDE68A")) == "#1E293B"   # amarelo claro
    assert texto_sobre(hex_to_rgb("#1A1A2E")) == "#F8FAF8"   # azul escuro
    assert "--brand-verde-claro: #8e44ad" in css_para_cor("#8E44AD")
    assert css_para_cor("xyz") == ""                          # inválida
