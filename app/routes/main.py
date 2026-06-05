from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user
from sqlalchemy import select, func

from app import db
from app.models import Paciente, Profissional, Agendamento, LancamentoFinanceiro
from app.services.app_info import app_version, migration_head

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return render_template("main/index.html")


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
        .where(Agendamento.inicio >= hoje_ini, Agendamento.inicio <= hoje_fim)
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

    # KPIs financeiros do mes + retornos (so admin/recepcao).
    entradas_mes = a_receber = retornos_pendentes = None
    if current_user.is_admin or current_user.is_recepcao:
        from app.routes.crm import contar_retornos_pendentes
        retornos_pendentes = contar_retornos_pendentes()
        L = LancamentoFinanceiro
        mes_ini = hoje_ini.replace(day=1)
        mes_fim = (mes_ini.replace(year=mes_ini.year + 1, month=1)
                   if mes_ini.month == 12
                   else mes_ini.replace(month=mes_ini.month + 1))
        entradas_mes = db.session.execute(
            select(func.coalesce(func.sum(L.valor), 0)).where(
                L.status == L.STATUS_PAGO, L.tipo == L.TIPO_RECEITA,
                L.pago_em >= mes_ini, L.pago_em < mes_fim,
            )
        ).scalar_one()
        a_receber = db.session.execute(
            select(func.coalesce(func.sum(L.valor), 0)).where(
                L.status == L.STATUS_PENDENTE, L.tipo == L.TIPO_RECEITA,
            )
        ).scalar_one()

    return render_template(
        "main/dashboard.html",
        agendamentos_hoje=agendamentos_hoje,
        total_pacientes=total_pacientes,
        total_profissionais=total_profissionais,
        entradas_mes=entradas_mes,
        a_receber=a_receber,
        retornos_pendentes=retornos_pendentes,
    )


def _intervalo_hoje():
    """Inicio e fim do dia de hoje em UTC (aproximacao — suficiente pro MVP)."""
    agora = datetime.now(timezone.utc)
    ini = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    fim = ini + timedelta(days=1) - timedelta(seconds=1)
    return ini, fim