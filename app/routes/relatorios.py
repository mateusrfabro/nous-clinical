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

from flask import (
    Blueprint, render_template, request, Response, redirect, url_for, flash,
)
from flask_login import login_required
from sqlalchemy import select, func

from app import db
from app.auth_decorators import admin_required
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


def _agrega(ini, fim, prof_id=None):
    """Calcula todos os indicadores do período [ini, fim) (UTC aware).

    Filtro opcional por profissional (`prof_id`): aplica à agenda direto e ao
    financeiro via a consulta ligada (despesas não se atribuem a um médico, então
    ficam zeradas quando há filtro). Retorna um dict pronto pra render/CSV.
    """
    L = LancamentoFinanceiro
    A = Agendamento
    pago_periodo = (L.status == L.STATUS_PAGO, L.pago_em >= ini, L.pago_em < fim)
    # Filtros opcionais por profissional.
    ag_prof = (A.profissional_id == prof_id,) if prof_id else ()
    rec_prof = ((L.agendamento_id.in_(
        select(A.id).where(A.profissional_id == prof_id)),) if prof_id else ())

    def _soma(*w):
        return db.session.execute(
            select(func.coalesce(func.sum(L.valor), 0)).where(*w)
        ).scalar_one()

    def _conta_status(i, f):
        rows = db.session.execute(
            select(A.status, func.count(A.id))
            .where(A.inicio >= i, A.inicio < f, *ag_prof)
            .group_by(A.status)
        ).all()
        return {s: c for s, c in rows}

    receitas = _soma(*pago_periodo, L.tipo == L.TIPO_RECEITA, *rec_prof)
    # Despesas não são atribuíveis a um profissional -> zeradas sob filtro.
    despesas = (Decimal("0.00") if prof_id
                else _soma(*pago_periodo, L.tipo == L.TIPO_DESPESA))
    saldo = receitas - despesas
    n_receitas = db.session.execute(
        select(func.count(L.id)).where(*pago_periodo, L.tipo == L.TIPO_RECEITA,
                                       *rec_prof)
    ).scalar_one()
    ticket = (receitas / n_receitas) if n_receitas else Decimal("0.00")

    por_status = _conta_status(ini, fim)
    total_ags = sum(por_status.values())
    faltas = por_status.get(A.STATUS_FALTOU, 0)
    atendidos = por_status.get(A.STATUS_ATENDIDO, 0)
    cancelados = por_status.get(A.STATUS_CANCELADO, 0)
    taxa_faltas = (faltas / total_ags * 100) if total_ags else 0.0

    # Novos pacientes cadastrados no período (sob filtro: só os do profissional).
    pac_prof = ((Paciente.id.in_(
        select(A.paciente_id).where(A.profissional_id == prof_id)),)
        if prof_id else ())
    novos_pacientes = db.session.execute(
        select(func.count(Paciente.id))
        .where(Paciente.criado_em >= ini, Paciente.criado_em < fim, *pac_prof)
    ).scalar_one()

    # --- Comparativo com o período anterior de mesma duração ---
    dur = fim - ini
    ini_ant, fim_ant = ini - dur, ini
    pago_ant = (L.status == L.STATUS_PAGO, L.pago_em >= ini_ant,
                L.pago_em < fim_ant)
    receitas_ant = _soma(*pago_ant, L.tipo == L.TIPO_RECEITA, *rec_prof)
    por_status_ant = _conta_status(ini_ant, fim_ant)
    atendidos_ant = por_status_ant.get(A.STATUS_ATENDIDO, 0)
    novos_ant = db.session.execute(
        select(func.count(Paciente.id))
        .where(Paciente.criado_em >= ini_ant, Paciente.criado_em < fim_ant,
               *pac_prof)
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
        .where(*pago_periodo, L.tipo == L.TIPO_RECEITA, *rec_prof)
        .group_by(L.convenio)
        .order_by(func.coalesce(func.sum(L.valor), 0).desc())
    ).all()
    # Dependência financeira (3.6): % de cada convênio sobre a receita total.
    _tot_conv = sum(float(t or 0) for _, t in conv_rows) or 1.0
    por_convenio = [{"convenio": c or "Sem convênio", "total": t,
                     "percent": round(float(t or 0) / _tot_conv * 100, 1)}
                    for c, t in conv_rows]

    # Receita por médico (consultas pagas ligadas a agendamento).
    med_rows = db.session.execute(
        select(Profissional.nome,
               func.coalesce(func.sum(L.valor), 0),
               func.count(L.id))
        .join(A, L.agendamento_id == A.id)
        .join(Profissional, A.profissional_id == Profissional.id)
        .where(*pago_periodo, L.tipo == L.TIPO_RECEITA, *ag_prof)
        .group_by(Profissional.id, Profissional.nome)  # id evita colapsar homônimos
        .order_by(func.coalesce(func.sum(L.valor), 0).desc())
    ).all()
    por_medico = [{"nome": n, "total": t, "qtd": q} for n, t, q in med_rows]

    # Repasse / comissão por profissional (sobre a receita recebida de consultas).
    rep_rows = db.session.execute(
        select(Profissional.nome, Profissional.comissao_percent,
               func.coalesce(func.sum(L.valor), 0))
        .join(A, L.agendamento_id == A.id)
        .join(Profissional, A.profissional_id == Profissional.id)
        .where(*pago_periodo, L.tipo == L.TIPO_RECEITA,
               Profissional.comissao_percent > 0, *ag_prof)
        .group_by(Profissional.id, Profissional.nome,
                  Profissional.comissao_percent)
        .order_by(func.coalesce(func.sum(L.valor), 0).desc())
    ).all()
    repasse, total_repasse = [], Decimal("0.00")
    for nome, pct, total in rep_rows:
        pct = pct or Decimal("0")
        val = (Decimal(str(total or 0)) * pct / Decimal("100")).quantize(Decimal("0.01"))
        total_repasse += val
        repasse.append({"nome": nome, "recebido": total, "percent": pct,
                        "repasse": val})

    # Produtividade / ocupação por profissional (agendamentos do período).
    ocup_rows = db.session.execute(
        select(Profissional.nome, A.status, func.count(A.id))
        .join(Profissional, A.profissional_id == Profissional.id)
        .where(A.inicio >= ini, A.inicio < fim, *ag_prof)
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
        .where(Atendimento.criado_em >= ini, Atendimento.criado_em < fim,
               *((Atendimento.profissional_id == prof_id,) if prof_id else ()))
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
        "repasse": repasse, "total_repasse": total_repasse,
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


def _idade(nascimento, hoje=None):
    """Idade em anos a partir da data de nascimento. None se sem data ou se a
    data for futura (cadastro inválido) — evita idade negativa na tela/CSV."""
    if not nascimento:
        return None
    hoje = hoje or datetime.now(_BR).date()
    if nascimento > hoje:
        return None
    return (hoje.year - nascimento.year
            - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day)))


