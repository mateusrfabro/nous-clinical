"""Auditoria — isolamento multi-tenant da trilha (LGPD).

Garante que o admin de uma clínica vê SÓ a trilha dos usuários da própria
clínica: nunca a ação da plataforma (superadmin) nem a de outra clínica. Cobre
o hardening fail-closed + exclusão de superadmin do escopo do tenant.
"""
from app import db
from app.models import AuditLog, Usuario, Clinica
from app.services.passwords import hash_senha


def _audit(usuario_id, detalhes):
    log = AuditLog(usuario_id=usuario_id, acao="login", detalhes=detalhes)
    db.session.add(log)
    db.session.flush()


def test_admin_nao_ve_superadmin_nem_outra_clinica(client_admin, app):
    admin = Usuario.query.filter_by(email="admin@test.com").first()

    # Superadmin com clinica_id setado IGUAL ao do admin (pior caso de drift):
    # mesmo assim NÃO pode aparecer pro tenant.
    sa = Usuario(email="super@test.com", senha_hash=hash_senha("x"),
                 nome_responsavel="Super", telefone="(43) 99999-0000",
                 tipo="superadmin", clinica_id=admin.clinica_id)
    db.session.add(sa)
    db.session.flush()

    # Outra clínica + admin dela.
    c2 = Clinica(nome="Outra Clínica", slug="outra")
    db.session.add(c2)
    db.session.flush()
    a2 = Usuario(email="admin2@test.com", senha_hash=hash_senha("x"),
                 nome_responsavel="Admin 2", telefone="(43) 99999-0000",
                 tipo="admin", clinica_id=c2.id)
    db.session.add(a2)
    db.session.flush()

    _audit(admin.id, "ENTRADA-DA-PROPRIA-CLINICA")
    _audit(sa.id, "ENTRADA-DO-SUPERADMIN")
    _audit(a2.id, "ENTRADA-DE-OUTRA-CLINICA")
    db.session.commit()

    body = client_admin.get("/auditoria/", follow_redirects=True).get_data(as_text=True)
    assert "ENTRADA-DA-PROPRIA-CLINICA" in body           # vê a própria
    assert "ENTRADA-DO-SUPERADMIN" not in body            # NÃO vê a plataforma
    assert "ENTRADA-DE-OUTRA-CLINICA" not in body         # NÃO vê outra clínica
    assert "super@test.com" not in body


def test_export_csv_tambem_escopa(client_admin, app):
    admin = Usuario.query.filter_by(email="admin@test.com").first()
    sa = Usuario(email="super2@test.com", senha_hash=hash_senha("x"),
                 nome_responsavel="Super", telefone="(43) 99999-0000",
                 tipo="superadmin", clinica_id=admin.clinica_id)
    db.session.add(sa)
    db.session.flush()
    _audit(admin.id, "OWN-CSV")
    _audit(sa.id, "SUPER-CSV")
    db.session.commit()

    body = client_admin.get("/auditoria/export.csv").get_data(as_text=True)
    assert "OWN-CSV" in body
    assert "SUPER-CSV" not in body


def test_admin_sem_clinica_fail_closed(client_admin, app):
    """Admin sem clinica_id (não deveria ocorrer) não vaza a trilha inteira."""
    from sqlalchemy import update
    admin = Usuario.query.filter_by(email="admin@test.com").first()
    _audit(admin.id, "MARCADOR-FAILCLOSED")
    # Zera o clinica_id por SQL direto (sem passar pelo before_flush do tenant).
    db.session.execute(update(Usuario).where(Usuario.id == admin.id)
                       .values(clinica_id=None))
    db.session.commit()

    body = client_admin.get("/auditoria").get_data(as_text=True)
    assert "MARCADOR-FAILCLOSED" not in body   # fail-closed: nada, em vez de tudo
