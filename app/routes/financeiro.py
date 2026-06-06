"""Modulo financeiro: lancamentos (receitas/despesas), fluxo de caixa,
contas a receber/pagar e recebimento integrado da consulta.

Acesso: recepcao ou admin. Profissional NAO acessa o financeiro.
Dinheiro sempre Numeric/Decimal (nunca Float). Datas em UTC no DB; o
intervalo do periodo e calculado no fuso de Brasilia e convertido pra UTC.
"""
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
)
from flask_login import login_required, current_user
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app import db
from app.auth_decorators import recepcao_ou_admin
from app.models import (
    LancamentoFinanceiro, Paciente, Agendamento, AuditLog,
)
from app.services.audit import audit

financeiro_bp = Blueprint("financeiro", __name__, url_prefix="/financeiro")

_BR_TZ = ZoneInfo("America/Sao_Paulo")
_PERIODOS = ("dia", "semana", "mes")


def _parse_ref(valor: str):
    """'YYYY-MM-DD' -> date. Default: hoje (fuso BR)."""
    if valor:
        try:
            return datetime.strptime(valor, "%Y-%m-%d").date()
        except ValueError:
            pass
    return datetime.now(_BR_TZ).date()


def _intervalo(periodo: str, ref):
    """(ini_utc, fim_utc, ref_anterior, ref_seguinte, rotulo) pro periodo.

    Os limites sao meia-noite no fuso BR convertidos pra UTC aware, casando
    com o filtro por `pago_em` (armazenado em UTC).
    """
    if periodo == "dia":
        ini_d, fim_d = ref, ref + timedelta(days=1)
        ant, seg = ref - timedelta(days=1), ref + timedelta(days=1)
        rotulo = ref.strftime("%d/%m/%Y")
    elif periodo == "semana":
        ini_d = ref - timedelta(days=ref.weekday())   # segunda-feira
        fim_d = ini_d + timedelta(days=7)
        ant, seg = ini_d - timedelta(days=7), ini_d + timedelta(days=7)
        rotulo = (f"{ini_d.strftime('%d/%m')} a "
                  f"{(fim_d - timedelta(days=1)).strftime('%d/%m/%Y')}")
    else:  # mes (default)
        ini_d = ref.replace(day=1)
        fim_d = (ini_d.replace(year=ini_d.year + 1, month=1)
                 if ini_d.month == 12
                 else ini_d.replace(month=ini_d.month + 1))
        ant, seg = (ini_d - timedelta(days=1)).replace(day=1), fim_d
        rotulo = ini_d.strftime("%m/%Y")

    ini = datetime.combine(ini_d, time.min, tzinfo=_BR_TZ).astimezone(timezone.utc)
    fim = datetime.combine(fim_d, time.min, tzinfo=_BR_TZ).astimezone(timezone.utc)
    return ini, fim, ant.isoformat(), seg.isoformat(), rotulo


def _parse_valor(bruto: str):
    """Aceita '1.234,56' (BR) ou '1234.56'. Retorna Decimal>0 ou None."""
    if not bruto:
        return None
    s = bruto.strip().replace("R$", "").replace(" ", "")
    if "," in s:                       # formato BR: '.' milhar, ',' decimal
        s = s.replace(".", "").replace(",", ".")
    try:
        v = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    if v <= 0:
        return None
    return v.quantize(Decimal("0.01"))


def _soma(extra_where):
    """Soma de valor (coalesce 0) sob os filtros dados."""
    return db.session.execute(
        select(func.coalesce(func.sum(LancamentoFinanceiro.valor), 0))
        .where(*extra_where)
    ).scalar_one()


@financeiro_bp.route("/")
@login_required
@recepcao_ou_admin
def fluxo():
    """Fluxo de caixa do periodo (dia/semana/mes) — realizados (status=pago)."""
    periodo = request.args.get("periodo", "mes")
    if periodo not in _PERIODOS:
        periodo = "mes"
    ref = _parse_ref(request.args.get("ref", ""))
    ini, fim, ref_ant, ref_seg, rotulo = _intervalo(periodo, ref)

    L = LancamentoFinanceiro
    pagos_periodo = (L.status == L.STATUS_PAGO, L.pago_em >= ini, L.pago_em < fim)

    lancamentos = db.session.execute(
        select(L).where(*pagos_periodo).order_by(L.pago_em.desc())
    ).scalars().all()

    entradas = _soma((*pagos_periodo, L.tipo == L.TIPO_RECEITA))
    saidas = _soma((*pagos_periodo, L.tipo == L.TIPO_DESPESA))
    saldo = entradas - saidas

    # Pendentes (todo o periodo) pros cards secundarios "a receber / a pagar".
    a_receber = _soma((L.status == L.STATUS_PENDENTE, L.tipo == L.TIPO_RECEITA))
    a_pagar = _soma((L.status == L.STATUS_PENDENTE, L.tipo == L.TIPO_DESPESA))

    return render_template(
        "financeiro/fluxo.html",
        lancamentos=lancamentos, periodo=periodo, ref=ref.isoformat(),
        ref_ant=ref_ant, ref_seg=ref_seg, rotulo=rotulo,
        entradas=entradas, saidas=saidas, saldo=saldo,
        a_receber=a_receber, a_pagar=a_pagar,
    )