def _cpf_mascarado(cpf):
    """Mascara o CPF para relatórios analíticos (minimização LGPD): mantém o
    1º bloco e os 2 últimos dígitos (desambigua homônimos sem expor o PII)."""
    if not cpf:
        return ""
    digitos = [c for c in cpf if c.isdigit()]
    if len(digitos) < 11:
        return "***"
    return f"{''.join(digitos[:3])}.***.***-{''.join(digitos[-2:])}"


def _gasto_por_paciente(ini, fim, prof_id=None):
    """Subquery: total gasto + nº de recebimentos por paciente no período.
    Base dos relatórios 3.1 (ticket médio) e 3.4 (faixa etária)."""
    L = LancamentoFinanceiro
    A = Agendamento
    rec_prof = ((L.agendamento_id.in_(
        select(A.id).where(A.profissional_id == prof_id)),) if prof_id else ())
    return (
        select(L.paciente_id.label("pid"),
               func.coalesce(func.sum(L.valor), 0).label("total"),
               func.count(L.id).label("qtd"))
        .where(L.status == L.STATUS_PAGO, L.tipo == L.TIPO_RECEITA,
               L.pago_em >= ini, L.pago_em < fim,
               L.paciente_id.is_not(None), *rec_prof)
        .group_by(L.paciente_id)
        .subquery()
    )


