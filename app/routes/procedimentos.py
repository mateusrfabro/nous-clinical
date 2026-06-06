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
from app.models import Procedimento, AuditLog
from app.services.audit import audit

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
