"""Relatórios / BI — centro de inteligência da clínica.

Indicadores do período (fuso BR): faturamento, despesas, saldo, ticket médio,
atendimentos, taxa de faltas, ranking por convênio, volume de procedimentos,
**receita por médico**, **produtividade/ocupação por profissional**, **novos
pacientes + comparativo com o período anterior** e **pacientes em risco de
evasão**. Export CSV do faturamento. Gate: recepcao_ou_admin.
"""
import csv
import io
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import Blueprint, render_template, request, Response
from flask_login import login_required
from sqlalchemy import select, func

from app import db
from app.auth_decorators import recepcao_ou_admin
from app.models import (
    LancamentoFinanceiro, Agendamento, Atendimento, ItemAtendimento,
    Profissional, Paciente, AuditLog,
)
from app.services.audit import audit

relatorios_bp = Blueprint("relatorios", __name__, url_prefix="/relatorios")
_BR = ZoneInfo("America/Sao_Paulo")


def _parse_d(valor, default):
    if valor:
        try:
            return datetime.strptime(valor, "%Y-%m-%d").date()
        except ValueError:
            pass
    return default


def _periodo(args):
    """Lê ini/fim da query (datas BR) e devolve as bordas UTC + as datas."""
    hoje = datetime.now(_BR).date()
    ini_d = _parse_d(args.get("ini"), hoje.replace(day=1))
    fim_d = _parse_d(args.get("fim"), hoje)
    if fim_d < ini_d:
        fim_d = ini_d
    ini = datetime.combine(ini_d, time.min, tzinfo=_BR).astimezone(timezone.utc)
    fim = datetime.combine(fim_d + timedelta(days=1), time.min,
                           tzinfo=_BR).astimezone(timezone.utc)
    return ini_d, fim_d, ini, fim


