"""Modulo financeiro: lancamentos (receitas/despesas), fluxo de caixa,
contas a receber/pagar e recebimento integrado da consulta.

Acesso: recepcao ou admin. Profissional NAO acessa o financeiro.
Dinheiro sempre Numeric/Decimal (nunca Float). Datas em UTC no DB; o
intervalo do periodo e calculado no fuso de Brasilia e convertido pra UTC.
"""
import json
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
)
from flask import abort
from flask_login import login_required, current_user
from sqlalchemy import select, func, or_
from sqlalchemy.orm import selectinload
from sqlalchemy.exc import IntegrityError

from app import db
from app.auth_decorators import recepcao_ou_admin
from app.models import (
    LancamentoFinanceiro, Paciente, Agendamento, AuditLog, MovimentoBancario,
    FechamentoCaixa,
)
from app.services.audit import audit
from app.services.ofx import OFXError
from app.services.extrato import parse_extrato
from app.services.conciliacao import (
    importar_extrato, sugestao_para, candidatos_para,
    lancamentos_nao_conciliados,
)

financeiro_bp = Blueprint("financeiro", __name__, url_prefix="/financeiro")

_BR_TZ = ZoneInfo("America/Sao_Paulo")
_PERIODOS = ("dia", "semana", "mes")
# Despesas sensíveis que a recepção NÃO vê nem lança (decisão de negócio).
_CATEGORIAS_RESTRITAS = ("aluguel", "salario", "imposto")


def _get_tenant(Model, id_):
    """db.session.get + guard EXPLÍCITO de clínica (defesa em profundidade).
    Além do escopo automático do tenant loader, recusa objeto de outra clínica —
    blinda contra qualquer caminho que furasse o escopo. None se inexistente ou
    de outro tenant."""
    obj = db.session.get(Model, id_)
    if obj is None:
        return None
    cid = getattr(obj, "clinica_id", None)
    if cid is not None and cid != current_user.clinica_id:
        return None
    return obj


