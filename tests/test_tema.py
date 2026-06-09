"""White-label por clínica: escolha de tema (admin) + classe no <body>."""
from app import db
from app.models import Clinica


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
