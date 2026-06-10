"""Documentos clínicos em PDF: prescrição (receita) e atestado médico.

Gerados a partir de um Atendimento. DADO SENSÍVEL (LGPD) — gate clínico
(profissional/admin); o profissional só emite documentos da própria agenda.
"""
import io

from flask import Blueprint, redirect, url_for, flash, send_file, abort
from flask_login import login_required, current_user

from app import db
from app.auth_decorators import clinico_required
from app.models import Agendamento, AuditLog
from app.services.audit import audit
from app.services.documentos_pdf import receita_pdf, atestado_pdf

documentos_bp = Blueprint("documentos", __name__, url_prefix="/documentos")


def _pode(atendimento) -> bool:
    """Profissional só emite documentos da própria agenda; admin emite tudo."""
    if current_user.is_admin:
        return True
    return bool(
        current_user.is_profissional and current_user.profissional
        and atendimento
        and atendimento.profissional_id == current_user.profissional.id
    )


def _carrega(agendamento_id):
    ag = db.session.get(Agendamento, agendamento_id)
    if not ag:
        return None, None
    return ag, ag.atendimento


def _enviar(dados: bytes, nome: str):
    return send_file(io.BytesIO(dados), mimetype="application/pdf",
                     as_attachment=False, download_name=nome)


@documentos_bp.route("/receita/<int:agendamento_id>.pdf")
@login_required
@clinico_required
def receita(agendamento_id):
    ag, registro = _carrega(agendamento_id)
    if not ag:
        flash("Agendamento não encontrado.", "error")
        return redirect(url_for("agenda.listar"))
    if not _pode(registro):
        abort(403)
    if not registro or not (registro.prescricao or "").strip():
        flash("Não há prescrição registrada para exportar.", "error")
        return redirect(url_for("agenda.atendimento", agendamento_id=ag.id))
    dados = receita_pdf(registro)
    audit(AuditLog.ACAO_DOCUMENTO_EMITIDO, recurso_tipo="atendimento",
          recurso_id=registro.id, detalhes="receita")
    return _enviar(dados, f"receita_{ag.id}.pdf")


@documentos_bp.route("/atestado/<int:agendamento_id>.pdf")
@login_required
@clinico_required
def atestado(agendamento_id):
    ag, registro = _carrega(agendamento_id)
    if not ag:
        flash("Agendamento não encontrado.", "error")
        return redirect(url_for("agenda.listar"))
    if not _pode(registro):
        abort(403)
    if not registro or not registro.atestado_dias:
        flash("Preencha os dias de afastamento do atestado antes de exportar.",
              "error")
        return redirect(url_for("agenda.atendimento", agendamento_id=ag.id))
    dados = atestado_pdf(registro)
    audit(AuditLog.ACAO_DOCUMENTO_EMITIDO, recurso_tipo="atendimento",
          recurso_id=registro.id, detalhes="atestado")
    return _enviar(dados, f"atestado_{ag.id}.pdf")
