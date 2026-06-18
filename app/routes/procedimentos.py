"""Cadastro de Itens — catálogo de itens faturáveis (procedimentos/produtos) E
cadastro centralizado de convênios.

O médico marca o item consumido no atendimento; o financeiro puxa o total.
Convênios viram lista controlada (master data) — evita duplicidade/erro de
grafia no texto livre dos cadastros. Gate: recepção ou admin.
"""
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app import db
from app.auth_decorators import recepcao_ou_admin
from app.models import (
    Procedimento, PrecoConvenio, Convenio, ItemAtendimento, AuditLog, Sala,
)
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
@recepcao_ou_admin
def listar():
    procedimentos = db.session.execute(
        select(Procedimento).order_by(Procedimento.ativo.desc(), Procedimento.nome)
    ).scalars().all()
    convenios = db.session.execute(
        select(Convenio).order_by(Convenio.ativo.desc(), Convenio.nome)
    ).scalars().all()
    salas = db.session.execute(
        select(Sala).order_by(Sala.ativo.desc(), Sala.nome)
    ).scalars().all()
    return render_template("procedimentos/listar.html",
                           procedimentos=procedimentos, convenios=convenios,
                           salas=salas)


@procedimentos_bp.route("/adicionar", methods=["POST"])
@login_required
@recepcao_ou_admin
def adicionar():
    """Add unificado: cria um Item faturável OU um Convênio, conforme `tipo`."""
    tipo = request.form.get("tipo", "item").strip()
    nome = request.form.get("nome", "").strip()
    if not nome:
        flash("Informe o nome.", "error")
        return redirect(url_for("procedimentos.listar"))

    if tipo == "convenio":
        existe = db.session.execute(
            select(Convenio).where(Convenio.nome == nome)
        ).scalar_one_or_none()
        if existe:
            flash("Este convênio já está cadastrado.", "error")
            return redirect(url_for("procedimentos.listar"))
        c = Convenio(nome=nome)
        db.session.add(c)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Este convênio já está cadastrado.", "error")
            return redirect(url_for("procedimentos.listar"))
        audit(AuditLog.ACAO_CONVENIO_SALVO, recurso_tipo="convenio",
              recurso_id=c.id, detalhes="criado")
        flash("Convênio cadastrado.", "success")
        return redirect(url_for("procedimentos.listar"))

    if tipo == "sala":
        existe = db.session.execute(
            select(Sala).where(Sala.nome == nome)
        ).scalar_one_or_none()
        if existe:
            flash("Esta sala já está cadastrada.", "error")
            return redirect(url_for("procedimentos.listar"))
        s = Sala(nome=nome[:60])
        db.session.add(s)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Esta sala já está cadastrada.", "error")
            return redirect(url_for("procedimentos.listar"))
        audit(AuditLog.ACAO_SALA_SALVA, recurso_tipo="sala",
              recurso_id=s.id, detalhes="criada")
        flash("Sala cadastrada.", "success")
        return redirect(url_for("procedimentos.listar"))

    # tipo == item (default)
    valor = _parse_valor(request.form.get("valor", ""))
    if valor is None:
        flash("Informe um valor válido para o item.", "error")
        return redirect(url_for("procedimentos.listar"))
    p = Procedimento(nome=nome, valor_padrao=valor)
    db.session.add(p)
    db.session.commit()
    audit(AuditLog.ACAO_PROCEDIMENTO_SALVO, recurso_tipo="procedimento",
          recurso_id=p.id, detalhes="criado")
    flash("Item cadastrado.", "success")
    return redirect(url_for("procedimentos.listar"))


@procedimentos_bp.route("/convenios/<int:convenio_id>/toggle", methods=["POST"])
@login_required
@recepcao_ou_admin
def convenio_toggle(convenio_id):
    c = db.session.get(Convenio, convenio_id)
    cid = clinica_atual()
    if not c or (cid is not None and c.clinica_id != cid):
        flash("Convênio não encontrado.", "error")
        return redirect(url_for("procedimentos.listar"))
    c.ativo = not c.ativo
    db.session.commit()
    audit(AuditLog.ACAO_CONVENIO_SALVO, recurso_tipo="convenio",
          recurso_id=c.id, detalhes=f"ativo={c.ativo}")
    flash("Convênio atualizado.", "success")
    return redirect(url_for("procedimentos.listar"))


