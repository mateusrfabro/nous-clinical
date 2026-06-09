"""Portal público POR CLÍNICA (white-label): /c/<slug>.

Cada clínica tem o seu endereço público com a própria marca (logo + tema/cor):
- /c/<slug>          -> tela de login com a identidade da clínica
- /c/<slug>/agendar  -> agendamento online ESCOPADO aos profissionais da clínica
- /c/<slug>/logo     -> logo da clínica (público, brand asset)
- /c/<slug>/tema.css -> CSS da cor de marca livre (público, CSP-safe)

As rotas resolvem a clínica pelo slug, marcam `g.portal_clinica` (que o context
processor usa pra aplicar a identidade nas páginas públicas) e DELEGAM para a
lógica existente de auth/agenda — sem duplicar regra de segurança.
"""
import io

from flask import Blueprint, g, abort, send_file
from sqlalchemy import select

from app import db
from app.models import Clinica
from app.services.storage import get_storage
from app.services.cores import css_para_cor

portal_bp = Blueprint("portal", __name__, url_prefix="/c")


def _clinica_por_slug(slug):
    cl = db.session.execute(
        select(Clinica).where(Clinica.slug == slug, Clinica.ativo.is_(True))
        .execution_options(ignore_tenant=True)
    ).scalar_one_or_none()
    if cl is None:
        abort(404)
    return cl


@portal_bp.route("/<slug>", methods=["GET", "POST"])
def entrar(slug):
    """Login com a marca da clínica. Reusa a view de auth (rate-limit, anti
    timing, anti session-fixation) — só injeta o branding via g.portal_clinica."""
    g.portal_clinica = _clinica_por_slug(slug)
    from app.routes.auth import login as _login
    return _login()


@portal_bp.route("/<slug>/agendar", methods=["GET", "POST"])
def agendar(slug):
    """Agendamento online escopado à clínica do slug (reusa agenda.agendar_online)."""
    g.portal_clinica = _clinica_por_slug(slug)
    from app.routes.agenda import agendar_online as _agendar
    return _agendar()


@portal_bp.route("/<slug>/logo")
def logo(slug):
    """Logo da clínica — brand asset PÚBLICO (aparece no login/portal)."""
    cl = _clinica_por_slug(slug)
    if not cl.logo_key:
        abort(404)
    try:
        dados = get_storage().read(cl.logo_key)
    except FileNotFoundError:
        abort(404)
    return send_file(io.BytesIO(dados), mimetype=cl.logo_mime or "image/png")


@portal_bp.route("/<slug>/tema.css")
def tema_css(slug):
    """CSS da cor de marca livre da clínica — público, servido como text/css."""
    from flask import Response
    cl = _clinica_por_slug(slug)
    css = css_para_cor(cl.cor_primaria) if cl.cor_primaria else ""
    resp = Response(css, mimetype="text/css")
    resp.headers["Cache-Control"] = "no-cache"
    return resp
