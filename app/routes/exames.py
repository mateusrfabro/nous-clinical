"""Anexos de exame/documento no atendimento. DADO SENSÍVEL (LGPD).

Upload/listagem/download/remoção gated a clínico (profissional/admin). O
profissional só mexe nos exames da própria agenda. Arquivos no storage (fora
de static/); download por esta rota autenticada (nunca link direto).
"""
import io
import os

from flask import (
    Blueprint, redirect, url_for, flash, request, send_file, abort,
)
from flask_login import login_required, current_user

from app import db
from app.auth_decorators import clinico_required
from app.models import Agendamento, Atendimento, Exame, AuditLog
from app.services.audit import audit
from app.services.storage import get_storage

exames_bp = Blueprint("exames", __name__, url_prefix="/exames")

_EXT_OK = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}


def _pode(atendimento) -> bool:
    """Profissional só acessa exames da própria agenda; admin acessa tudo."""
    if current_user.is_admin:
        return True
    return bool(
        current_user.is_profissional and current_user.profissional
        and atendimento and atendimento.profissional_id == current_user.profissional.id
    )


@exames_bp.route("/atendimento/<int:agendamento_id>", methods=["POST"])
@login_required
@clinico_required
def upload(agendamento_id):
    ag = db.session.get(Agendamento, agendamento_id)
    if not ag:
        flash("Agendamento não encontrado.", "error")
        return redirect(url_for("agenda.listar"))
    if current_user.is_profissional and (not _pode(ag)):
        flash("Você só anexa exames da sua agenda.", "error")
        return redirect(url_for("agenda.listar"))

    file = request.files.get("arquivo")
    destino = url_for("agenda.atendimento", agendamento_id=ag.id)
    if not file or not file.filename:
        flash("Selecione um arquivo.", "error")
        return redirect(destino)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in _EXT_OK:
        flash("Tipo não permitido. Use PDF, JPG, PNG ou WEBP.", "error")
        return redirect(destino)

    # Tamanho (limite global MAX_CONTENT_LENGTH já barra >5MB com 413).
    file.stream.seek(0, os.SEEK_END)
    tamanho = file.stream.tell()
    file.stream.seek(0)

    # Garante o registro de atendimento pra vincular o anexo.
    registro = ag.atendimento
    if registro is None:
        registro = Atendimento(agendamento_id=ag.id, paciente_id=ag.paciente_id,
                               profissional_id=ag.profissional_id)
        db.session.add(registro)
        db.session.flush()

    key = get_storage().save(file, subdir="exames", original_name=file.filename)
    ex = Exame(
        atendimento_id=registro.id, paciente_id=ag.paciente_id,
        nome_original=(file.filename or "exame")[:200],
        arquivo_key=key, content_type=file.mimetype, tamanho=tamanho,
        criado_por_id=current_user.id,
    )
    db.session.add(ex)
    db.session.commit()
    audit(AuditLog.ACAO_EXAME_ANEXADO, recurso_tipo="exame", recurso_id=ex.id)
    flash("Exame anexado.", "success")
    return redirect(destino)


@exames_bp.route("/<int:exame_id>/download")
@login_required
@clinico_required
def download(exame_id):
    ex = db.session.get(Exame, exame_id)
    if not ex:
        abort(404)
    if not _pode(ex.atendimento):
        abort(403)
    try:
        dados = get_storage().read(ex.arquivo_key)
    except FileNotFoundError:
        flash("Arquivo não encontrado no storage.", "error")
        return redirect(url_for("pacientes.detalhe", paciente_id=ex.paciente_id))
    return send_file(
        io.BytesIO(dados),
        mimetype=ex.content_type or "application/octet-stream",
        as_attachment=False, download_name=ex.nome_original or "exame",
    )


@exames_bp.route("/<int:exame_id>/excluir", methods=["POST"])
@login_required
@clinico_required
def excluir(exame_id):
    ex = db.session.get(Exame, exame_id)
    if not ex:
        flash("Exame não encontrado.", "error")
        return redirect(url_for("agenda.listar"))
    if not _pode(ex.atendimento):
        abort(403)
    ag_id = ex.atendimento.agendamento_id if ex.atendimento else None
    pac_id = ex.paciente_id
    key = ex.arquivo_key
    db.session.delete(ex)
    db.session.commit()
    get_storage().delete(key)
    audit(AuditLog.ACAO_EXAME_REMOVIDO, recurso_tipo="exame", recurso_id=exame_id)
    flash("Exame removido.", "success")
    if ag_id:
        return redirect(url_for("agenda.atendimento", agendamento_id=ag_id))
    return redirect(url_for("pacientes.detalhe", paciente_id=pac_id))
