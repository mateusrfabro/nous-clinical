"""Configurações da clínica (admin): Aparência — white-label (tema + logo)."""
import io
import os

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    send_file, abort,
)
from flask_login import login_required, current_user

from flask import Response

from app import db
from app.auth_decorators import admin_required
from app.models import Clinica, AuditLog
from app.services.audit import audit
from app.services.storage import get_storage
from app.services.cores import hex_to_rgb, css_para_cor

configuracoes_bp = Blueprint("configuracoes", __name__,
                             url_prefix="/configuracoes")

# Logo: só raster (NUNCA SVG — risco de XSS). content-type vem da extensão
# validada, nunca do mimetype enviado pelo cliente.
_LOGO_EXT_MIME = {".png": "image/png", ".jpg": "image/jpeg",
                  ".jpeg": "image/jpeg", ".webp": "image/webp"}


def _minha_clinica():
    return (db.session.get(Clinica, current_user.clinica_id)
            if current_user.clinica_id else None)

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
    clinica = _minha_clinica()
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


@configuracoes_bp.route("/logo", methods=["POST"])
@login_required
@admin_required
def logo_upload():
    clinica = _minha_clinica()
    if not clinica:
        flash("Clínica não encontrada.", "error")
        return redirect(url_for("main.dashboard"))
    file = request.files.get("logo")
    if not file or not file.filename:
        flash("Selecione um arquivo de imagem.", "error")
        return redirect(url_for("configuracoes.aparencia"))
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in _LOGO_EXT_MIME:
        flash("Formato não suportado. Use PNG, JPG ou WEBP.", "error")
        return redirect(url_for("configuracoes.aparencia"))

    antiga = clinica.logo_key
    key = get_storage().save(file, subdir="logos", original_name=file.filename)
    clinica.logo_key = key
    clinica.logo_mime = _LOGO_EXT_MIME[ext]
    db.session.commit()
    if antiga:                       # remove a logo anterior do storage
        get_storage().delete(antiga)
    audit(AuditLog.ACAO_CLINICA_STATUS, recurso_tipo="clinica",
          recurso_id=clinica.id, detalhes="logo_atualizada")
    flash("Logo atualizada.", "success")
    return redirect(url_for("configuracoes.aparencia"))


@configuracoes_bp.route("/logo/remover", methods=["POST"])
@login_required
@admin_required
def logo_remover():
    clinica = _minha_clinica()
    if clinica and clinica.logo_key:
        key = clinica.logo_key
        clinica.logo_key = None
        clinica.logo_mime = None
        db.session.commit()
        get_storage().delete(key)
        flash("Logo removida.", "success")
    return redirect(url_for("configuracoes.aparencia"))


@configuracoes_bp.route("/cor", methods=["POST"])
@login_required
@admin_required
def cor_salvar():
    """Salva a cor de marca livre (v2b). Sobrescreve o tema na primária."""
    clinica = _minha_clinica()
    if not clinica:
        flash("Clínica não encontrada.", "error")
        return redirect(url_for("main.dashboard"))
    cor = (request.form.get("cor", "") or "").strip()
    if hex_to_rgb(cor) is None:
        flash("Cor inválida.", "error")
        return redirect(url_for("configuracoes.aparencia"))
    clinica.cor_primaria = cor.lower()
    db.session.commit()
    audit(AuditLog.ACAO_CLINICA_STATUS, recurso_tipo="clinica",
          recurso_id=clinica.id, detalhes=f"cor={cor.lower()}")
    flash("Cor de marca atualizada — recarregue para ver em todo o sistema.",
          "success")
    return redirect(url_for("configuracoes.aparencia"))


@configuracoes_bp.route("/cor/remover", methods=["POST"])
@login_required
@admin_required
def cor_remover():
    clinica = _minha_clinica()
    if clinica and clinica.cor_primaria:
        clinica.cor_primaria = None
        db.session.commit()
        flash("Cor personalizada removida — voltou ao tema.", "success")
    return redirect(url_for("configuracoes.aparencia"))


@configuracoes_bp.route("/tema.css")
@login_required
def tema_css():
    """CSS por clínica (cor de marca livre). Servido como text/css de 'self'
    -> CSP-safe. Vazio se a clínica não tem cor personalizada."""
    clinica = _minha_clinica()
    css = css_para_cor(clinica.cor_primaria) if (clinica and clinica.cor_primaria) else ""
    resp = Response(css, mimetype="text/css")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@configuracoes_bp.route("/logo/<int:clinica_id>")
@login_required
def logo_servir(clinica_id):
    """Serve a logo de uma clínica (brand asset, não-sensível). Acesso: a
    própria clínica ou superadmin. content-type confiável (da extensão)."""
    if not (current_user.is_superadmin or current_user.clinica_id == clinica_id):
        abort(403)
    clinica = db.session.get(Clinica, clinica_id)
    if not clinica or not clinica.logo_key:
        abort(404)
    try:
        dados = get_storage().read(clinica.logo_key)
    except FileNotFoundError:
        abort(404)
    return send_file(io.BytesIO(dados),
                     mimetype=clinica.logo_mime or "image/png")