def _clientes_ticket(ini, fim, prof_id=None):
    """3.1 — Clientes e Ticket Médio: por paciente, total gasto, nº de
    consultas pagas e ticket médio por consulta, no período."""
    g = _gasto_por_paciente(ini, fim, prof_id)
    rows = db.session.execute(
        select(Paciente.id, Paciente.nome_completo, Paciente.cpf,
               Paciente.sexo, g.c.total, g.c.qtd)
        .join(g, g.c.pid == Paciente.id)
        .order_by(g.c.total.desc())
    ).all()
    out = []
    for pid, nome, cpf, sexo, total, qtd in rows:
        total = total or Decimal("0.00")
        qtd = qtd or 0
        ticket = (Decimal(str(total)) / qtd).quantize(Decimal("0.01")) if qtd \
            else Decimal("0.00")
        out.append({"id": pid, "nome": nome, "cpf": _cpf_mascarado(cpf),
                    "sexo": sexo, "total": total, "qtd": qtd, "ticket": ticket})
    return out


def _pacientes_por_convenio(convenio=None):
    """3.2 — Pacientes por Convênio: lista a base ativa (nome, CPF, convênio,
    idade), com filtro opcional por convênio. Foto da base, não do período."""
    q = (select(Paciente.id, Paciente.nome_completo, Paciente.cpf,
                Paciente.convenio, Paciente.data_nascimento)
         .where(Paciente.ativo.is_(True)))
    if convenio:
        q = q.where(Paciente.convenio == convenio)
    q = q.order_by(Paciente.convenio.is_(None), Paciente.convenio,
                   Paciente.nome_completo)
    hoje = datetime.now(_BR).date()
    return [{"id": i, "nome": n, "cpf": c, "convenio": conv or "Sem convênio",
             "idade": _idade(nasc, hoje)}
            for i, n, c, conv, nasc in db.session.execute(q).all()]


# Faixas etárias para o relatório 3.4 (rótulo, mín, máx inclusive; máx None=+).
_FAIXAS = [("0–17", 0, 17), ("18–29", 18, 29), ("30–44", 30, 44),
           ("45–59", 45, 59), ("60+", 60, None)]


def _faixa_de(idade):
    if idade is None:
        return "Sem data"
    for rotulo, lo, hi in _FAIXAS:
        if idade >= lo and (hi is None or idade <= hi):
            return rotulo
    return "Sem data"


def _faixa_etaria(ini, fim, prof_id=None):
    """3.4 — Relatório por Faixa Etária: pacientes ativos com idade, sexo e
    total gasto no período; mais um resumo agregado por faixa."""
    g = _gasto_por_paciente(ini, fim, prof_id)
    rows = db.session.execute(
        select(Paciente.id, Paciente.nome_completo, Paciente.cpf,
               Paciente.sexo, Paciente.data_nascimento,
               func.coalesce(g.c.total, 0))
        .join(g, g.c.pid == Paciente.id, isouter=True)
        .where(Paciente.ativo.is_(True))
        .order_by(Paciente.data_nascimento.is_(None), Paciente.data_nascimento)
    ).all()
    hoje = datetime.now(_BR).date()
    pacientes, resumo = [], {}
    for pid, nome, cpf, sexo, nasc, total in rows:
        idade = _idade(nasc, hoje)
        faixa = _faixa_de(idade)
        total = total or Decimal("0.00")
        pacientes.append({"id": pid, "nome": nome, "cpf": _cpf_mascarado(cpf),
                          "sexo": sexo, "idade": idade, "faixa": faixa,
                          "total": total})
        r = resumo.setdefault(faixa, {"qtd": 0, "total": Decimal("0.00")})
        r["qtd"] += 1
        r["total"] += Decimal(str(total))
    ordem = [f[0] for f in _FAIXAS] + ["Sem data"]
    resumo_ord = [{"faixa": f, **resumo[f]} for f in ordem if f in resumo]
    return pacientes, resumo_ord


def _origem_leads():
    """3.5 — Origem de Leads: distribuição da base ativa por origem (como
    conheceu a clínica), com quantidade e % sobre o total. Inteligência
    comercial: de onde vêm os pacientes."""
    rows = db.session.execute(
        select(Paciente.origem, func.count(Paciente.id))
        .where(Paciente.ativo.is_(True))
        .group_by(Paciente.origem)
        .order_by(func.count(Paciente.id).desc())
    ).all()
    total = sum(q for _, q in rows) or 1
    return ([{"origem": o or "Não informado", "qtd": q,
              "percent": round(q / total * 100, 1)} for o, q in rows],
            sum(q for _, q in rows))


