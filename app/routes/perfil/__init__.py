"""Perfil do usuario logado — editar dados basicos + trocar senha."""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from app.services.passwords import hash_senha, check_senha
from datetime import datetime, timezone

perfil_bp = Blueprint("perfil", __name__, url_prefix="/perfil")


@perfil_bp.route("/", methods=["GET", "POST"])
@login_required
def editar():
    if request.method == "POST":
        current_user.nome_responsavel = (
            request.form.get("nome_responsavel", "").strip()
            or current_user.nome_responsavel
        )
        current_user.telefone = request.form.get("telefone", "").strip() or None
        db.session.commit()
        flash("Perfil atualizado.", "success")
        return redirect(url_for("perfil.editar"))
    return render_template("perfil/editar.html")


@perfil_bp.route("/senha", methods=["POST"])
@login_required
def trocar_senha():
    atual = request.form.get("senha_atual", "")
    nova = request.form.get("senha_nova", "")
    confirma = request.form.get("senha_confirma", "")

    ok, _ = check_senha(atual, current_user.senha_hash)
    if not ok:
        flash("Senha atual incorreta.", "error")
        return redirect(url_for("perfil.editar"))
    if len(nova) < 8:
        flash("A nova senha deve ter pelo menos 8 caracteres.", "error")
        return redirect(url_for("perfil.editar"))
    if nova != confirma:
        flash("A confirmação não confere.", "error")
        return redirect(url_for("perfil.editar"))

    current_user.senha_hash = hash_senha(nova)
    current_user.senha_atualizada_em = datetime.now(timezone.utc)
    db.session.commit()
    flash("Senha alterada com sucesso.", "success")
    return redirect(url_for("perfil.editar"))