def _agrega(ini, fim):
    """Calcula todos os indicadores do período [ini, fim) (UTC aware).

    Retorna um dict pronto pra render/CSV. Centralizado pra index() e export().
    """
    L = LancamentoFinanceiro
    A = Agendamento
    pago_periodo = (L.status == L.STATUS_PAGO, L.pago_em >= ini, L.pago_em < fim)

    def _soma(*w):
        return db.session.execute(
            select(func.coalesce(func.sum(L.valor), 0)).where(*w)
        ).scalar_one()

    def _conta_status(i, f):
        rows = db.session.execute(
            select(A.status, func.count(A.id))
            .where(A.inicio >= i, A.inicio < f)
            .group_by(A.status)
        ).all()
        return {s: c for s, c in rows}

    receitas = _soma(*pago_periodo, L.tipo == L.TIPO_RECEITA)
    despesas = _soma(*pago_periodo, L.tipo == L.TIPO_DESPESA)
    saldo = receitas - despesas
    n_receitas = db.session.execute(
        select(func.count(L.id)).where(*pago_periodo, L.tipo == L.TIPO_RECEITA)
    ).scalar_one()
    ticket = (receitas / n_receitas) if n_receitas else Decimal("0.00")

    por_status = _conta_status(ini, fim)
    total_ags = sum(por_status.values())
    faltas = por_status.get(A.STATUS_FALTOU, 0)
    atendidos = por_status.get(A.STATUS_ATENDIDO, 0)
    cancelados = por_status.get(A.STATUS_CANCELADO, 0)
    taxa_faltas = (faltas / total_ags * 100) if total_ags else 0.0

    # Novos pacientes cadastrados no período.
    novos_pacientes = db.session.execute(
        select(func.count(Paciente.id))
        .where(Paciente.criado_em >= ini, Paciente.criado_em < fim)
    ).scalar_one()

    # --- Comparativo com o período anterior de mesma duração ---
    dur = fim - ini
    ini_ant, fim_ant = ini - dur, ini
    pago_ant = (L.status == L.STATUS_PAGO, L.pago_em >= ini_ant,
                L.pago_em < fim_ant)
    receitas_ant = _soma(*pago_ant, L.tipo == L.TIPO_RECEITA)
    por_status_ant = _conta_status(ini_ant, fim_ant)
    atendidos_ant = por_status_ant.get(A.STATUS_ATENDIDO, 0)
    novos_ant = db.session.execute(
        select(func.count(Paciente.id))
        .where(Paciente.criado_em >= ini_ant, Paciente.criado_em < fim_ant)
    ).scalar_one()

    def _delta(atual, anterior):
        atual, anterior = float(atual or 0), float(anterior or 0)
        if not anterior:
            return None  # sem base de comparação
        return (atual - anterior) / anterior * 100

    comparativo = {
        "receitas_ant": receitas_ant,
        "atendidos_ant": atendidos_ant,
        "novos_ant": novos_ant,
        "d_receitas": _delta(receitas, receitas_ant),
        "d_atendidos": _delta(atendidos, atendidos_ant),
        "d_novos": _delta(novos_pacientes, novos_ant),
    }

    # Ranking por convênio (receitas pagas).
    conv_rows = db.session.execute(
        select(L.convenio, func.coalesce(func.sum(L.valor), 0))
        .where(*pago_periodo, L.tipo == L.TIPO_RECEITA)
        .group_by(L.convenio)
        .order_by(func.coalesce(func.sum(L.valor), 0).desc())
    ).all()
    por_convenio = [{"convenio": c or "Sem convênio", "total": t}
                    for c, t in conv_rows]

    # Receita por médico (consultas pagas ligadas a agendamento).
    med_rows = db.session.execute(
        select(Profissional.nome,
               func.coalesce(func.sum(L.valor), 0),
               func.count(L.id))
        .join(A, L.agendamento_id == A.id)
        .join(Profissional, A.profissional_id == Profissional.id)
        .where(*pago_periodo, L.tipo == L.TIPO_RECEITA)
        .group_by(Profissional.id, Profissional.nome)  # id evita colapsar homônimos
        .order_by(func.coalesce(func.sum(L.valor), 0).desc())
    ).all()
    por_medico = [{"nome": n, "total": t, "qtd": q} for n, t, q in med_rows]

    # Produtividade / ocupação por profissional (agendamentos do período).
    ocup_rows = db.session.execute(
        select(Profissional.nome, A.status, func.count(A.id))
        .join(Profissional, A.profissional_id == Profissional.id)
        .where(A.inicio >= ini, A.inicio < fim)
        .group_by(Profissional.nome, A.status)
    ).all()
    ocup = {}
    for nome, status, qtd in ocup_rows:
        d = ocup.setdefault(nome, {"total": 0, "atendidos": 0, "faltas": 0,
                                   "cancelados": 0})
        d["total"] += qtd
        if status == A.STATUS_ATENDIDO:
            d["atendidos"] += qtd
        elif status == A.STATUS_FALTOU:
            d["faltas"] += qtd
        elif status == A.STATUS_CANCELADO:
            d["cancelados"] += qtd
    produtividade = []
    for nome, d in ocup.items():
        t = d["total"]
        produtividade.append({
            "nome": nome, **d,
            "taxa_atend": (d["atendidos"] / t * 100) if t else 0.0,
            "taxa_falta": (d["faltas"] / t * 100) if t else 0.0,
        })
    produtividade.sort(key=lambda x: x["atendidos"], reverse=True)

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

    return {
        "receitas": receitas, "despesas": despesas, "saldo": saldo,
        "n_receitas": n_receitas, "ticket": ticket,
        "total_ags": total_ags, "atendidos": atendidos, "faltas": faltas,
        "cancelados": cancelados, "taxa_faltas": taxa_faltas,
        "novos_pacientes": novos_pacientes, "comparativo": comparativo,
        "por_convenio": por_convenio, "por_medico": por_medico,
        "produtividade": produtividade, "procedimentos": procedimentos,
    }


