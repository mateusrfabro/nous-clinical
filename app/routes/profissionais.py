"""Gestao de profissionais (admin). Cria o login (Usuario tipo=profissional)
junto com o registro Profissional."""
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import select

from app import db
from app.auth_decorators import admin_required
from app.models import Usuario, Profissional, AuditLog
from app.services.passwords import hash_senha
from app.services.audit import audit

profissionais_bp = Blueprint("profissionais", __name__,
                             url_prefix="/profissionais")


def _parse_comissao(raw):
    """Texto -> Decimal de comissão clampado em 0..100 (default 0)."""
    s = (raw or "").strip().replace("%", "").replace(",", ".")
    if not s:
        return Decimal("0")
    try:
        v = Decimal(s)
        if not v.is_finite():        # 'nan'/'inf' constroem mas quebram comparação
            return Decimal("0")
    except InvalidOperation:
        return Decimal("0")
    return min(max(v, Decimal("0")), Decimal("100"))


@profissionais_bp.route("/")
@login_required
@admin_required
def listar():
    profissionais = db.session.execute(
        select(Profissional).order_by(Profissional.nome)
    ).scalars().all()
    return render_template("profissionais/listar.html",
                           profissionais=profissionais)


@profissionais_bp.route("/novo", methods=["GET", "POST"])
@login_required
@admin_required
def novo():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        if not (nome and email and len(senha) >= 8):
            flash("Nome, e-mail e senha (mín. 8 caracteres) são obrigatórios.",
                  "error")
            return render_template("profissionais/form.html", form=request.form)

        ja_existe = db.session.execute(
            select(Usuario).where(Usuario.email == email)
        ).scalar_one_or_none()
        if ja_existe:
            flash("Já existe um usuário com esse e-mail.", "error")
            return render_template("profissionais/form.html", form=request.form)

        usuario = Usuario(
            email=email,
            senha_hash=hash_senha(senha),
            nome_responsavel=nome,
            telefone=request.form.get("telefone", "").strip() or None,
            tipo="profissional",
        )
        db.session.add(usuario)
        db.session.flush()

        prof = Profissional(
            usuario_id=usuario.id,
            nome=nome,
            especialidade=request.form.get("especialidade", "").strip() or None,
            registro_conselho=request.form.get("registro_conselho", "").strip()
            or None,
            cor_agenda=request.form.get("cor_agenda", "").strip() or "#43B8A5",
            duracao_padrao_min=request.form.get("duracao_padrao_min", type=int)
            or 30,
            sala=request.form.get("sala", "").strip() or None,
            comissao_percent=_parse_comissao(request.form.get("comissao_percent", "")),
        )
        db.session.add(prof)
        db.session.commit()
        audit(AuditLog.ACAO_PROFISSIONAL_CRIADO, recurso_tipo="profissional",
              recurso_id=prof.id)
        flash("Profissional cadastrado com acesso ao sistema.", "success")
        return redirect(url_for("profissionais.listar"))

    return render_template("profissionais/form.html", form={})


@profissionais_bp.route("/<int:profissional_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def editar(profissional_id):
    prof = db.session.get(Profissional, profissional_id)
    if not prof:
        flash("Profissional não encontrado.", "error")
        return redirect(url_for("profissionais.listar"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Nome é obrigatório.", "error")
            return render_template("profissionais/editar.html", prof=prof)
        prof.nome = nome
        prof.especialidade = request.form.get("especialidade", "").strip() or None
        prof.registro_conselho = request.form.get("registro_conselho", "").strip() or None
        prof.cor_agenda = request.form.get("cor_agenda", "").strip() or prof.cor_agenda
        prof.duracao_padrao_min = (request.form.get("duracao_padrao_min", type=int)
                                   or prof.duracao_padrao_min)
        prof.sala = request.form.get("sala", "").strip() or None
        prof.comissao_percent = _parse_comissao(request.form.get("comissao_percent", ""))
        prof.ativo = bool(request.form.get("ativo"))
        db.session.commit()
        audit(AuditLog.ACAO_PROFISSIONAL_EDITADO, recurso_tipo="profissional",
              recurso_id=prof.id)
        flash("Profissional atualizado.", "success")
        return redirect(url_for("profissionais.listar"))

    return render_template("profissionais/editar.html", prof=prof)