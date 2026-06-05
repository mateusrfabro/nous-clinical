"""Gestao de profissionais (admin). Cria o login (Usuario tipo=profissional)
junto com o registro Profissional."""
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
            cor_agenda=request.form.get("cor_agenda", "").strip() or "#2563eb",
            duracao_padrao_min=request.form.get("duracao_padrao_min", type=int)
            or 30,
        )
        db.session.add(prof)
        db.session.commit()
        audit(AuditLog.ACAO_PROFISSIONAL_CRIADO, recurso_tipo="profissional",
              recurso_id=prof.id)
        flash("Profissional cadastrado com acesso ao sistema.", "success")
        return redirect(url_for("profissionais.listar"))

    return render_template("profissionais/form.html", form={})