def _dre(ini, fim):
    """3.3 — DRE Simplificado: Receita Bruta − Impostos − Custos − Despesas
    = Resultado Operacional. Classifica as despesas pagas por categoria
    (imposto / insumo=custos / demais=despesas operacionais)."""
    L = LancamentoFinanceiro
    pago = (L.status == L.STATUS_PAGO, L.pago_em >= ini, L.pago_em < fim)

    def _soma(*w):
        return db.session.execute(
            select(func.coalesce(func.sum(L.valor), 0)).where(*w)
        ).scalar_one()

    receita = _soma(*pago, L.tipo == L.TIPO_RECEITA)
    impostos = _soma(*pago, L.tipo == L.TIPO_DESPESA, L.categoria == "imposto")
    custos = _soma(*pago, L.tipo == L.TIPO_DESPESA, L.categoria == "insumo")
    desp_total = _soma(*pago, L.tipo == L.TIPO_DESPESA)
    # Despesas operacionais = todas as despesas menos impostos e custos. Como
    # residual, captura também categorias nulas/futuras -> o DRE sempre fecha.
    despesas = Decimal(str(desp_total)) - Decimal(str(impostos)) \
        - Decimal(str(custos))
    resultado = (Decimal(str(receita)) - Decimal(str(desp_total)))
    return {"receita": receita, "impostos": impostos, "custos": custos,
            "despesas": despesas, "resultado": resultado}


# Catálogo de relatórios do seletor (req. do sócio item 2). (chave, rótulo).
RELATORIOS = [
    ("visao_geral", "Visão geral (KPIs + comparativo)"),
    ("faturamento", "Faturamento e receita por médico"),
    ("clientes_ticket", "Clientes e ticket médio"),
    ("pacientes_convenio", "Pacientes por convênio"),
    ("faixa_etaria", "Pacientes por faixa etária"),
    ("origem_leads", "Origem de leads (como conheceu)"),
    ("dependencia_convenio", "Dependência financeira por convênio"),
    ("dre", "DRE simplificado (resultado operacional)"),
    ("produtividade", "Produtividade por profissional"),
    ("evasao", "Pacientes em risco de evasão"),
    ("auditoria", "Trilha de auditoria"),
]
_RELATORIOS_CHAVES = {k for k, _ in RELATORIOS}
# Relatórios cujos dados vêm de _agrega (KPIs financeiros/agenda do período).
_AGREGA_TIPOS = {"visao_geral", "faturamento", "dependencia_convenio",
                 "produtividade"}
# Relatórios que já têm export CSV próprio (formato=csv -> redireciona).
_CSV_ROTA = {
    "faturamento": "relatorios.export_csv",
    "dependencia_convenio": "relatorios.dependencia_csv",
    "clientes_ticket": "relatorios.clientes_csv",
    "pacientes_convenio": "relatorios.convenio_csv",
    "faixa_etaria": "relatorios.faixa_csv",
    "origem_leads": "relatorios.leads_csv",
    "dre": "relatorios.dre_csv",
    "auditoria": "auditoria.export_csv",
}


