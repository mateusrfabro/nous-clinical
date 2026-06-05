from datetime import datetime, timedelta, timezone

from flask import Blueprint, render_template, redirect, url_for, jsonify
from flask_login import login_required, current_user
from sqlalchemy import select, func

from app import db
from app.models import Paciente, Profissional, Agendamento
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

    return render_template(
        "main/dashboard.html",
        agendamentos_hoje=agendamentos_hoje,
        total_pacientes=total_pacientes,
        total_profissionais=total_profissionais,
    )


def _intervalo_hoje():
    """Inicio e fim do dia de hoje em UTC (aproximacao — suficiente pro MVP)."""
    agora = datetime.now(timezone.utc)
    ini = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    fim = ini + timedelta(days=1) - timedelta(seconds=1)
    return ini, fim