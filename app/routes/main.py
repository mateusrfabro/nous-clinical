import hmac
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint, render_template, redirect, url_for, jsonify, request,
    abort, current_app,
)
from flask_login import login_required, current_user
from sqlalchemy import select, func

from app import db, csrf, limiter
from app.models import Paciente, Profissional, Agendamento, LancamentoFinanceiro
from app.services.app_info import app_version, migration_head

main_bp = Blueprint("main", __name__)


@main_bp.route("/tarefas/lembretes", methods=["POST"])
@csrf.exempt
@limiter.limit("12 per hour")
def tarefa_lembretes():
    """Dispara os lembretes do dia (gatilho de cron externo).

    Protegido por token (config TAREFAS_TOKEN). Sem token configurado -> 404
    (recurso inexistente). Token errado -> 403. Endpoint de máquina: isento de
    CSRF e sem sessão.
    """
    token = current_app.config.get("TAREFAS_TOKEN")
    if not token:
        abort(404)
    enviado = request.args.get("key") or request.headers.get("X-Tarefa-Token", "")
    if not (enviado and hmac.compare_digest(enviado, token)):
        abort(403)
    from app.services.lembretes import enviar_lembretes
    return jsonify(enviar_lembretes())


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("main/index.html")


@main_bp.route("/buscar")
@login_required
def buscar():
    """Busca rápida de pacientes (paleta de comando Ctrl+K). Retorna JSON.

    Escopo por papel: recepção/admin acham qualquer paciente; profissional só
    os pacientes que atende (têm agendamento com ele).
    """
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"pacientes": []})

    sel = (select(Paciente)
           .where(Paciente.ativo.is_(True),
                  Paciente.nome_completo.ilike(f"%{q}%"))
           .order_by(Paciente.nome_completo)
           .limit(8))
    if current_user.is_profissional and current_user.profissional:
        sel = sel.where(Paciente.id.in_(
            select(Agendamento.paciente_id).where(
                Agendamento.profissional_id == current_user.profissional.id)
        ))
    elif current_user.is_profissional:
        return jsonify({"pacientes": []})

    pacientes = db.session.execute(sel).scalars().all()
    return jsonify({"pacientes": [
        {"id": p.id, "nome": p.nome_completo,
         "sub": p.convenio or p.telefone or "",
         "url": url_for("pacientes.detalhe", paciente_id=p.id)}
        for p in pacientes
    ]})


@main_bp.route("/health")
def health():
    """Healthcheck JSON pro orquestrador/deploy."""
    return jsonify({
        "status": "ok",
        "version": app_version(),
        "migration_head": migration_head(),
    })


@main_bp.route("/painel")
@login_required
def dashboard():
    hoje_ini, hoje_fim = _intervalo_hoje()

    # Agendamentos de hoje (filtrados pelo profissional se for o caso).
    q = (
        select(Agendamento)
        .where(Agendamento.inicio >= hoje_ini, Agendamento.inicio < hoje_fim)
        .order_by(Agendamento.inicio)
    )
    if current_user.is_profissional and current_user.profissional:
        q = q.where(Agendamento.profissional_id == current_user.profissional.id)

    agendamentos_hoje = db.session.execute(q).scalars().all()

    total_pacientes = db.session.execute(
        select(func.count(Paciente.id)).where(Paciente.ativo.is_(True))
    ).scalar_one()
    total_profissionais = db.session.execute(
        select(func.count(Profissional.id)).where(Profissional.ativo.is_(True))
    ).scalar_one()

    # Entrada da semana (receitas pagas seg-dom, fuso BR) — admin/recepcao.
    entrada_semana = None
    if current_user.is_admin or current_user.is_recepcao:
        from zoneinfo import ZoneInfo
        from datetime import time as _time
        BR = ZoneInfo("America/Sao_Paulo")
        hoje_br = datetime.now(BR).date()
        ini_sem = hoje_br - timedelta(days=hoje_br.weekday())   # segunda-feira
        fim_sem = ini_sem + timedelta(days=7)
        ini_utc = datetime.combine(ini_sem, _time.min, tzinfo=BR).astimezone(timezone.utc)
        fim_utc = datetime.combine(fim_sem, _time.min, tzinfo=BR).astimezone(timezone.utc)
        L = LancamentoFinanceiro
        entrada_semana = db.session.execute(
            select(func.coalesce(func.sum(L.valor), 0)).where(
                L.status == L.STATUS_PAGO, L.tipo == L.TIPO_RECEITA,
                L.pago_em >= ini_utc, L.pago_em < fim_utc,
            )
        ).scalar_one()

    return render_template(
        "main/dashboard.html",
        agendamentos_hoje=agendamentos_hoje,
        total_pacientes=total_pacientes,
        total_profissionais=total_profissionais,
        entrada_semana=entrada_semana,
    )


def _intervalo_hoje():
    """Inicio (incl.) e fim (excl.) do dia de hoje no fuso BR, em UTC aware.

    Casa com a agenda (que calcula o dia em America/Sao_Paulo) — evita
    divergencia de KPI nas primeiras horas do dia BR.
    """
    from zoneinfo import ZoneInfo
    from datetime import time as _time
    BR = ZoneInfo("America/Sao_Paulo")
    hoje = datetime.now(BR).date()
    ini = datetime.combine(hoje, _time.min, tzinfo=BR).astimezone(timezone.utc)
    fim = ini + timedelta(days=1)
    return ini, fim