@relatorios_bp.route("/")
@login_required
@admin_required
def index():
    """Seletor de relatórios (req. do sócio item 2): escolhe UM relatório +
    período + formato e clica em "Gerar". Geração SOB DEMANDA (só calcula em
    ?gerar=1). CSV redireciona pro export do relatório; PDF/Excel = futuro."""
    ini_d, fim_d, ini, fim = _periodo(request.args)
    tipo = request.args.get("tipo", "visao_geral")
    if tipo not in _RELATORIOS_CHAVES:
        tipo = "visao_geral"
    formato = request.args.get("formato", "tela")
    prof_id = request.args.get("profissional_id", type=int)
    convenio_sel = (request.args.get("convenio") or "").strip()
    gerado = request.args.get("gerar") is not None
    profissionais = db.session.execute(
        select(Profissional).where(Profissional.ativo.is_(True))
        .order_by(Profissional.nome)
    ).scalars().all()

    if gerado:
        # Auditoria tem tela própria (rica) — manda pra lá (ou pro CSV dela).
        if tipo == "auditoria":
            if formato == "csv":
                return redirect(url_for("auditoria.export_csv", ini=ini_d, fim=fim_d))
            return redirect(url_for("auditoria.listar", ini=ini_d, fim=fim_d))
        if formato == "csv":
            rota = _CSV_ROTA.get(tipo)
            if rota:
                return redirect(url_for(rota, ini=ini_d, fim=fim_d,
                                        profissional_id=prof_id or None,
                                        convenio=convenio_sel or None))
            flash("Export CSV ainda não disponível para este relatório; "
                  "exibindo em tela.", "info")
        elif formato in ("pdf", "excel"):
            flash("Exportação em PDF/Excel chega em breve; exibindo em tela.",
                  "info")

    contexto = {"ini": ini_d.isoformat(), "fim": fim_d.isoformat(),
                "gerado": gerado, "profissionais": profissionais,
                "prof_id": prof_id, "tipo": tipo, "formato": formato,
                "convenio_sel": convenio_sel, "relatorios": RELATORIOS}
    if gerado:
        if tipo in _AGREGA_TIPOS:
            contexto.update(_agrega(ini, fim, prof_id=prof_id))
        elif tipo == "evasao":
            contexto["evasao"] = _risco_evasao()
        elif tipo == "clientes_ticket":
            contexto["clientes"] = _clientes_ticket(ini, fim, prof_id)
        elif tipo == "pacientes_convenio":
            contexto["pac_conv"] = _pacientes_por_convenio(convenio_sel or None)
        elif tipo == "faixa_etaria":
            contexto["faixas"], contexto["faixa_resumo"] = \
                _faixa_etaria(ini, fim, prof_id)
        elif tipo == "origem_leads":
            contexto["leads"], contexto["leads_total"] = _origem_leads()
        elif tipo == "dre":
            contexto["dre"] = _dre(ini, fim)
    return render_template("relatorios/index.html", **contexto)


