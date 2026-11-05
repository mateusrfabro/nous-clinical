"""Perfil do usuario logado — editar dados basicos + trocar senha + 2FA."""
import io

import segno
from flask import (Blueprint, render_template, redirect, url_for, flash,
                   request, session)
from flask_login import login_required, current_user

from app import db
from app.models import AuditLog
from app.services.passwords import hash_senha, check_senha
from app.services.audit import audit
from app.services.cripto import cifrar
from app.services import totp as totp_svc
from datetime import datetime, timezone

perfil_bp = Blueprint("perfil", __name__, url_prefix="/perfil")

_2FA_PENDING = "2fa_pending_secret"


def _qr_svg(uri):
    """SVG inline do QR (CSP-safe: é markup, não script nem img externa)."""
    buff = io.BytesIO()
    segno.make(uri, error="m").save(buff, kind="svg", scale=4, border=2,
                                    xmldecl=False, svgns=True)
    return buff.getvalue().decode()


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


# ---------------- 2FA (verificação em duas etapas) ----------------

@perfil_bp.route("/2fa")
@login_required
def dois_fatores():
    if current_user.totp_ativado:
        return render_template("perfil/2fa.html", ativado=True)
    # Gera (ou reusa) um segredo PENDENTE na sessão — só vai pro DB ao confirmar.
    secret = session.get(_2FA_PENDING)
    if not secret:
        secret = totp_svc.gerar_secret()
        session[_2FA_PENDING] = secret
    uri = totp_svc.uri_otpauth(secret, current_user.email)
    return render_template("perfil/2fa.html", ativado=False,
                           qr_svg=_qr_svg(uri), secret=secret)


@perfil_bp.route("/2fa/ativar", methods=["POST"])
@login_required
def dois_fatores_ativar():
    secret = session.get(_2FA_PENDING)
    codigo = request.form.get("codigo", "")
    contador = totp_svc.verificar_contador(secret, codigo) if secret else None
    if contador is None:
        flash("Código inválido. Confira o app autenticador e tente de novo.", "error")
        return redirect(url_for("perfil.dois_fatores"))
    current_user.totp_secret = cifrar(secret)
    current_user.totp_ativado = True
    # Anti-replay: o código usado no enrollment não vale como 1º login.
    current_user.totp_ultimo_contador = contador
    codigos = totp_svc.gerar_recuperacao()
    current_user.totp_recovery = totp_svc.serializar_recuperacao(codigos)
    db.session.commit()
    session.pop(_2FA_PENDING, None)
    audit(AuditLog.ACAO_2FA_ATIVADO, usuario_id=current_user.id)
    # Mostra os códigos de recuperação UMA vez (não são recuperáveis depois).
    return render_template("perfil/2fa_recovery.html", codigos=codigos)


@perfil_bp.route("/2fa/desativar", methods=["POST"])
@login_required
def dois_fatores_desativar():
    senha = request.form.get("senha", "")
    ok, _ = check_senha(senha, current_user.senha_hash)
    if not ok:
        flash("Senha incorreta — 2FA não foi desativado.", "error")
        return redirect(url_for("perfil.dois_fatores"))
    current_user.totp_secret = None
    current_user.totp_ativado = False
    current_user.totp_recovery = None
    db.session.commit()
    audit(AuditLog.ACAO_2FA_DESATIVADO, usuario_id=current_user.id)
    flash("Verificação em duas etapas desativada.", "success")
    return redirect(url_for("perfil.dois_fatores"))