"""Catálogo de procedimentos/produtos faturáveis (config de preços).

Admin cadastra/edita nome + preço. O médico marca o que foi consumido no
atendimento (flagbox) e o financeiro puxa o total automaticamente. Gate: admin.
"""
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import select

from app import db
from app.auth_decorators import admin_required
from app.models import Procedimento, PrecoConvenio, AuditLog
from app.services.audit import audit
from app.services.tenant import clinica_atual

procedimentos_bp = Blueprint("procedimentos", __name__,
                             url_prefix="/procedimentos")


def _parse_valor(bruto: str):
    """'1.234,56' (BR) ou '1234.56' -> Decimal>=0, ou None se inválido."""
    if bruto is None:
        return None
    s = bruto.strip().replace("R$", "").replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        v = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    if v < 0:
        return None
    return v.quantize(Decimal("0.01"))


@procedimentos_bp.route("/")
@login_required
@admin_required
def listar():
    procedimentos = db.session.execute(
        select(Procedimento).order_by(Procedimento.ativo.desc(), Procedimento.nome)
    ).scalars().all()
    return render_template("procedimentos/listar.html",
                           procedimentos=procedimentos)


@procedimentos_bp.route("/novo", methods=["POST"])
@login_required
@admin_required
def novo():
    nome = request.form.get("nome", "").strip()
    valor = _parse_valor(request.form.get("valor", ""))
    if not nome or valor is None:
        flash("Informe nome e um valor válido.", "error")
        return redirect(url_for("procedimentos.listar"))
    p = Procedimento(nome=nome, valor_padrao=valor)
    db.session.add(p)
    db.session.commit()
    audit(AuditLog.ACAO_PROCEDIMENTO_SALVO, recurso_tipo="procedimento",
          recurso_id=p.id, detalhes="criado")
    flash("Procedimento cadastrado.", "success")
    return redirect(url_for("procedimentos.listar"))


@procedimentos_bp.route("/<int:procedimento_id>", methods=["POST"])
@login_required
@admin_required
def salvar(procedimento_id):
    p = db.session.get(Procedimento, procedimento_id)
    if not p:
        flash("Procedimento não encontrado.", "error")
        return redirect(url_for("procedimentos.listar"))
    nome = request.form.get("nome", "").strip()
    valor = _parse_valor(request.form.get("valor", ""))
    if not nome or valor is None:
        flash("Informe nome e um valor válido.", "error")
        return redirect(url_for("procedimentos.listar"))
    p.nome = nome
    p.valor_padrao = valor
    p.ativo = request.form.get("ativo") == "on"
    db.session.commit()
    audit(AuditLog.ACAO_PROCEDIMENTO_SALVO, recurso_tipo="procedimento",
          recurso_id=p.id, detalhes="editado")
    flash("Procedimento atualizado.", "success")
    return redirect(url_for("procedimentos.listar"))


@procedimentos_bp.route("/<int:procedimento_id>/precos", methods=["GET", "POST"])
@login_required
@admin_required
def precos(procedimento_id):
    """Tabela de preços por convênio de um procedimento (upsert por convênio)."""
    p = db.session.get(Procedimento, procedimento_id)
    if not p:
        flash("Procedimento não encontrado.", "error")
        return redirect(url_for("procedimentos.listar"))

    if request.method == "POST":
        convenio = request.form.get("convenio", "").strip()
        valor = _parse_valor(request.form.get("valor", ""))
        if not convenio or valor is None:
            flash("Informe convênio e um valor válido.", "error")
            return redirect(url_for("procedimentos.precos", procedimento_id=p.id))
        existente = next((x for x in p.precos if x.convenio == convenio), None)
        if existente:
            existente.valor = valor
        else:
            db.session.add(PrecoConvenio(procedimento_id=p.id,
                                         convenio=convenio, valor=valor))
        db.session.commit()
        audit(AuditLog.ACAO_PROCEDIMENTO_SALVO, recurso_tipo="procedimento",
              recurso_id=p.id, detalhes=f"preco_convenio={convenio}")
        flash("Preço por convênio salvo.", "success")
        return redirect(url_for("procedimentos.precos", procedimento_id=p.id))

    return render_template("procedimentos/precos.html", procedimento=p)


@procedimentos_bp.route("/precos/<int:preco_id>/excluir", methods=["POST"])
@login_required
@admin_required
def excluir_preco(preco_id):
    pc = db.session.get(PrecoConvenio, preco_id)
    # PrecoConvenio não tem clinica_id próprio: confirma a posse pelo pai
    # comparando clinica_id explicitamente. Não dá pra confiar no escopo
    # automático aqui — session.get() não reaplica with_loader_criteria.
    proc = db.session.get(Procedimento, pc.procedimento_id) if pc else None
    cid = clinica_atual()
    if not pc or proc is None or (cid is not None and proc.clinica_id != cid):
        flash("Preço não encontrado.", "error")
        return redirect(url_for("procedimentos.listar"))
    proc_id = pc.procedimento_id
    db.session.delete(pc)
    db.session.commit()
    flash("Preço removido.", "success")
    return redirect(url_for("procedimentos.precos", procedimento_id=proc_id))
