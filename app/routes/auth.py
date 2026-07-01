import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse, urljoin

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    current_app, session,
)
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import select

from app import db, limiter
from app.models import Usuario, AuditLog
from app.services.passwords import hash_senha, check_senha, check_dummy
from app.services.audit import audit
from app.services.pii import mask_email as _mask_email
from app.services.notificacoes import enviar_link_recuperacao
from app.services.email import enviar_email

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)

_RECUPERACAO_SALT = "recuperar-senha"
_RECUPERACAO_TTL_SEG = 3600  # 1 hora

# Lockout por-conta: N falhas seguidas bloqueiam a conta por M minutos.
_MAX_TENTATIVAS = 5
_BLOQUEIO_MIN = 15


def _usuario_por_email(email: str) -> Usuario | None:
    return db.session.execute(
        select(Usuario).where(Usuario.email == email)
    ).scalar_one_or_none()


def _proximo_url_seguro(alvo: str | None) -> str | None:
    """Bloqueia open redirect no ?next= — so aceita mesmo host."""
    if not alvo:
        return None
    ref = urlparse(request.host_url)
    destino = urlparse(urljoin(request.host_url, alvo))
    if destino.scheme in ("http", "https") and destino.netloc == ref.netloc:
        return alvo
    return None


def _client_ip() -> str:
    cf = request.headers.get("CF-Connecting-IP", "").strip()
    if cf:
        return cf
    xff = request.headers.get("X-Forwarded-For", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.remote_addr or "-"


def _token_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def _agora_utc():
    return datetime.now(timezone.utc)


def _as_utc(dt):
    """Normaliza um DateTime que pode vir naive (SQLite) pra aware em UTC."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _alertar_login_novo(usuario, ip):
    """Best-effort: avisa por e-mail quando o login vem de um IP diferente do
    último conhecido. Não bloqueia o login se o e-mail falhar (ou SMTP off)."""
    anterior = usuario.ultimo_login_ip
    if anterior and anterior != ip and usuario.email:
        quando = _agora_utc().strftime("%d/%m/%Y %H:%M UTC")
        corpo = (
            f"Olá, {usuario.nome_responsavel}.\n\n"
            f"Detectamos um acesso à sua conta Nous Clinical em {quando}, "
            f"de um endereço diferente do habitual (IP {ip}).\n\n"
            "Se foi você, pode ignorar este aviso. Se não reconhece, "
            "troque sua senha imediatamente em 'Esqueci a senha'."
        )
        try:
            enviar_email(usuario.email, "Novo acesso à sua conta Nous", corpo)
        except Exception:   # noqa: BLE001
            logger.warning("ALERTA_LOGIN_FALHA", exc_info=True)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"],
               error_message="Muitas tentativas de login. Aguarde 1 minuto.")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        ip = _client_ip()
        usuario = _usuario_por_email(email)

        # Conta travada por brute-force (falhas consecutivas)? Recusa antes de
        # checar a senha. Mensagem clara pro dono legítimo; só afeta conta real.
        if usuario and _as_utc(usuario.bloqueado_ate) \
                and _as_utc(usuario.bloqueado_ate) > _agora_utc():
            logger.warning("LOGIN_BLOQUEADO_TENTATIVA email=%s ip=%s",
                           _mask_email(email), ip)
            flash("Muitas tentativas. Por segurança, esta conta ficou bloqueada "
                  "por alguns minutos. Tente novamente em instantes.", "error")
            return render_template("auth/login.html", email_anterior=email)

        novo_hash = None
        if usuario:
            senha_ok, novo_hash = check_senha(senha, usuario.senha_hash)
        else:
            check_dummy(senha)
            senha_ok = False

        if usuario and senha_ok:
            if not getattr(usuario, "ativo", True):
                logger.warning("LOGIN_BLOQUEADO email=%s motivo=inativo",
                               _mask_email(email))
                flash("Conta desativada. Contate o administrador.", "error")
                return render_template("auth/login.html", email_anterior=email)
            if novo_hash:
                usuario.senha_hash = novo_hash
            # Sucesso: zera contador de falhas e alerta se o IP mudou.
            usuario.tentativas_falhas = 0
            usuario.bloqueado_ate = None
            _alertar_login_novo(usuario, ip)
            usuario.ultimo_login_ip = ip
            db.session.commit()
            session.clear()
            session.permanent = True
            login_user(usuario)
            logger.info("LOGIN_OK usuario=%s tipo=%s ip=%s",
                        usuario.id, usuario.tipo, ip)
            audit(AuditLog.ACAO_LOGIN_OK, usuario_id=usuario.id,
                  detalhes=f"tipo={usuario.tipo}")
            proximo = _proximo_url_seguro(request.args.get("next"))
            return redirect(proximo or url_for("main.dashboard"))

        # Falha: incrementa o contador da conta existente e bloqueia no limite.
        if usuario:
            usuario.tentativas_falhas = (usuario.tentativas_falhas or 0) + 1
            if usuario.tentativas_falhas >= _MAX_TENTATIVAS:
                usuario.bloqueado_ate = _agora_utc() + timedelta(minutes=_BLOQUEIO_MIN)
                usuario.tentativas_falhas = 0
                audit(AuditLog.ACAO_LOGIN_BLOQUEADO, usuario_id=usuario.id,
                      detalhes=f"bloqueio={_BLOQUEIO_MIN}min")
                logger.warning("LOGIN_CONTA_BLOQUEADA email=%s ip=%s",
                               _mask_email(email), ip)
            db.session.commit()

        logger.warning("LOGIN_FAIL email=%s ip=%s existe=%s",
                       _mask_email(email), ip, bool(usuario))
        audit(AuditLog.ACAO_LOGIN_FAIL,
              detalhes=f"email={_mask_email(email)} existe={bool(usuario)}")
        flash("E-mail ou senha incorretos.", "error")
        return render_template("auth/login.html",
                               erro_login=True, email_anterior=email)

    return render_template("auth/login.html")


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    """Logout via POST + CSRF (defende contra <img src=/logout>)."""
    uid = current_user.id
    logout_user()
    session.clear()
    audit(AuditLog.ACAO_LOGOUT, usuario_id=uid)
    return redirect(url_for("auth.login"))


@auth_bp.route("/esqueci-senha", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"],
               error_message="Muitas tentativas recentes. Aguarde 1 hora.")
def esqueci_senha():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        usuario = _usuario_por_email(email) if email else None
        # Nao vaza existencia do e-mail — mensagem identica sempre.
        if usuario:
            token = _token_serializer().dumps(usuario.id, salt=_RECUPERACAO_SALT)
            link = url_for("auth.redefinir_senha", token=token, _external=True)
            enviar_link_recuperacao(usuario, link)
        flash(
            "Se o e-mail existir, enviamos o link de redefinição por e-mail "
            "ou Telegram. Sem esses canais, peça reset ao administrador.",
            "success",
        )
        return redirect(url_for("auth.login"))

    return render_template("auth/esqueci_senha.html")


@auth_bp.route("/redefinir-senha/<token>", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"],
               error_message="Muitas tentativas recentes. Aguarde 1 hora.")
def redefinir_senha(token):
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    try:
        user_id, token_emitido_em = _token_serializer().loads(
            token, salt=_RECUPERACAO_SALT, max_age=_RECUPERACAO_TTL_SEG,
            return_timestamp=True,
        )
    except SignatureExpired:
        flash("Link expirado. Gere um novo em 'Esqueci minha senha'.", "error")
        return redirect(url_for("auth.esqueci_senha"))
    except BadSignature:
        flash("Link inválido.", "error")
        return redirect(url_for("auth.esqueci_senha"))

    usuario = db.session.get(Usuario, user_id)
    if not usuario:
        flash("Usuário não encontrado.", "error")
        return redirect(url_for("auth.esqueci_senha"))

    # Token de uso unico: invalida se senha ja foi trocada apos a emissao.
    if usuario.senha_atualizada_em:
        senha_atualizada = usuario.senha_atualizada_em
        if senha_atualizada.tzinfo is None:
            senha_atualizada = senha_atualizada.replace(tzinfo=timezone.utc)
        emitido = token_emitido_em
        if emitido.tzinfo is None:
            emitido = emitido.replace(tzinfo=timezone.utc)
        if senha_atualizada >= emitido:
            flash("Este link já foi utilizado. Gere um novo se precisar.", "error")
            return redirect(url_for("auth.esqueci_senha"))

    if request.method == "POST":
        senha = request.form.get("senha", "")
        confirmacao = request.form.get("confirmacao", "")
        if len(senha) < 8:
            flash("A senha deve ter pelo menos 8 caracteres.", "error")
            return render_template("auth/redefinir_senha.html",
                                   token=token, erro_senha_curta=True)
        if senha != confirmacao:
            flash("As senhas não conferem.", "error")
            return render_template("auth/redefinir_senha.html",
                                   token=token, erro_match=True)

        usuario.senha_hash = hash_senha(senha)
        usuario.senha_atualizada_em = _agora_utc()
        db.session.commit()
        audit(AuditLog.ACAO_SENHA_REDEFINIDA, usuario_id=usuario.id)
        flash("Senha redefinida com sucesso. Faça login com a nova senha.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/redefinir_senha.html", token=token)