from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_caching import Cache
from config import config


def _ip_real_atras_proxy() -> str:
    """Key func do Flask-Limiter ciente de Cloudflare Tunnel / proxy.

    Prioriza CF-Connecting-IP (autoritativo atras de Cloudflare). Fallback:
    remote_addr (ja corrigido por ProxyFix em prod).
    """
    cf = request.headers.get("CF-Connecting-IP", "").strip()
    if cf:
        return cf
    return get_remote_address()


db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Faça login para acessar o sistema."
login_manager.session_protection = "strong"
csrf = CSRFProtect()
migrate = Migrate()
limiter = Limiter(key_func=_ip_real_atras_proxy, default_limits=["200 per hour"])
cache = Cache()


def create_app(config_name="default"):
    app = Flask(__name__)
    app.config.from_object(config[config_name])

    if config_name == "production":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    if config_name == "production" and not app.config.get("SECRET_KEY"):
        raise RuntimeError(
            "SECRET_KEY nao configurada em producao. "
            "Defina no .env ou variavel de ambiente antes de iniciar."
        )

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    from app import models  # noqa: F401
    migrate.init_app(app, db, render_as_batch=True)
    limiter.init_app(app)
    cache.init_app(app)

    # Headers de seguranca (Talisman). style-src SEM 'unsafe-inline'
    # (estilos dinamicos via data-bind.js). force_https ligado so em prod.
    csp = {
        "default-src": "'self'",
        "style-src": ["'self'", "https://fonts.googleapis.com"],
        "script-src": "'self'",
        "img-src": ["'self'", "data:"],
        "font-src": ["'self'", "https://fonts.gstatic.com"],
        "object-src": "'none'",
        "base-uri": "'self'",
        "form-action": "'self'",
        "frame-ancestors": "'none'",
    }
    permissions_policy = {
        "accelerometer":   "()",
        "camera":          "()",
        "geolocation":     "()",
        "gyroscope":       "()",
        "magnetometer":    "()",
        "microphone":      "()",
        "payment":         "()",
        "usb":             "()",
        "interest-cohort": "()",
    }
    Talisman(
        app,
        content_security_policy=csp,
        content_security_policy_nonce_in=None,
        force_https=(config_name == "production"),
        strict_transport_security=(config_name == "production"),
        strict_transport_security_max_age=31536000,
        referrer_policy="strict-origin-when-cross-origin",
        frame_options="DENY",
        session_cookie_secure=(config_name == "production"),
        permissions_policy=permissions_policy,
    )

    from app.services.storage import init_storage
    init_storage(app)

    # Splash banner no boot (logs): versao + migration head + dialect DB.
    if config_name != "testing":
        from app.services.app_info import app_version, migration_head
        with app.app_context():
            try:
                head = migration_head()
                dialect = db.engine.dialect.name
            except Exception:
                head, dialect = "unknown", "unknown"
            app.logger.info(
                "[nous] BOOT version=%s migration_head=%s db=%s env=%s",
                app_version(), head, dialect, config_name,
            )

    # Em testing, o conftest mantem 1 app_context aberto — limpa o cache de
    # user do flask-login antes de cada request pra evitar leak entre clients.
    if config_name == "testing":
        from flask import g as _g

        @app.before_request
        def _reset_login_user_cache():
            if hasattr(_g, "_login_user"):
                delattr(_g, "_login_user")

    # ---- Timeout de sessao por inatividade (LGPD: estacao compartilhada) ----
    @app.before_request
    def _idle_timeout():
        import time as _time
        from flask import session, flash, redirect, url_for
        from flask_login import current_user, logout_user

        if request.endpoint in (None, "static"):
            return
        if not current_user.is_authenticated:
            return
        idle = app.config.get("IDLE_SESSION_LIFETIME")
        agora = _time.time()
        ultima = session.get("_ultima_atividade")
        if idle and ultima and (agora - ultima) > idle:
            logout_user()
            session.clear()
            flash("Sessão expirada por inatividade. Faça login novamente.", "info")
            return redirect(url_for("auth.login"))
        # Renova a janela de inatividade e mantem o TTL absoluto valido.
        session.permanent = True
        session["_ultima_atividade"] = agora

    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.pacientes import pacientes_bp
    from app.routes.agenda import agenda_bp
    from app.routes.profissionais import profissionais_bp
    from app.routes.financeiro import financeiro_bp
    from app.routes.crm import crm_bp
    from app.routes.procedimentos import procedimentos_bp
    from app.routes.relatorios import relatorios_bp
    from app.routes.exames import exames_bp
    from app.routes.perfil import perfil_bp

    # Error handlers amigaveis + sanitizacao de tokens em logs
    import logging as _logging
    import re as _re
    from flask import render_template, request, jsonify
    from flask_login import current_user
    _err_logger = _logging.getLogger("app.errors")

    _TOKEN_PATH_RE = _re.compile(
        r'(/(?:redefinir-senha|uploads)/)([^/?\s"\']+)'
    )

    class _SanitizeTokenFilter(_logging.Filter):
        def filter(self, record):
            try:
                msg = record.getMessage()
            except Exception:
                return True
            if isinstance(msg, str) and "/" in msg:
                novo = _TOKEN_PATH_RE.sub(r"\1<redacted>", msg)
                if novo != msg:
                    record.msg = novo
                    record.args = ()
            return True

    _sanitize_filter = _SanitizeTokenFilter()
    for _name in ("werkzeug", "gunicorn.access", "gunicorn.error"):
        _logging.getLogger(_name).addFilter(_sanitize_filter)

    def _wants_json():
        return (
            request.is_json
            or "application/json" in (request.headers.get("Accept") or "")
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        )

    @app.errorhandler(404)
    def erro_404(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def erro_403(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(400)
    def erro_400(e):
        if _wants_json():
            return jsonify({"erro": "requisicao_invalida"}), 400
        return render_template("errors/400.html"), 400

    @app.errorhandler(413)
    def erro_413(e):
        if _wants_json():
            return jsonify({"erro": "arquivo_muito_grande"}), 413
        return render_template("errors/413.html"), 413

    @app.errorhandler(429)
    def erro_429(e):
        if _wants_json():
            return jsonify({"erro": "muitas_tentativas"}), 429
        return render_template("errors/429.html"), 429

    @app.errorhandler(500)
    def erro_500(e):
        uid = getattr(current_user, "id", None) if current_user else None
        _err_logger.exception(
            "UNHANDLED_500 path=%s method=%s usuario=%s",
            request.path, request.method, uid,
        )
        db.session.rollback()
        return render_template("errors/500.html"), 500

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(pacientes_bp)
    app.register_blueprint(agenda_bp)
    app.register_blueprint(profissionais_bp)
    app.register_blueprint(financeiro_bp)
    app.register_blueprint(crm_bp)
    app.register_blueprint(procedimentos_bp)
    app.register_blueprint(relatorios_bp)
    app.register_blueprint(exames_bp)
    app.register_blueprint(perfil_bp)

    from app.commands import register_commands
    register_commands(app)

    # ---- Context processor + filtros Jinja (genericos, sem dominio) ----

    @app.context_processor
    def _inject_globals():
        numero = app.config.get("WHATSAPP_NUMERO") or ""
        url = f"https://wa.me/{numero}" if numero else ""
        from app.permissions import tem_permissao
        from flask_login import current_user as _cu
        from flask import url_for as _url_for

        def _url_confirmacao(ag):
            from app.services.tokens import gerar_token_confirmacao
            return _url_for("agenda.confirmar_publico",
                            token=gerar_token_confirmacao(ag.id), _external=True)

        return {
            "whatsapp_url": url,
            # Global Jinja: pode("financeiro:ver") -> bool (RBAC, mostra/oculta UI).
            "pode": lambda permissao: tem_permissao(_cu, permissao),
            # Link público de confirmação (WhatsApp) — token assinado.
            "url_confirmacao": _url_confirmacao,
        }

    # Status de agendamento -> label PT-BR + classe de cor.
    STATUS_AGENDAMENTO = {
        "agendado":   ("Agendado", "tag-info"),
        "confirmado": ("Confirmado", "tag-create"),
        "atendido":   ("Atendido", "tag-success"),
        "cancelado":  ("Cancelado", "tag-danger"),
        "faltou":     ("Faltou", "tag-edit"),
    }

    @app.template_filter("status_label")
    def status_label(status):
        label, _ = STATUS_AGENDAMENTO.get((status or "").lower(),
                                          (status or "—", "tag-info"))
        return label

    @app.template_filter("status_class")
    def status_class(status):
        _, cls = STATUS_AGENDAMENTO.get((status or "").lower(), ("", "tag-info"))
        return cls

    # ---- Financeiro: labels PT-BR + classe de tag por status ----
    FIN_STATUS = {
        "pendente":  ("Pendente", "tag-info"),
        "pago":      ("Pago", "tag-success"),
        "cancelado": ("Cancelado", "tag-danger"),
    }
    FORMA_PGTO = {
        "dinheiro":       "Dinheiro",
        "pix":            "Pix",
        "cartao_credito": "Cartão de crédito",
        "cartao_debito":  "Cartão de débito",
        "convenio":       "Convênio",
        "boleto":         "Boleto",
        "transferencia":  "Transferência",
    }
    CATEGORIA_FIN = {
        "consulta":    "Consulta",
        "procedimento": "Procedimento",
        "convenio":    "Convênio",
        "aluguel":     "Aluguel",
        "salario":     "Salário",
        "insumo":      "Insumo",
        "imposto":     "Imposto",
        "outro":       "Outro",
    }

    @app.template_filter("fin_status_label")
    def fin_status_label(status):
        return FIN_STATUS.get((status or "").lower(), (status or "—", ""))[0]

    @app.template_filter("fin_status_class")
    def fin_status_class(status):
        return FIN_STATUS.get((status or "").lower(), ("", "tag-info"))[1]

    @app.template_filter("forma_pgto_label")
    def forma_pgto_label(forma):
        if not forma:
            return "—"
        return FORMA_PGTO.get(forma.lower(), forma)

    @app.template_filter("categoria_label")
    def categoria_label(categoria):
        if not categoria:
            return "—"
        return CATEGORIA_FIN.get(categoria.lower(), categoria.capitalize())

    @app.template_filter("wa_numero")
    def wa_numero(telefone):
        """Telefone -> dígitos com código BR (55) para link wa.me. '' se vazio."""
        if not telefone:
            return ""
        d = "".join(c for c in str(telefone) if c.isdigit())
        if not d:
            return ""
        return d if len(d) > 11 else "55" + d

    @app.template_filter("brl")
    def format_brl(valor):
        if valor is None:
            return "—"
        try:
            v = float(valor)
        except (TypeError, ValueError):
            return str(valor)
        inteiro, decimal = f"{v:.2f}".split(".")
        sinal = "-" if inteiro.startswith("-") else ""
        inteiro = inteiro.lstrip("-")
        with_sep = ""
        for i, ch in enumerate(reversed(inteiro)):
            if i and i % 3 == 0:
                with_sep = "." + with_sep
            with_sep = ch + with_sep
        return f"R$ {sinal}{with_sep},{decimal}"

    # ---- Datas no fuso de Brasilia (DB guarda UTC) ----
    from zoneinfo import ZoneInfo
    _BRASIL_TZ = ZoneInfo("America/Sao_Paulo")

    def _em_brasil(dt):
        from datetime import timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_BRASIL_TZ)

    @app.template_filter("datetime_br")
    def format_datetime_br(data):
        from datetime import datetime as dt
        if data is None:
            return "—"
        if isinstance(data, dt):
            return _em_brasil(data).strftime("%d/%m/%Y às %H:%M")
        try:
            return data.strftime("%d/%m/%Y às %H:%M")
        except AttributeError:
            return "—"

    @app.template_filter("data_br")
    def format_data_br(data):
        from datetime import date, datetime as dt
        if data is None:
            return "—"
        if isinstance(data, dt):
            return _em_brasil(data).strftime("%d/%m/%Y")
        if isinstance(data, date):
            return data.strftime("%d/%m/%Y")
        return "—"

    @app.template_filter("hora_br")
    def format_hora_br(data):
        from datetime import datetime as dt
        if data is None:
            return "—"
        if isinstance(data, dt):
            return _em_brasil(data).strftime("%H:%M")
        try:
            return data.strftime("%H:%M")
        except AttributeError:
            return "—"

    @app.template_filter("idade")
    def format_idade(nascimento):
        """Idade em anos a partir de date de nascimento."""
        from datetime import date
        if not nascimento:
            return "—"
        hoje = date.today()
        anos = hoje.year - nascimento.year - (
            (hoje.month, hoje.day) < (nascimento.month, nascimento.day)
        )
        return f"{anos} anos"

    return app