"""Camada de produto multi-clínica: superadmin cria/gerencia clínicas."""
import hashlib

from app import db
from app.models import Usuario, Clinica
from app.services.passwords import hash_senha


def _superadmin_client(app, email="super@test.com"):
    sa = Usuario.query.filter_by(email=email).first()
    if not sa:
        sa = Usuario(email=email, senha_hash=hash_senha("x"),
                     nome_responsavel="Super", tipo="superadmin")
        db.session.add(sa)
        db.session.commit()
    c = app.test_client()
    sid = hashlib.sha512(f"test-{sa.id}".encode()).hexdigest()
    with c.session_transaction() as s:
        s["_user_id"] = str(sa.id)
        s["_fresh"] = True
        s["_id"] = sid
        s["_permanent"] = True
    return c


def test_admin_normal_nao_acessa_clinicas(client_admin):
    assert client_admin.get("/clinicas/").status_code in (301, 302)
    assert client_admin.get("/clinicas/nova").status_code in (301, 302)


def test_superadmin_lista_clinicas(app):
    c = _superadmin_client(app)
    r = c.get("/clinicas/")
    assert r.status_code == 200
    assert b"Cl" in r.data            # tem a tabela/título de clínicas


def test_superadmin_cria_clinica_com_admin(app):
    c = _superadmin_client(app)
    antes = Clinica.query.count()
    r = c.post("/clinicas/nova", data={
        "nome": "Clínica Nova", "slug": "nova",
        "admin_nome": "Admin Novo", "admin_email": "admin@nova.com",
        "senha": "senha1234",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert Clinica.query.count() == antes + 1
    nova = Clinica.query.filter_by(slug="nova").first()
    novo_admin = Usuario.query.filter_by(email="admin@nova.com").first()
    assert nova is not None
    assert novo_admin is not None and novo_admin.tipo == "admin"
    assert novo_admin.clinica_id == nova.id          # admin vinculado à clínica


def test_criar_clinica_email_duplicado(app):
    c = _superadmin_client(app)
    antes = Clinica.query.count()
    r = c.post("/clinicas/nova", data={
        "nome": "Outra", "slug": "outra",
        "admin_nome": "X", "admin_email": "admin@test.com",  # já existe (seed)
        "senha": "senha1234",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "Já existe".encode() in r.data
    assert Clinica.query.count() == antes              # não criou


def test_superadmin_toggle_status(app):
    c = _superadmin_client(app)
    clinica = Clinica.query.first()
    estado = clinica.ativo
    c.post(f"/clinicas/{clinica.id}/toggle", follow_redirects=True)
    assert db.session.get(Clinica, clinica.id).ativo is (not estado)