@relatorios_bp.route("/export.csv")
@login_required
@admin_required
def export_csv():
    """Exporta os recebimentos (receitas pagas) do período em CSV.

    Acesso a dado financeiro consolidado — auditado (LGPD/governança).
    """
    ini_d, fim_d, ini, fim = _periodo(request.args)
    prof_id = request.args.get("profissional_id", type=int)
    L = LancamentoFinanceiro
    A = Agendamento
    rec_prof = ((L.agendamento_id.in_(
        select(A.id).where(A.profissional_id == prof_id)),) if prof_id else ())
    rows = db.session.execute(
        select(L.pago_em, L.categoria, L.descricao, L.convenio,
               L.forma_pagamento, L.valor)
        .where(L.status == L.STATUS_PAGO, L.tipo == L.TIPO_RECEITA,
               L.pago_em >= ini, L.pago_em < fim, *rec_prof)
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


@relatorios_bp.route("/dependencia.csv")
@login_required
@admin_required
def dependencia_csv():
    """Relatório de Dependência Financeira por Convênio (3.6): quanto cada
    convênio representa da receita do período. Mede o risco de concentração."""
    ini_d, fim_d, ini, fim = _periodo(request.args)
    prof_id = request.args.get("profissional_id", type=int)
    dados = _agrega(ini, fim, prof_id=prof_id)

    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Convênio", "Receita Gerada (R$)", "% da Receita Total"])
    for r in dados["por_convenio"]:
        c = r["convenio"]
        if c and c[0] in ("=", "+", "-", "@", "\t", "\r"):
            c = "'" + c
        valor_br = f"{float(r['total'] or 0):.2f}".replace(".", ",")
        w.writerow([c, valor_br, f"{r['percent']:.1f}".replace(".", ",")])

    audit(AuditLog.ACAO_RELATORIO_EXPORTADO,
          detalhes=f"dependencia_convenio {ini_d}..{fim_d}")
    nome = f"dependencia_convenio_{ini_d}_{fim_d}.csv"
    conteudo = "﻿" + buf.getvalue()
    return Response(
        conteudo, mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


def _csv_safe(v):
    """Neutraliza CSV/formula injection (Excel/Calc)."""
    s = "" if v is None else str(v)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


def _brl_csv(v):
    """Número no formato pt-BR (vírgula decimal) para planilha."""
    return f"{float(v or 0):.2f}".replace(".", ",")


def _csv_response(nome, cabecalho, linhas, audit_detalhe):
    """Monta uma resposta CSV (delimitador ;, BOM p/ Excel) e audita o export."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(cabecalho)
    for linha in linhas:
        w.writerow([_csv_safe(c) for c in linha])
    audit(AuditLog.ACAO_RELATORIO_EXPORTADO, detalhes=audit_detalhe)
    conteudo = "﻿" + buf.getvalue()
    return Response(
        conteudo, mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@relatorios_bp.route("/clientes.csv")
@login_required
@admin_required
def clientes_csv():
    """3.1 — Clientes e ticket médio em CSV."""
    ini_d, fim_d, ini, fim = _periodo(request.args)
    prof_id = request.args.get("profissional_id", type=int)
    dados = _clientes_ticket(ini, fim, prof_id)
    linhas = [[c["nome"], c["cpf"] or "", c["sexo"] or "", _brl_csv(c["total"]),
               c["qtd"], _brl_csv(c["ticket"])] for c in dados]
    return _csv_response(
        f"clientes_ticket_{ini_d}_{fim_d}.csv",
        ["Nome", "CPF", "Sexo", "Valor Total Gasto (R$)",
         "Qtd. Consultas", "Ticket Médio (R$)"],
        linhas, f"clientes_ticket {ini_d}..{fim_d} ({len(linhas)} linhas)")


@relatorios_bp.route("/pacientes_convenio.csv")
@login_required
@admin_required
def convenio_csv():
    """3.2 — Pacientes por convênio em CSV."""
    convenio = (request.args.get("convenio") or "").strip() or None
    dados = _pacientes_por_convenio(convenio)
    linhas = [[p["nome"], p["cpf"] or "", p["convenio"],
               p["idade"] if p["idade"] is not None else ""] for p in dados]
    return _csv_response(
        "pacientes_por_convenio.csv",
        ["Nome", "CPF", "Convênio", "Idade"],
        linhas, f"pacientes_convenio ({convenio or 'todos'}, {len(linhas)})")


@relatorios_bp.route("/faixa_etaria.csv")
@login_required
@admin_required
def faixa_csv():
    """3.4 — Pacientes por faixa etária em CSV."""
    ini_d, fim_d, ini, fim = _periodo(request.args)
    prof_id = request.args.get("profissional_id", type=int)
    pacientes, _ = _faixa_etaria(ini, fim, prof_id)
    linhas = [[p["nome"], p["cpf"] or "", p["sexo"] or "",
               p["idade"] if p["idade"] is not None else "", p["faixa"],
               _brl_csv(p["total"])] for p in pacientes]
    return _csv_response(
        f"faixa_etaria_{ini_d}_{fim_d}.csv",
        ["Nome", "CPF", "Sexo", "Idade", "Faixa", "Valor Total Gasto (R$)"],
        linhas, f"faixa_etaria {ini_d}..{fim_d} ({len(linhas)} linhas)")


@relatorios_bp.route("/leads.csv")
@login_required
@admin_required
def leads_csv():
    """3.5 — Origem de leads em CSV."""
    leads, _ = _origem_leads()
    linhas = [[r["origem"], r["qtd"], f"{r['percent']:.1f}".replace(".", ",")]
              for r in leads]
    return _csv_response(
        "origem_leads.csv",
        ["Origem do Lead", "Qtd. de Pacientes", "% da Base Total"],
        linhas, f"origem_leads ({len(linhas)} origens)")


@relatorios_bp.route("/dre.csv")
@login_required
@admin_required
def dre_csv():
    """3.3 — DRE simplificado em CSV."""
    ini_d, fim_d, ini, fim = _periodo(request.args)
    d = _dre(ini, fim)
    linhas = [
        ["Receita Bruta", _brl_csv(d["receita"])],
        ["(-) Impostos", _brl_csv(d["impostos"])],
        ["(-) Custos", _brl_csv(d["custos"])],
        ["(-) Despesas", _brl_csv(d["despesas"])],
        ["= Resultado Operacional", _brl_csv(d["resultado"])],
    ]
    return _csv_response(
        f"dre_{ini_d}_{fim_d}.csv",
        ["Classificação", "Valor (R$)"],
        linhas, f"dre {ini_d}..{fim_d}")