def _risco_evasao(limite_dias=180, maximo=50):
    """Pacientes ativos cujo último atendimento passou de `limite_dias` e que
    não têm consulta futura agendada — candidatos a recall (anti-churn)."""
    hoje = datetime.now(_BR).date()
    limite = datetime.combine(hoje - timedelta(days=limite_dias), time.min,
                              tzinfo=_BR).astimezone(timezone.utc)
    agora = datetime.now(timezone.utc)

    ult = (select(Atendimento.paciente_id.label("pid"),
                  func.max(Atendimento.criado_em).label("ult"))
           .group_by(Atendimento.paciente_id).subquery())
    tem_futuro = (
        select(Agendamento.id)
        .where(Agendamento.paciente_id == Paciente.id,
               Agendamento.inicio >= agora,
               Agendamento.status.in_([Agendamento.STATUS_AGENDADO,
                                       Agendamento.STATUS_CONFIRMADO]))
        .exists()
    )
    rows = db.session.execute(
        select(Paciente.id, Paciente.nome_completo, Paciente.telefone,
               Paciente.convenio, ult.c.ult)
        .join(ult, ult.c.pid == Paciente.id)
        .where(Paciente.ativo.is_(True), ult.c.ult < limite, ~tem_futuro)
        .order_by(ult.c.ult.asc())
        .limit(maximo)
    ).all()
    return [{"id": i, "nome": n, "telefone": tel, "convenio": c, "ultimo": u}
            for i, n, tel, c, u in rows]


@relatorios_bp.route("/")
@login_required
@recepcao_ou_admin
def index():
    ini_d, fim_d, ini, fim = _periodo(request.args)
    dados = _agrega(ini, fim)
    return render_template(
        "relatorios/index.html",
        ini=ini_d.isoformat(), fim=fim_d.isoformat(),
        evasao=_risco_evasao(),
        **dados,
    )


@relatorios_bp.route("/export.csv")
@login_required
@recepcao_ou_admin
def export_csv():
    """Exporta os recebimentos (receitas pagas) do período em CSV.

    Acesso a dado financeiro consolidado — auditado (LGPD/governança).
    """
    ini_d, fim_d, ini, fim = _periodo(request.args)
    L = LancamentoFinanceiro
    rows = db.session.execute(
        select(L.pago_em, L.categoria, L.descricao, L.convenio,
               L.forma_pagamento, L.valor)
        .where(L.status == L.STATUS_PAGO, L.tipo == L.TIPO_RECEITA,
               L.pago_em >= ini, L.pago_em < fim)
        .order_by(L.pago_em)
    ).all()

    def _safe(v):
        """Neutraliza CSV/formula injection: célula de texto iniciada por
        = + - @ (ou TAB/CR) é prefixada com aspa simples — assim o Excel/Calc
        não interpreta como fórmula ao abrir o arquivo."""
        s = "" if v is None else str(v)
        if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + s
        return s

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Data", "Categoria", "Descrição", "Convênio",
                "Forma de pagamento", "Valor (R$)"])
    for pago_em, categoria, descricao, convenio, forma, valor in rows:
        dt = pago_em
        if dt is not None and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        data_br = dt.astimezone(_BR).strftime("%d/%m/%Y") if dt else ""
        valor_br = f"{float(valor or 0):.2f}".replace(".", ",")
        w.writerow([data_br, _safe(categoria), _safe(descricao),
                    _safe(convenio), _safe(forma), valor_br])

    audit(AuditLog.ACAO_RELATORIO_EXPORTADO,
          detalhes=f"faturamento {ini_d}..{fim_d} ({len(rows)} linhas)")

    nome = f"faturamento_{ini_d}_{fim_d}.csv"
    # BOM pro Excel reconhecer UTF-8 com acentos.
    conteudo = "﻿" + buf.getvalue()
    return Response(
        conteudo, mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