@financeiro_bp.route("/novo", methods=["GET", "POST"])
@login_required
@recepcao_ou_admin
def novo():
    pacientes = db.session.execute(
        select(Paciente).where(Paciente.ativo.is_(True))
        .order_by(Paciente.nome_completo)
    ).scalars().all()

    if request.method == "POST":
        L = LancamentoFinanceiro
        tipo = request.form.get("tipo", "").strip()
        if tipo not in (L.TIPO_RECEITA, L.TIPO_DESPESA):
            tipo = L.TIPO_RECEITA
        valor = _parse_valor(request.form.get("valor", ""))

        if not valor:
            flash("Informe um valor válido (maior que zero).", "error")
            return render_template("financeiro/form.html",
                                   pacientes=pacientes, form=request.form)

        vencimento = None
        venc = request.form.get("vencimento", "").strip()
        if venc:
            try:
                vencimento = datetime.strptime(venc, "%Y-%m-%d").date()
            except ValueError:
                vencimento = None

        lanc = L(
            tipo=tipo,
            categoria=request.form.get("categoria", "").strip() or None,
            descricao=request.form.get("descricao", "").strip() or None,
            valor=valor,
            forma_pagamento=request.form.get("forma_pagamento", "").strip() or None,
            vencimento=vencimento,
            convenio=request.form.get("convenio", "").strip() or None,
            criado_por_id=current_user.id,
        )
        paciente_id = request.form.get("paciente_id", type=int)
        if paciente_id and db.session.get(Paciente, paciente_id):
            lanc.paciente_id = paciente_id

        # Vindo da agenda (botao Pagamento): liga a consulta e herda o paciente.
        ag_id = request.form.get("agendamento_id", type=int)
        if ag_id:
            ag = db.session.get(Agendamento, ag_id)
            if ag and ag.lancamento is None:
                lanc.agendamento_id = ag.id
                if not lanc.paciente_id:
                    lanc.paciente_id = ag.paciente_id

        if request.form.get("status") == L.STATUS_PAGO:
            lanc.status = L.STATUS_PAGO
            lanc.pago_em = datetime.now(timezone.utc)
        else:
            lanc.status = L.STATUS_PENDENTE

        db.session.add(lanc)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Esta consulta já tem pagamento registrado.", "error")
            return redirect(url_for("financeiro.fluxo"))
        audit(AuditLog.ACAO_LANCAMENTO_CRIADO, recurso_tipo="lancamento",
              recurso_id=lanc.id, detalhes=f"tipo={tipo} status={lanc.status}")
        flash("Lançamento registrado.", "success")
        return redirect(url_for("financeiro.fluxo"))

    # GET: prefill quando vem da agenda (paciente/valor/consulta).
    form_inicial = {"status": "pago"}
    for k in ("tipo", "categoria", "valor", "descricao", "convenio"):
        v = request.args.get(k)
        if v:
            form_inicial[k] = v
    pid = request.args.get("paciente_id", type=int)
    if pid:
        form_inicial["paciente_id"] = pid
    ag_id = request.args.get("agendamento_id", type=int)
    if ag_id:
        ag = db.session.get(Agendamento, ag_id)
        if ag:
            form_inicial["agendamento_id"] = ag.id
            form_inicial.setdefault("paciente_id", ag.paciente_id)
            at = ag.atendimento
            if at and at.itens:
                # Puxa itens marcados pelo medico (total + descricao) — evita
                # a recepcao lancar manualmente/errado.
                form_inicial["descricao"] = " + ".join(
                    i.descricao or "Item" for i in at.itens)
                form_inicial.setdefault("valor", f"{at.total_itens:.2f}")
            else:
                form_inicial.setdefault(
                    "descricao", f"Consulta - {ag.paciente.nome_completo}")
                if ag.valor and "valor" not in form_inicial:
                    form_inicial["valor"] = f"{ag.valor:.2f}"
            if ag.convenio:
                form_inicial.setdefault("convenio", ag.convenio)
    return render_template("financeiro/form.html", pacientes=pacientes,
                           form=form_inicial)


