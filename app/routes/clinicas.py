"""Gestão de clínicas (tenants) — apenas superadmin da plataforma.

O superadmin cria cada clínica junto com o login admin dela; não há
auto-cadastro público. O superadmin é cross-tenant (sem escopo), então
enxerga e conta todas as clínicas.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app import db
from app.auth_decorators import superadmin_required
from app.models import Clinica, Usuario, Paciente, AuditLog
from app.services.passwords import hash_senha
from app.services.audit import audit

clinicas_bp = Blueprint("clinicas", __name__, url_prefix="/clinicas")


@clinicas_bp.route("/")
@login_required
@superadmin_required
def listar():
    clinicas = db.session.execute(
        select(Clinica).order_by(Clinica.nome)
    ).scalars().all()
    # Contagens por clínica (usuários e pacientes) — superadmin vê tudo.
    n_users = dict(db.session.execute(
        select(Usuario.clinica_id, func.count(Usuario.id)).group_by(Usuario.clinica_id)
    ).all())
    n_pacientes = dict(db.session.execute(
        select(Paciente.clinica_id, func.count(Paciente.id)).group_by(Paciente.clinica_id)
    ).all())
    return render_template("clinicas/listar.html", clinicas=clinicas,
                           n_users=n_users, n_pacientes=n_pacientes)


@clinicas_bp.route("/nova", methods=["GET", "POST"])
@login_required
@superadmin_required
def nova():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        slug = request.form.get("slug", "").strip().lower() or None
        admin_nome = request.form.get("admin_nome", "").strip()
        admin_email = request.form.get("admin_email", "").strip().lower()
        senha = request.form.get("senha", "")

        if not (nome and admin_nome and admin_email and len(senha) >= 8):
            flash("Preencha nome da clínica, nome/e-mail do admin e senha "
                  "(mín. 8 caracteres).", "error")
            return render_template("clinicas/form.html", form=request.form)

        if db.session.execute(
            select(Usuario).where(Usuario.email == admin_email)
        ).scalar_one_or_none():
            flash("Já existe um usuário com esse e-mail.", "error")
            return render_template("clinicas/form.html", form=request.form)

        clinica = Clinica(nome=nome, slug=slug)
        db.session.add(clinica)
        db.session.flush()

        admin = Usuario(
            email=admin_email, senha_hash=hash_senha(senha),
            nome_responsavel=admin_nome, tipo="admin", clinica_id=clinica.id)
        db.session.add(admin)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Não foi possível criar (slug ou e-mail já em uso).", "error")
            return render_template("clinicas/form.html", form=request.form)

        audit(AuditLog.ACAO_CLINICA_CRIADA, recurso_tipo="clinica",
              recurso_id=clinica.id)
        flash(f"Clínica '{nome}' criada com o admin {admin_email}.", "success")
        return redirect(url_for("clinicas.listar"))

    return render_template("clinicas/form.html", form={})


@clinicas_bp.route("/<int:clinica_id>/toggle", methods=["POST"])
@login_required
@superadmin_required
def toggle(clinica_id):
    clinica = db.session.get(Clinica, clinica_id)
    if not clinica:
        flash("Clínica não encontrada.", "error")
        return redirect(url_for("clinicas.listar"))
    clinica.ativo = not clinica.ativo
    db.session.commit()
    audit(AuditLog.ACAO_CLINICA_STATUS, recurso_tipo="clinica",
          recurso_id=clinica.id, detalhes=f"ativo={clinica.ativo}")
    flash("Status da clínica atualizado.", "success")
    return redirect(url_for("clinicas.listar"))