@procedimentos_bp.route("/salas/<int:sala_id>/toggle", methods=["POST"])
@login_required
@recepcao_ou_admin
def sala_toggle(sala_id):
    s = db.session.get(Sala, sala_id)
    cid = clinica_atual()
    if not s or (cid is not None and s.clinica_id != cid):
        flash("Sala não encontrada.", "error")
        return redirect(url_for("procedimentos.listar"))
    s.ativo = not s.ativo
    db.session.commit()
    audit(AuditLog.ACAO_SALA_SALVA, recurso_tipo="sala",
          recurso_id=s.id, detalhes=f"ativo={s.ativo}")
    flash("Sala atualizada.", "success")
    return redirect(url_for("procedimentos.listar"))


@procedimentos_bp.route("/novo", methods=["POST"])
@login_required
@recepcao_ou_admin
def novo():
    """Compat: criação de item (mantida pra não quebrar links antigos)."""
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
    flash("Item cadastrado.", "success")
    return redirect(url_for("procedimentos.listar"))


@procedimentos_bp.route("/<int:procedimento_id>", methods=["POST"])
@login_required
@recepcao_ou_admin
def salvar(procedimento_id):
    p = db.session.get(Procedimento, procedimento_id)
    if not p:
        flash("Item não encontrado.", "error")
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
    flash("Item atualizado.", "success")
    return redirect(url_for("procedimentos.listar"))


@procedimentos_bp.route("/<int:procedimento_id>/excluir", methods=["POST"])
@login_required
@recepcao_ou_admin
def excluir(procedimento_id):
    """Exclui um item faturável. Preserva o histórico: os ItemAtendimento já
    consumidos guardam snapshot de nome+valor, então só desvinculamos o
    procedimento (procedimento_id -> NULL) antes de remover. Preços por
    convênio caem por cascade."""
    p = db.session.get(Procedimento, procedimento_id)
    # Guarda de posse explícita (defense-in-depth): além do escopo automático,
    # confirma a clínica — session.get pode devolver do identity map sem
    # reaplicar o critério. Mesmo padrão de excluir_preco.
    cid = clinica_atual()
    if not p or (cid is not None and p.clinica_id != cid):
        flash("Item não encontrado.", "error")
        return redirect(url_for("procedimentos.listar"))
    # Desvincula os snapshots históricos (mantém descricao/valor preservados).
    db.session.execute(
        ItemAtendimento.__table__.update()
        .where(ItemAtendimento.procedimento_id == p.id)
        .values(procedimento_id=None)
    )
    nome = p.nome
    db.session.delete(p)
    db.session.commit()
    audit(AuditLog.ACAO_PROCEDIMENTO_EXCLUIDO, recurso_tipo="procedimento",
          recurso_id=procedimento_id, detalhes=f"excluido:{nome}")
    flash("Item excluído.", "success")
    return redirect(url_for("procedimentos.listar"))


@procedimentos_bp.route("/<int:procedimento_id>/precos", methods=["GET", "POST"])
@login_required
@recepcao_ou_admin
def precos(procedimento_id):
    """Tabela de preços por convênio de um item (upsert por convênio)."""
    p = db.session.get(Procedimento, procedimento_id)
    if not p:
        flash("Item não encontrado.", "error")
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

    convenios = db.session.execute(
        select(Convenio.nome).where(Convenio.ativo.is_(True))
        .order_by(Convenio.nome)
    ).scalars().all()
    return render_template("procedimentos/precos.html", procedimento=p,
                           convenios=convenios)


@procedimentos_bp.route("/precos/<int:preco_id>/excluir", methods=["POST"])
@login_required
@recepcao_ou_admin
def excluir_preco(preco_id):
    pc = db.session.get(PrecoConvenio, preco_id)
    # PrecoConvenio não tem clinica_id próprio: confirma a posse comparando
    # clinica_id do Procedimento pai explicitamente. Não dá pra confiar no
    # escopo automático aqui — session.get() não reaplica with_loader_criteria.
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
