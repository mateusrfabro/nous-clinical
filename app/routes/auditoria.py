"""Tela de auditoria (visualização do AuditLog). Gate: admin.

A trilha é append-only (gravada pelo service `audit`). Aqui o admin LÊ as
ações da própria clínica — escopo aplicado via join em Usuario.clinica_id
(AuditLog não tem clinica_id próprio; o vínculo é pelo usuário que agiu).
Superadmin (sem clínica) vê tudo.
"""
import csv
import io
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, request, Response
from flask_login import login_required, current_user
from sqlalchemy import select, func

from app import db
from app.auth_decorators import admin_required
from app.models import AuditLog, Usuario
from app.services.audit import audit

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
    "atendimento_editado": "Prontuário editado",
    "profissional_criado": "Profissional criado",
    "profissional_editado": "Profissional editado",
    "clinica_criada": "Clínica criada",
    "clinica_status": "Status de clínica",
    "lancamento_criado": "Lançamento criado",
    "lancamento_pago": "Lançamento pago",
    "lancamento_cancelado": "Lançamento cancelado",
    "procedimento_salvo": "Item/procedimento salvo",
    "procedimento_excluido": "Item/procedimento excluído",
    "convenio_salvo": "Convênio salvo",
    "sala_salva": "Sala salva",
    "exame_anexado": "Exame anexado",
    "exame_removido": "Exame removido",
    "prontuario_visualizado": "Prontuário visualizado",
    "exame_baixado": "Exame baixado",
    "relatorio_exportado": "Relatório exportado",
    "documento_emitido": "Documento emitido (PDF)",
    "crm_interacao": "Interação de CRM registrada",
    "bloqueio_criado": "Bloqueio de agenda criado",
    "bloqueio_removido": "Bloqueio de agenda removido",
    "ajuda_consulta": "Consulta ao assistente de ajuda",
    "whatsapp_config": "WhatsApp configurado",
    "whatsapp_enviada": "Mensagem WhatsApp enviada",
    "fiscal_config": "Configuração fiscal (NF)",
    "conciliacao_import": "Extrato bancário importado",
    "conciliacao_conciliado": "Movimento conciliado",
    "conciliacao_ignorado": "Movimento ignorado",
    "conciliacao_desfeito": "Conciliação desfeita",
}


def _parse_data(valor):
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _base_filtrada(acao, ini, fim):
    """SELECT de AuditLog escopado por clínica + filtros (ação, período).
    Reusado pela listagem e pelo export CSV."""
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
    return base


@auditoria_bp.route("/")
@login_required
@admin_required
def listar():
    pagina = max(request.args.get("pagina", 1, type=int) or 1, 1)
    acao = request.args.get("acao", "").strip()
    ini = _parse_data(request.args.get("ini"))
    fim = _parse_data(request.args.get("fim"))

    base = _base_filtrada(acao, ini, fim)

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


def _safe_csv(v):
    """Neutraliza CSV/formula injection (Excel/Calc)."""
    s = "" if v is None else str(v)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


@auditoria_bp.route("/export.csv")
@login_required
@admin_required
def export_csv():
    """Exporta a trilha de auditoria filtrada em CSV (req. do sócio 3.7).
    Colunas: Data, Hora, Usuário, Ação, Módulo, Registro, Detalhes."""
    acao = request.args.get("acao", "").strip()
    ini = _parse_data(request.args.get("ini"))
    fim = _parse_data(request.args.get("fim"))
    base = _base_filtrada(acao, ini, fim)

    _LIMITE = 20000
    logs = db.session.execute(
        base.order_by(AuditLog.criado_em.desc()).limit(_LIMITE)
    ).scalars().all()
    truncado = len(logs) >= _LIMITE

    uids = {x.usuario_id for x in logs if x.usuario_id}
    usuarios = {}
    if uids:
        for u in db.session.execute(
            select(Usuario).where(Usuario.id.in_(uids))
        ).scalars().all():
            usuarios[u.id] = u

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Data", "Hora", "Usuário", "Ação", "Módulo", "Registro",
                "Detalhes", "IP"])
    for log in logs:
        dt = log.criado_em
        if dt is not None and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_br = dt.astimezone(_BR) if dt else None
        u = usuarios.get(log.usuario_id)
        quem = (u.email if u else (f"#{log.usuario_id}" if log.usuario_id else "—"))
        w.writerow([
            dt_br.strftime("%d/%m/%Y") if dt_br else "",
            dt_br.strftime("%H:%M:%S") if dt_br else "",
            _safe_csv(quem),
            _safe_csv(ACAO_LABEL.get(log.acao, log.acao)),
            _safe_csv(log.recurso_tipo or ""),
            _safe_csv(log.recurso_id or ""),
            _safe_csv(log.detalhes or ""),
            _safe_csv(log.ip or ""),
        ])

    if truncado:
        # Sinaliza o truncamento na própria planilha (em vez de silencioso).
        w.writerow([f"# AVISO: exportação limitada a {_LIMITE} linhas "
                    "(mais antigas omitidas). Refine o período/ação."])
    audit(AuditLog.ACAO_RELATORIO_EXPORTADO,
          detalhes=f"auditoria ({len(logs)} linhas{' TRUNCADO' if truncado else ''})")
    conteudo = "﻿" + buf.getvalue()   # BOM p/ Excel reconhecer UTF-8
    return Response(
        conteudo, mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="auditoria.csv"'},
    )
