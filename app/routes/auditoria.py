"""Tela de auditoria (visualização do AuditLog). Gate: admin.

A trilha é append-only (gravada pelo service `audit`). Aqui o admin LÊ as
ações da própria clínica — escopo aplicado via join em Usuario.clinica_id
(AuditLog não tem clinica_id próprio; o vínculo é pelo usuário que agiu).
Superadmin (sem clínica) vê tudo.
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from sqlalchemy import select, func

from app import db
from app.auth_decorators import admin_required
from app.models import AuditLog, Usuario

auditoria_bp = Blueprint("auditoria", __name__, url_prefix="/auditoria")

_BR = ZoneInfo("America/Sao_Paulo")
_POR_PAGINA = 50

# Rótulos PT-BR das ações (chave = AuditLog.ACAO_*).
ACAO_LABEL = {
    "login_ok": "Login",
    "login_fail": "Login falhou",
    "logout": "Logout",
    "senha_redefinida": "Senha redefinida",
    "paciente_criado": "Paciente criado",
    "paciente_editado": "Paciente editado",
    "agendamento_criado": "Agendamento criado",
    "agendamento_status": "Status de agendamento",
    "agendamento_editado": "Agendamento editado",
    "agendamento_checkin": "Check-in",
    "agendamento_confirmado_publico": "Confirmação (link público)",
    "atendimento_registrado": "Atendimento registrado",
    "profissional_criado": "Profissional criado",
    "profissional_editado": "Profissional editado",
    "clinica_criada": "Clínica criada",
    "clinica_status": "Status de clínica",
    "lancamento_criado": "Lançamento criado",
    "lancamento_pago": "Lançamento pago",
    "lancamento_cancelado": "Lançamento cancelado",
    "procedimento_salvo": "Item/procedimento salvo",
    "convenio_salvo": "Convênio salvo",
    "exame_anexado": "Exame anexado",
    "exame_removido": "Exame removido",
    "prontuario_visualizado": "Prontuário visualizado",
    "exame_baixado": "Exame baixado",
    "relatorio_exportado": "Relatório exportado",
}


def _parse_data(valor):
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


@auditoria_bp.route("/")
@login_required
@admin_required
def listar():
    pagina = max(request.args.get("pagina", 1, type=int) or 1, 1)
    acao = request.args.get("acao", "").strip()
    ini = _parse_data(request.args.get("ini"))
    fim = _parse_data(request.args.get("fim"))

    base = select(AuditLog)
    # Escopo por clínica via usuário que agiu (AuditLog não é tenant-scoped).
    if not current_user.is_superadmin and current_user.clinica_id:
        ids = db.session.execute(
            select(Usuario.id).where(
                Usuario.clinica_id == current_user.clinica_id)
        ).scalars().all()
        base = base.where(AuditLog.usuario_id.in_(ids))

    if acao:
        base = base.where(AuditLog.acao == acao)
    if ini:
        ini_utc = datetime.combine(ini, time.min, tzinfo=_BR).astimezone(timezone.utc)
        base = base.where(AuditLog.criado_em >= ini_utc)
    if fim:
        fim_utc = datetime.combine(fim + timedelta(days=1), time.min,
                                   tzinfo=_BR).astimezone(timezone.utc)
        base = base.where(AuditLog.criado_em < fim_utc)

    total = db.session.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()
    paginas = max((total + _POR_PAGINA - 1) // _POR_PAGINA, 1)
    pagina = min(pagina, paginas)

    logs = db.session.execute(
        base.order_by(AuditLog.criado_em.desc())
        .limit(_POR_PAGINA).offset((pagina - 1) * _POR_PAGINA)
    ).scalars().all()

    # Mapa usuario_id -> nome/email pra exibir quem agiu.
    uids = {x.usuario_id for x in logs if x.usuario_id}
    usuarios = {}
    if uids:
        for u in db.session.execute(
            select(Usuario).where(Usuario.id.in_(uids))
        ).scalars().all():
            usuarios[u.id] = u

    return render_template(
        "auditoria/listar.html",
        logs=logs, usuarios=usuarios, acao_label=ACAO_LABEL,
        acoes=sorted(ACAO_LABEL.items(), key=lambda kv: kv[1]),
        acao_sel=acao, ini=request.args.get("ini", ""),
        fim=request.args.get("fim", ""),
        pagina=pagina, paginas=paginas, total=total,
    )
