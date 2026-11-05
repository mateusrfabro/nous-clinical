"""Anexos de exame/documento no atendimento. DADO SENSÍVEL (LGPD).

Upload/listagem/download/remoção gated a clínico (profissional/admin). O
profissional só mexe nos exames da própria agenda. Arquivos no storage (fora
de static/); download por esta rota autenticada (nunca link direto).
"""
import io
import logging
import os

from flask import (
    Blueprint, redirect, url_for, flash, request, send_file, abort,
)
from flask_login import login_required, current_user

from app import db
from app.auth_decorators import clinico_required
from app.models import Agendamento, Atendimento, Exame, AuditLog
from app.routes.agenda import aplicar_campos_prontuario
from app.services.audit import audit
from app.services.storage import get_storage
from app.services.tenant import get_da_clinica

exames_bp = Blueprint("exames", __name__, url_prefix="/exames")
logger = logging.getLogger(__name__)

# Extensão -> content-type confiável (derivado da extensão validada, NUNCA do
# mimetype enviado pelo cliente, que poderia contrabandear HTML same-origin).
_EXT_MIME = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
_EXT_OK = set(_EXT_MIME)


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
    ag = get_da_clinica(Agendamento, agendamento_id)
    if not ag:
        flash("Agendamento não encontrado.", "error")
        return redirect(url_for("agenda.listar"))
    if current_user.is_profissional and (not _pode(ag)):
        flash("Você só anexa exames da sua agenda.", "error")
        return redirect(url_for("agenda.listar"))

    destino = url_for("agenda.atendimento", agendamento_id=ag.id)

    # O upload vem do MESMO form do prontuário. ANTES de mexer no arquivo,
    # persiste o rascunho digitado (queixa/evolução/prescrição/itens/atestado)
    # — assim anexar nunca apaga o que o médico escreveu (bug reportado). NÃO
    # marca a consulta como atendida (isso só no "Salvar atendimento").
    registro = ag.atendimento
    if registro is None:
        registro = Atendimento(agendamento_id=ag.id, paciente_id=ag.paciente_id,
                               profissional_id=ag.profissional_id)
        db.session.add(registro)
        db.session.flush()
    aplicar_campos_prontuario(registro, ag)
    db.session.commit()

    file = request.files.get("arquivo")
    if not file or not file.filename:
        flash("Rascunho salvo. Selecione um arquivo para anexar.", "info")
        return redirect(destino)
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in _EXT_OK:
        flash("Tipo não permitido. Use PDF, JPG, PNG ou WEBP.", "error")
        return redirect(destino)

    # Tamanho (limite global MAX_CONTENT_LENGTH já barra >5MB com 413).
    file.stream.seek(0, os.SEEK_END)
    tamanho = file.stream.tell()
    file.stream.seek(0)

    # Falha de storage (disco cheio, S3 fora) não pode virar 500 cru: o rascunho
    # do prontuário já foi salvo acima; aqui só o anexo falha, com aviso amigável.
    try:
        key = get_storage().save(file, subdir="exames", original_name=file.filename)
    except Exception:   # noqa: BLE001
        logger.warning("EXAME_UPLOAD_STORAGE_FALHA ag=%s", ag.id, exc_info=True)
        flash("Rascunho salvo, mas não foi possível anexar o arquivo agora. "
              "Tente de novo em instantes.", "error")
        return redirect(destino)
    ex = Exame(
        atendimento_id=registro.id, paciente_id=ag.paciente_id,
        nome_original=(file.filename or "exame")[:200],
        arquivo_key=key, content_type=_EXT_MIME[ext], tamanho=tamanho,
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
    ex = get_da_clinica(Exame, exame_id)
    if not ex:
        abort(404)
    if not _pode(ex.atendimento):
        abort(403)
    try:
        dados = get_storage().read(ex.arquivo_key)
    except FileNotFoundError:
        flash("Arquivo não encontrado no storage.", "error")
        return redirect(url_for("pacientes.detalhe", paciente_id=ex.paciente_id))
    audit(AuditLog.ACAO_EXAME_BAIXADO, recurso_tipo="exame", recurso_id=ex.id)
    mime = ex.content_type or "application/octet-stream"
    inline = mime in set(_EXT_MIME.values())  # só tipos confiáveis abrem inline
    return send_file(
        io.BytesIO(dados), mimetype=mime,
        as_attachment=not inline, download_name=ex.nome_original or "exame",
    )


@exames_bp.route("/<int:exame_id>/excluir", methods=["POST"])
@login_required
@clinico_required
def excluir(exame_id):
    ex = get_da_clinica(Exame, exame_id)
    if not ex:
        flash("Exame não encontrado.", "error")
        return redirect(url_for("agenda.listar"))
    if not _pode(ex.atendimento):
        abort(403)
    ag_id = ex.atendimento.agendamento_id if ex.atendimento else None
    pac_id = ex.paciente_id
    key = ex.arquivo_key
    # Apaga o ARQUIVO primeiro (dado sensível LGPD). Se o storage falhar, aborta
    # sem tocar no DB — evita registro deletado com arquivo órfão persistido.
    try:
        get_storage().delete(key)
    except FileNotFoundError:
        pass   # já não existe no storage — segue e limpa o registro órfão
    except Exception:   # noqa: BLE001
        logger.warning("EXAME_DELETE_STORAGE_FALHA exame=%s", exame_id, exc_info=True)
        flash("Não foi possível remover o arquivo agora. Tente novamente.", "error")
        return redirect(url_for("agenda.atendimento", agendamento_id=ag_id)
                        if ag_id else url_for("pacientes.detalhe", paciente_id=pac_id))
    db.session.delete(ex)
    db.session.commit()
    audit(AuditLog.ACAO_EXAME_REMOVIDO, recurso_tipo="exame", recurso_id=exame_id)
    flash("Exame removido.", "success")
    if ag_id:
        return redirect(url_for("agenda.atendimento", agendamento_id=ag_id))
    return redirect(url_for("pacientes.detalhe", paciente_id=pac_id))
