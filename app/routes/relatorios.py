"""Relatórios / BI (v1).

Indicadores do período (fuso BR): faturamento, despesas, saldo, ticket médio,
atendimentos, taxa de faltas, ranking por convênio e volume de procedimentos/
exames. Gate: recepcao_ou_admin. Filtros serão refinados com o sócio.
"""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import select, func

from app import db
from app.auth_decorators import recepcao_ou_admin
from app.models import (
    LancamentoFinanceiro, Agendamento, Atendimento, ItemAtendimento,
)

relatorios_bp = Blueprint("relatorios", __name__, url_prefix="/relatorios")
_BR = ZoneInfo("America/Sao_Paulo")


def _parse_d(valor, default):
    if valor:
        try:
            return datetime.strptime(valor, "%Y-%m-%d").date()
        except ValueError:
            pass
    return default


@relatorios_bp.route("/")
@login_required
@recepcao_ou_admin
def index():
    hoje = datetime.now(_BR).date()
    ini_d = _parse_d(request.args.get("ini"), hoje.replace(day=1))
    fim_d = _parse_d(request.args.get("fim"), hoje)
    if fim_d < ini_d:
        fim_d = ini_d
    ini = datetime.combine(ini_d, time.min, tzinfo=_BR).astimezone(timezone.utc)
    fim = datetime.combine(fim_d + timedelta(days=1), time.min,
                           tzinfo=_BR).astimezone(timezone.utc)

    L = LancamentoFinanceiro
    pago_periodo = (L.status == L.STATUS_PAGO, L.pago_em >= ini, L.pago_em < fim)

    def _soma(*w):
        return db.session.execute(
            select(func.coalesce(func.sum(L.valor), 0)).where(*w)
        ).scalar_one()

    receitas = _soma(*pago_periodo, L.tipo == L.TIPO_RECEITA)
    despesas = _soma(*pago_periodo, L.tipo == L.TIPO_DESPESA)
    saldo = receitas - despesas
    n_receitas = db.session.execute(
        select(func.count(L.id)).where(*pago_periodo, L.tipo == L.TIPO_RECEITA)
    ).scalar_one()
    ticket = (receitas / n_receitas) if n_receitas else Decimal("0.00")

    # Agendamentos por status no período (por data de início).
    rows = db.session.execute(
        select(Agendamento.status, func.count(Agendamento.id))
        .where(Agendamento.inicio >= ini, Agendamento.inicio < fim)
        .group_by(Agendamento.status)
    ).all()
    por_status = {s: c for s, c in rows}
    total_ags = sum(por_status.values())
    faltas = por_status.get(Agendamento.STATUS_FALTOU, 0)
    atendidos = por_status.get(Agendamento.STATUS_ATENDIDO, 0)
    cancelados = por_status.get(Agendamento.STATUS_CANCELADO, 0)
    taxa_faltas = (faltas / total_ags * 100) if total_ags else 0.0

    # Ranking por convênio (receitas pagas).
    conv_rows = db.session.execute(
        select(L.convenio, func.coalesce(func.sum(L.valor), 0))
        .where(*pago_periodo, L.tipo == L.TIPO_RECEITA)
        .group_by(L.convenio)
        .order_by(func.coalesce(func.sum(L.valor), 0).desc())
    ).all()
    por_convenio = [{"convenio": c or "Sem convênio", "total": t}
                    for c, t in conv_rows]

    # Volume de procedimentos/exames (itens marcados nos atendimentos).
    proc_rows = db.session.execute(
        select(ItemAtendimento.descricao,
               func.count(ItemAtendimento.id),
               func.coalesce(func.sum(ItemAtendimento.valor), 0))
        .join(Atendimento, ItemAtendimento.atendimento_id == Atendimento.id)
        .where(Atendimento.criado_em >= ini, Atendimento.criado_em < fim)
        .group_by(ItemAtendimento.descricao)
        .order_by(func.count(ItemAtendimento.id).desc())
    ).all()
    procedimentos = [{"nome": n or "—", "qtd": q, "total": t}
                     for n, q, t in proc_rows]

    return render_template(
        "relatorios/index.html",
        ini=ini_d.isoformat(), fim=fim_d.isoformat(),
        receitas=receitas, despesas=despesas, saldo=saldo,
        n_receitas=n_receitas, ticket=ticket,
        total_ags=total_ags, atendidos=atendidos, faltas=faltas,
        cancelados=cancelados, taxa_faltas=taxa_faltas,
        por_convenio=por_convenio, procedimentos=procedimentos,
    )