@financeiro_bp.route("/<int:lancamento_id>/pagar", methods=["POST"])
@login_required
@recepcao_ou_admin
def pagar(lancamento_id):
    lanc = db.session.get(LancamentoFinanceiro, lancamento_id)
    if not lanc:
        flash("Lançamento não encontrado.", "error")
        return redirect(url_for("financeiro.contas"))
    if lanc.status == LancamentoFinanceiro.STATUS_PENDENTE:
        lanc.status = LancamentoFinanceiro.STATUS_PAGO
        lanc.pago_em = datetime.now(timezone.utc)
        forma = request.form.get("forma_pagamento", "").strip()
        if forma:
            lanc.forma_pagamento = forma
        db.session.commit()
        audit(AuditLog.ACAO_LANCAMENTO_PAGO, recurso_tipo="lancamento",
              recurso_id=lanc.id)
        flash("Pagamento registrado.", "success")
    return redirect(url_for("financeiro.contas"))


@financeiro_bp.route("/<int:lancamento_id>/cancelar", methods=["POST"])
@login_required
@recepcao_ou_admin
def cancelar(lancamento_id):
    lanc = db.session.get(LancamentoFinanceiro, lancamento_id)
    if not lanc:
        flash("Lançamento não encontrado.", "error")
        return redirect(url_for("financeiro.contas"))
    if lanc.status != LancamentoFinanceiro.STATUS_CANCELADO:
        lanc.status = LancamentoFinanceiro.STATUS_CANCELADO
        db.session.commit()
        audit(AuditLog.ACAO_LANCAMENTO_CANCELADO, recurso_tipo="lancamento",
              recurso_id=lanc.id)
        flash("Lançamento cancelado.", "success")
    return redirect(url_for("financeiro.contas"))


@financeiro_bp.route("/contas")
@login_required
@recepcao_ou_admin
def contas():
    """Contas a receber / a pagar — pendentes, vencidas primeiro por data."""
    L = LancamentoFinanceiro

    def _pendentes(tipo):
        return db.session.execute(
            select(L).where(L.status == L.STATUS_PENDENTE, L.tipo == tipo)
            .order_by(L.vencimento.is_(None), L.vencimento)
        ).scalars().all()

    a_receber = _pendentes(L.TIPO_RECEITA)
    a_pagar = _pendentes(L.TIPO_DESPESA)
    total_receber = sum((x.valor for x in a_receber), Decimal("0"))
    total_pagar = sum((x.valor for x in a_pagar), Decimal("0"))

    return render_template(
        "financeiro/contas.html",
        a_receber=a_receber, a_pagar=a_pagar,
        total_receber=total_receber, total_pagar=total_pagar,
    )


@financeiro_bp.route("/consulta/<int:agendamento_id>/receber", methods=["POST"])
@login_required
@recepcao_ou_admin
def receber(agendamento_id):
    """Recebimento integrado: gera a receita (paga) ligada a consulta.

    Idempotente — a relacao 1:1 (unique em agendamento_id) impede duplicar.
    """
    ag = db.session.get(Agendamento, agendamento_id)
    if not ag:
        flash("Agendamento não encontrado.", "error")
        return redirect(url_for("agenda.listar"))

    dia = ag.inicio.astimezone(_BR_TZ).date().isoformat()
    # Espelha no servidor a regra do template: so consulta confirmada/atendida
    # gera receita (evita receber de cancelada/faltou via POST direto).
    if ag.status not in (Agendamento.STATUS_CONFIRMADO, Agendamento.STATUS_ATENDIDO):
        flash("Só é possível registrar recebimento de consulta confirmada ou atendida.",
              "error")
        return redirect(url_for("agenda.listar", dia=dia))
    if ag.lancamento is not None:
        flash("Esta consulta já tem recebimento registrado.", "error")
        return redirect(url_for("agenda.listar", dia=dia))

    valor = _parse_valor(request.form.get("valor", "")) or ag.valor
    if not valor or valor <= 0:
        flash("Informe o valor da consulta para registrar o recebimento.",
              "error")
        return redirect(url_for("agenda.listar", dia=dia))

    lanc = LancamentoFinanceiro(
        tipo=LancamentoFinanceiro.TIPO_RECEITA,
        categoria="consulta",
        descricao=f"Consulta - {ag.paciente.nome_completo}",
        valor=valor,
        status=LancamentoFinanceiro.STATUS_PAGO,
        pago_em=datetime.now(timezone.utc),
        forma_pagamento=request.form.get("forma_pagamento", "").strip() or None,
        paciente_id=ag.paciente_id,
        agendamento_id=ag.id,
        convenio=ag.convenio,
        criado_por_id=current_user.id,
    )
    db.session.add(lanc)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        flash("Esta consulta já tem recebimento registrado.", "error")
        return redirect(url_for("agenda.listar", dia=dia))

    audit(AuditLog.ACAO_LANCAMENTO_PAGO, recurso_tipo="lancamento",
          recurso_id=lanc.id, detalhes="recebimento_consulta")
    flash("Recebimento da consulta registrado.", "success")
    return redirect(url_for("agenda.listar", dia=dia))