def _filtro_categoria():
    """Clausula(s) que escondem as categorias sensíveis da recepção.

    Admin: lista vazia (vê tudo). Recepção: oculta aluguel/salário/imposto
    (tratando categoria NULL como visível — NOT IN é NULL-inseguro)."""
    if current_user.is_recepcao:
        L = LancamentoFinanceiro
        return [or_(L.categoria.is_(None),
                    L.categoria.notin_(_CATEGORIAS_RESTRITAS))]
    return []


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
    cat = _filtro_categoria()
    pagos_periodo = (L.status == L.STATUS_PAGO, L.pago_em >= ini,
                     L.pago_em < fim, *cat)

    lancamentos = db.session.execute(
        select(L).where(*pagos_periodo).order_by(L.pago_em.desc())
    ).scalars().all()

    entradas = _soma((*pagos_periodo, L.tipo == L.TIPO_RECEITA))
    saidas = _soma((*pagos_periodo, L.tipo == L.TIPO_DESPESA))
    saldo = entradas - saidas

    # Pendentes (todo o periodo) pros cards secundarios "a receber / a pagar".
    a_receber = _soma((L.status == L.STATUS_PENDENTE, L.tipo == L.TIPO_RECEITA, *cat))
    a_pagar = _soma((L.status == L.STATUS_PENDENTE, L.tipo == L.TIPO_DESPESA, *cat))

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
        categoria = request.form.get("categoria", "").strip() or None

        if not valor:
            flash("Informe um valor válido (maior que zero).", "error")
            return render_template("financeiro/form.html",
                                   pacientes=pacientes, form=request.form)
        if current_user.is_recepcao and categoria in _CATEGORIAS_RESTRITAS:
            flash("Sem permissão para lançar despesas de aluguel, salário ou "
                  "imposto. Fale com o administrador.", "error")
            return render_template("financeiro/form.html",
                                   pacientes=pacientes, form=request.form)

        # Forma de pagamento obrigatória ao registrar algo já pago/recebido
        # (req. do sócio). Em conta pendente ela é definida na baixa.
        forma = request.form.get("forma_pagamento", "").strip()
        if request.form.get("status") == L.STATUS_PAGO and not forma:
            flash("Informe a forma de pagamento.", "error")
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
            categoria=categoria,
            descricao=request.form.get("descricao", "").strip() or None,
            valor=valor,
            forma_pagamento=forma or None,
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
            if ag:
                if ag.status not in (Agendamento.STATUS_CONFIRMADO,
                                     Agendamento.STATUS_ATENDIDO):
                    flash("Só registra pagamento de consulta confirmada ou "
                          "atendida.", "error")
                    return render_template("financeiro/form.html",
                                           pacientes=pacientes, form=request.form)
                if ag.lancamento is not None:
                    flash("Esta consulta já tem pagamento registrado.", "error")
                    return render_template("financeiro/form.html",
                                           pacientes=pacientes, form=request.form)
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
    lanc = _get_tenant(LancamentoFinanceiro, lancamento_id)
    if not lanc:
        flash("Lançamento não encontrado.", "error")
        return redirect(url_for("financeiro.contas"))
    if current_user.is_recepcao and lanc.categoria in _CATEGORIAS_RESTRITAS:
        abort(403)
    if lanc.status == LancamentoFinanceiro.STATUS_PENDENTE:
        # Forma de pagamento obrigatória na baixa (req. do sócio).
        forma = request.form.get("forma_pagamento", "").strip()
        if not forma:
            flash("Selecione a forma de pagamento para dar baixa.", "error")
            return redirect(url_for("financeiro.contas"))
        lanc.status = LancamentoFinanceiro.STATUS_PAGO
        lanc.pago_em = datetime.now(timezone.utc)
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
    lanc = _get_tenant(LancamentoFinanceiro, lancamento_id)
    if not lanc:
        flash("Lançamento não encontrado.", "error")
        return redirect(url_for("financeiro.contas"))
    if current_user.is_recepcao and lanc.categoria in _CATEGORIAS_RESTRITAS:
        abort(403)
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

    cat = _filtro_categoria()

    def _pendentes(tipo):
        return db.session.execute(
            select(L).where(L.status == L.STATUS_PENDENTE, L.tipo == tipo, *cat)
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


# ===================== Conciliação bancária (OFX) =====================

@financeiro_bp.route("/conciliacao")
@login_required
@recepcao_ou_admin
def conciliacao():
    """Painel de conciliação: lista os movimentos do extrato (pendentes
    primeiro) com a sugestão de lançamento p/ cada pendente."""
    M = MovimentoBancario
    movimentos = db.session.execute(
        select(M).options(selectinload(M.lancamento))
        # pendentes primeiro, depois mais recentes.
        .order_by(M.status != M.STATUS_PENDENTE, M.data.desc(), M.id.desc())
    ).scalars().all()
    sugestoes = {m.id: sugestao_para(m)
                 for m in movimentos if m.status == M.STATUS_PENDENTE}
    n_pend = sum(1 for m in movimentos if m.status == M.STATUS_PENDENTE)
    n_conc = sum(1 for m in movimentos if m.status == M.STATUS_CONCILIADO)
    # Divergência do outro lado: receitas pagas (últimos 30d) sem extrato casado.
    desde = datetime.now(timezone.utc) - timedelta(days=30)
    sem_extrato = lancamentos_nao_conciliados(current_user.clinica_id, desde)
    return render_template(
        "financeiro/conciliacao.html",
        movimentos=movimentos, sugestoes=sugestoes,
        n_pend=n_pend, n_conc=n_conc, n_sem_extrato=len(sem_extrato),
    )


@financeiro_bp.route("/conciliacao/<int:movimento_id>")
@login_required
@recepcao_ou_admin
def conciliacao_detalhe(movimento_id):
    """Conciliação MANUAL: escolher um lançamento existente p/ o movimento
    quando a sugestão automática não serve (valor não bate exatamente)."""
    mov = _mov_ou_redirect(movimento_id)
    if not mov:
        return redirect(url_for("financeiro.conciliacao"))
    candidatos = candidatos_para(mov)
    return render_template(
        "financeiro/conciliacao_detalhe.html",
        mov=mov, candidatos=candidatos)


@financeiro_bp.route("/conciliacao/divergencias")
@login_required
@recepcao_ou_admin
def conciliacao_divergencias():
    """Os dois lados da divergência num período: movimentos do extrato sem
    lançamento (pendentes) × receitas pagas sem extrato casado."""
    dias = request.args.get("dias", 30, type=int)
    dias = max(1, min(dias, 365))
    desde_dia = datetime.now(_BR_TZ).date() - timedelta(days=dias)
    desde_utc = datetime.combine(desde_dia, time.min,
                                 tzinfo=_BR_TZ).astimezone(timezone.utc)
    M = MovimentoBancario
    pendentes = db.session.execute(
        select(M).where(M.status == M.STATUS_PENDENTE, M.data >= desde_dia)
        .order_by(M.data.desc(), M.id.desc())
    ).scalars().all()
    sem_extrato = lancamentos_nao_conciliados(current_user.clinica_id, desde_utc)
    total_pend = sum((m.valor for m in pendentes), Decimal("0"))
    total_sem = sum((x.valor for x in sem_extrato), Decimal("0"))
    return render_template(
        "financeiro/divergencias.html",
        pendentes=pendentes, sem_extrato=sem_extrato,
        total_pend=total_pend, total_sem=total_sem, dias=dias)


@financeiro_bp.route("/conciliacao/importar", methods=["POST"])
@login_required
@recepcao_ou_admin
def conciliacao_importar():
    arquivo = request.files.get("extrato")
    if not arquivo or not arquivo.filename:
        flash("Selecione um arquivo .ofx ou .csv do seu banco.", "error")
        return redirect(url_for("financeiro.conciliacao"))
    try:
        extrato = parse_extrato(arquivo.filename, arquivo.read())
    except OFXError as e:
        flash(f"Não foi possível ler o extrato: {e}", "error")
        return redirect(url_for("financeiro.conciliacao"))
    novos, dup = importar_extrato(
        extrato, current_user.clinica_id, current_user.id)
    audit(AuditLog.ACAO_CONCILIACAO_IMPORT, recurso_tipo="extrato",
          detalhes=f"novos={novos} dup={dup} conta={extrato.conta or '-'}")
    flash(f"Extrato importado: {novos} novo(s), {dup} já existente(s).",
          "success")
    return redirect(url_for("financeiro.conciliacao"))


def _mov_ou_redirect(movimento_id):
    """Carrega o movimento (auto-escopado por clínica) ou redireciona."""
    mov = _get_tenant(MovimentoBancario, movimento_id)
    if not mov:
        flash("Movimento não encontrado.", "error")
    return mov


@financeiro_bp.route("/conciliacao/<int:movimento_id>/conciliar",
                     methods=["POST"])
@login_required
@recepcao_ou_admin
def conciliacao_conciliar(movimento_id):
    """Casa o movimento a um lançamento existente (id vindo da sugestão)."""
    mov = _mov_ou_redirect(movimento_id)
    if not mov:
        return redirect(url_for("financeiro.conciliacao"))
    lanc_id = request.form.get("lancamento_id", type=int)
    lanc = _get_tenant(LancamentoFinanceiro, lanc_id) if lanc_id else None
    if not lanc:
        flash("Lançamento para conciliar não encontrado.", "error")
        return redirect(url_for("financeiro.conciliacao"))
    if lanc.movimento is not None and lanc.movimento.id != mov.id:
        flash("Esse lançamento já está conciliado com outro movimento.", "error")
        return redirect(url_for("financeiro.conciliacao"))
    mov.lancamento_id = lanc.id
    mov.status = MovimentoBancario.STATUS_CONCILIADO
    mov.conciliado_em = datetime.now(timezone.utc)
    mov.conciliado_por_id = current_user.id
    db.session.commit()
    audit(AuditLog.ACAO_CONCILIACAO_CONCILIADO, recurso_tipo="movimento",
          recurso_id=mov.id, detalhes=f"lancamento={lanc.id}")
    flash("Movimento conciliado.", "success")
    return redirect(url_for("financeiro.conciliacao"))


@financeiro_bp.route("/conciliacao/<int:movimento_id>/criar", methods=["POST"])
@login_required
@recepcao_ou_admin
def conciliacao_criar(movimento_id):
    """Cria um lançamento (pago) a partir do movimento e já concilia."""
    mov = _mov_ou_redirect(movimento_id)
    if not mov:
        return redirect(url_for("financeiro.conciliacao"))
    if mov.status == MovimentoBancario.STATUS_CONCILIADO:
        flash("Movimento já conciliado.", "error")
        return redirect(url_for("financeiro.conciliacao"))
    L = LancamentoFinanceiro
    tipo = (L.TIPO_RECEITA if mov.tipo == MovimentoBancario.TIPO_CREDITO
            else L.TIPO_DESPESA)
    # Data do extrato ao meio-dia BR -> UTC (evita virar o dia perto da 00h).
    pago_em = datetime.combine(mov.data, time(12, 0),
                               tzinfo=_BR_TZ).astimezone(timezone.utc)
    lanc = L(tipo=tipo, categoria="outro",
             descricao=(mov.descricao or "Movimento bancário")[:200],
             valor=mov.valor, status=L.STATUS_PAGO, pago_em=pago_em,
             criado_por_id=current_user.id)
    db.session.add(lanc)
    db.session.flush()
    mov.lancamento_id = lanc.id
    mov.status = MovimentoBancario.STATUS_CONCILIADO
    mov.conciliado_em = datetime.now(timezone.utc)
    mov.conciliado_por_id = current_user.id
    db.session.commit()
    audit(AuditLog.ACAO_LANCAMENTO_CRIADO, recurso_tipo="lancamento",
          recurso_id=lanc.id, detalhes=f"tipo={tipo} via=conciliacao")
    audit(AuditLog.ACAO_CONCILIACAO_CONCILIADO, recurso_tipo="movimento",
          recurso_id=mov.id, detalhes=f"lancamento={lanc.id} novo")
    flash("Lançamento criado e movimento conciliado.", "success")
    return redirect(url_for("financeiro.conciliacao"))


@financeiro_bp.route("/conciliacao/<int:movimento_id>/ignorar",
                     methods=["POST"])
@login_required
@recepcao_ou_admin
def conciliacao_ignorar(movimento_id):
    """Marca o movimento como ignorado (tarifa, transferência interna...)."""
    mov = _mov_ou_redirect(movimento_id)
    if not mov:
        return redirect(url_for("financeiro.conciliacao"))
    if mov.status != MovimentoBancario.STATUS_CONCILIADO:
        mov.status = MovimentoBancario.STATUS_IGNORADO
        db.session.commit()
        audit(AuditLog.ACAO_CONCILIACAO_IGNORADO, recurso_tipo="movimento",
              recurso_id=mov.id)
        flash("Movimento ignorado.", "success")
    return redirect(url_for("financeiro.conciliacao"))


@financeiro_bp.route("/conciliacao/<int:movimento_id>/desfazer",
                     methods=["POST"])
@login_required
@recepcao_ou_admin
def conciliacao_desfazer(movimento_id):
    """Volta o movimento p/ pendente (desfaz conciliação/ignore). NÃO apaga o
    lançamento vinculado — só desfaz o vínculo."""
    mov = _mov_ou_redirect(movimento_id)
    if not mov:
        return redirect(url_for("financeiro.conciliacao"))
    mov.lancamento_id = None
    mov.status = MovimentoBancario.STATUS_PENDENTE
    mov.conciliado_em = None
    mov.conciliado_por_id = None
    db.session.commit()
    audit(AuditLog.ACAO_CONCILIACAO_DESFEITO, recurso_tipo="movimento",
          recurso_id=mov.id)
    flash("Conciliação desfeita.", "success")
    return redirect(url_for("financeiro.conciliacao"))


# ===================== Fechamento de caixa diário =====================

def _dec(valor) -> Decimal:
    """Parse tolerante de dinheiro do form (aceita '150,50' ou '150.50')."""
    s = (valor or "").strip().replace(".", "").replace(",", ".") \
        if (valor and "," in valor) else (valor or "").strip()
    if not s:
        return Decimal("0.00")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _esperado_por_forma(dia):
    """Receitas PAGAS no dia (fuso BR) somadas por forma de pagamento.
    Retorna dict {forma|'nao_informada': Decimal}."""
    L = LancamentoFinanceiro
    ini = datetime.combine(dia, time.min, tzinfo=_BR_TZ).astimezone(timezone.utc)
    fim = ini + timedelta(days=1)
    rows = db.session.execute(
        select(L.forma_pagamento, func.coalesce(func.sum(L.valor), 0))
        .where(L.status == L.STATUS_PAGO, L.tipo == L.TIPO_RECEITA,
               L.pago_em >= ini, L.pago_em < fim)
        .group_by(L.forma_pagamento)
    ).all()
    return {(forma or "nao_informada"): Decimal(total) for forma, total in rows}


@financeiro_bp.route("/caixa")
@login_required
@recepcao_ou_admin
def caixa():
    """Fechamento de caixa do dia: esperado (receitas pagas por forma) × contado."""
    dia = _parse_ref(request.args.get("dia", ""))
    esperado = _esperado_por_forma(dia)
    esperado_total = sum(esperado.values(), Decimal("0.00"))
    # Formas a exibir: as canônicas + 'nao_informada' se houver receita sem forma.
    formas = list(LancamentoFinanceiro.FORMAS_PAGAMENTO)
    if "nao_informada" in esperado:
        formas.append("nao_informada")

    fechamento = db.session.execute(
        select(FechamentoCaixa).where(FechamentoCaixa.dia == dia)
    ).scalars().first()
    contado = {}
    if fechamento and fechamento.detalhes:
        try:
            det = json.loads(fechamento.detalhes)
            contado = {f: v.get("contado") for f, v in det.items()}
        except (ValueError, AttributeError):
            contado = {}

    hoje = datetime.now(_BR_TZ).date()
    return render_template(
        "financeiro/caixa.html",
        dia=dia, formas=formas, esperado=esperado,
        esperado_total=esperado_total, fechamento=fechamento, contado=contado,
        dia_anterior=(dia - timedelta(days=1)).isoformat(),
        dia_seguinte=(dia + timedelta(days=1)).isoformat(),
        hoje=hoje,
    )


@financeiro_bp.route("/caixa/fechar", methods=["POST"])
@login_required
@recepcao_ou_admin
def caixa_fechar():
    dia = _parse_ref(request.form.get("dia", ""))
    # Esperado é SEMPRE recalculado no servidor (não confia no cliente).
    esperado = _esperado_por_forma(dia)
    formas = set(LancamentoFinanceiro.FORMAS_PAGAMENTO) | set(esperado)
    detalhes = {}
    contado_total = Decimal("0.00")
    esperado_total = Decimal("0.00")
    for f in formas:
        e = esperado.get(f, Decimal("0.00"))
        c = _dec(request.form.get(f"contado_{f}", ""))
        if e == 0 and c == 0:
            continue   # não polui o snapshot com formas zeradas
        detalhes[f] = {"esperado": str(e), "contado": str(c)}
        esperado_total += e
        contado_total += c
    divergencia = contado_total - esperado_total

    fechamento = db.session.execute(
        select(FechamentoCaixa).where(FechamentoCaixa.dia == dia)
    ).scalars().first()
    if fechamento is None:
        fechamento = FechamentoCaixa(dia=dia)
        db.session.add(fechamento)
    fechamento.esperado_total = esperado_total
    fechamento.contado_total = contado_total
    fechamento.divergencia = divergencia
    fechamento.detalhes = json.dumps(detalhes)
    fechamento.observacoes = request.form.get("observacoes", "").strip()[:500] or None
    fechamento.fechado_por_id = current_user.id
    fechamento.fechado_em = datetime.now(timezone.utc)
    try:
        db.session.commit()
    except IntegrityError:
        # Corrida: outro fechamento do mesmo dia entrou (duplo-clique/2 abas).
        db.session.rollback()
        flash("Este caixa acabou de ser fechado. Recarregue a página.", "error")
        return redirect(url_for("financeiro.caixa", dia=dia.isoformat()))
    audit(AuditLog.ACAO_CAIXA_FECHADO, recurso_tipo="caixa",
          recurso_id=fechamento.id,
          detalhes=f"dia={dia.isoformat()} divergencia={divergencia}")
    if divergencia == 0:
        flash("Caixa fechado: bate certinho com o esperado.", "success")
    else:
        flash(f"Caixa fechado com divergência de {divergencia:+.2f}.", "error")
    return redirect(url_for("financeiro.caixa", dia=dia.isoformat()))


@financeiro_bp.route("/caixa/<int:fechamento_id>/reabrir", methods=["POST"])
@login_required
@recepcao_ou_admin
def caixa_reabrir(fechamento_id):
    fechamento = _get_tenant(FechamentoCaixa, fechamento_id)
    if not fechamento:
        flash("Fechamento não encontrado.", "error")
        return redirect(url_for("financeiro.caixa"))
    dia = fechamento.dia
    db.session.delete(fechamento)
    db.session.commit()
    audit(AuditLog.ACAO_CAIXA_REABERTO, recurso_tipo="caixa",
          detalhes=f"dia={dia.isoformat()}")
    flash("Caixa reaberto.", "success")
    return redirect(url_for("financeiro.caixa", dia=dia.isoformat()))
