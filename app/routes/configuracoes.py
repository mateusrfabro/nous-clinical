"""Configurações da clínica (admin). Por ora: Aparência (white-label / tema)."""
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from app.auth_decorators import admin_required
from app.models import Clinica, AuditLog
from app.services.audit import audit

configuracoes_bp = Blueprint("configuracoes", __name__,
                             url_prefix="/configuracoes")

# (chave do tema, rótulo, descrição curta)
TEMAS = [
    ("teal", "Teal", "Padrão Nous — teal + lilás"),
    ("indigo", "Índigo", "Confiança — índigo + céu"),
    ("violeta", "Violeta", "Sofisticação — violeta + rosé"),
    ("verde", "Verde clínico", "Saúde — esmeralda + azul"),
    ("ambar", "Âmbar", "Acolhimento — âmbar + azul"),
    ("petroleo", "Azul-petróleo", "Serenidade — petróleo + ouro"),
]
_TEMAS_VALIDOS = {k for k, _, _ in TEMAS}


@configuracoes_bp.route("/aparencia", methods=["GET", "POST"])
@login_required
@admin_required
def aparencia():
    clinica = (db.session.get(Clinica, current_user.clinica_id)
               if current_user.clinica_id else None)
    if not clinica:
        flash("Clínica não encontrada.", "error")
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        tema = request.form.get("tema", "").strip()
        if tema not in _TEMAS_VALIDOS:
            flash("Tema inválido.", "error")
            return redirect(url_for("configuracoes.aparencia"))
        clinica.tema = tema
        db.session.commit()
        audit(AuditLog.ACAO_CLINICA_STATUS, recurso_tipo="clinica",
              recurso_id=clinica.id, detalhes=f"tema={tema}")
        flash("Aparência atualizada — recarregue para ver em todo o sistema.",
              "success")
        return redirect(url_for("configuracoes.aparencia"))

    return render_template("configuracoes/aparencia.html",
                           temas=TEMAS, atual=clinica.tema, clinica=clinica)
