"""Hardening de segurança: timeout de sessão por inatividade, auditoria de
acesso a dado sensível (LGPD) e matriz de permissões (RBAC)."""
from app import db
from app.models import Agendamento, AuditLog
from app.permissions import (
    permissoes_de, FINANCEIRO_VER, PRONTUARIO_VER, RELATORIO_EXPORTAR,
    PROFISSIONAL_GERIR,
)


# ---- Idle timeout de sessão ----

def test_sessao_expira_por_inatividade(client_admin):
    # Marca a última atividade lá em 1970 -> excede o idle (1800s).
    with client_admin.session_transaction() as s:
        s["_ultima_atividade"] = 1.0
    r = client_admin.get("/painel")
    assert r.status_code in (301, 302)
    assert "login" in r.headers.get("Location", "")


def test_sessao_ativa_nao_expira(client_admin):
    # Sem marca antiga, a 1ª request seta a atividade e segue normal.
    r = client_admin.get("/painel")
    assert r.status_code == 200


# ---- Auditoria de acesso a dado sensível (LGPD art. 37) ----

def test_visualizar_prontuario_audita(client_prof):
    ag = Agendamento.query.first()
    client_prof.get(f"/agenda/{ag.id}/atendimento")
    log = db.session.execute(
        db.select(AuditLog).where(
            AuditLog.acao == AuditLog.ACAO_PRONTUARIO_VISUALIZADO)
    ).scalars().first()
    assert log is not None
    assert log.recurso_id == ag.paciente_id


def test_export_relatorio_audita(client_admin):
    client_admin.get("/relatorios/export.csv")
    log = db.session.execute(
        db.select(AuditLog).where(
            AuditLog.acao == AuditLog.ACAO_RELATORIO_EXPORTADO)
    ).scalars().first()
    assert log is not None


# ---- Matriz de permissões (RBAC) ----

def test_permissoes_recepcao():
    perms = permissoes_de("recepcao")
    assert FINANCEIRO_VER in perms
    assert RELATORIO_EXPORTAR not in perms  # recepção não vê mais relatórios
    assert PRONTUARIO_VER not in perms     # recepção não vê prontuário (LGPD)
    assert PROFISSIONAL_GERIR not in perms


def test_permissoes_profissional():
    perms = permissoes_de("profissional")
    assert PRONTUARIO_VER in perms
    assert FINANCEIRO_VER not in perms     # profissional não vê financeiro


def test_admin_tem_todas():
    admin = permissoes_de("admin")
    assert permissoes_de("recepcao") <= admin
    assert permissoes_de("profissional") <= admin


def test_papel_desconhecido_sem_permissao():
    assert permissoes_de("hacker") == set()


def test_global_pode_disponivel_no_template(app):
    from flask import render_template_string
    with app.test_request_context():
        out = render_template_string("{{ pode('financeiro:ver') }}")
        assert out.strip() in ("True", "False")
