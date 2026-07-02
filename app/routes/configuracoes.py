"""Configurações da clínica (admin): Aparência — white-label (tema + logo);
Fiscal — emissão de NFS-e (config do emitente, gated por NF_ATIVO)."""
import io
import os
import re
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
    send_file, abort,
)
from flask_login import login_required, current_user

from flask import Response
from sqlalchemy import select

from app import db
from app.auth_decorators import admin_required
from app.models import Clinica, AuditLog, ConfigFiscalClinica
from app.services.audit import audit
from app.services.fiscal import nf_disponivel, get_gateway, GatewayError
from app.services.storage import get_storage
from app.services.cores import (
    hex_to_rgb, css_para_cor, cor_de_marca, svg_favicon,
)

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
        # "Última ação vence": escolher um tema remove a cor personalizada que
        # antes sobrescrevia a primária — senão o tema parece "não aplicar".
        tinha_cor = bool(clinica.cor_primaria)
        clinica.cor_primaria = None
        db.session.commit()
        audit(AuditLog.ACAO_CLINICA_STATUS, recurso_tipo="clinica",
              recurso_id=clinica.id, detalhes=f"tema={tema}")
        msg = "Aparência atualizada — recarregue para ver em todo o sistema."
        if tinha_cor:
            msg = ("Tema aplicado (a cor personalizada foi removida) — "
                   "recarregue para ver em todo o sistema.")
        flash(msg, "success")
        return redirect(url_for("configuracoes.aparencia"))

    return render_template("configuracoes/aparencia.html",
                           temas=TEMAS, atual=clinica.tema, clinica=clinica)


def _parse_aliquota(valor):
    """'5,00' / '5.00' / '5' -> Decimal clampado em 0..100; vazio/inválido -> None."""
    s = (valor or "").strip().replace("%", "").replace(",", ".")
    if not s:
        return None
    try:
        v = Decimal(s)
    except InvalidOperation:
        return None
    return min(max(v, Decimal(0)), Decimal(100))


@configuracoes_bp.route("/fiscal", methods=["GET", "POST"])
@login_required
@admin_required
def fiscal():
    """Config de emissão de NFS-e da clínica (dados do emitente). Gated por NF_ATIVO:
    se o módulo está desligado globalmente, a tela nem existe (404)."""
    if not nf_disponivel():
        abort(404)
    clinica = _minha_clinica()
    if not clinica:
        flash("Clínica não encontrada.", "error")
        return redirect(url_for("main.dashboard"))

    cfg = db.session.execute(
        select(ConfigFiscalClinica).where(
            ConfigFiscalClinica.clinica_id == clinica.id)
    ).scalar_one_or_none()

    if request.method == "POST":
        # "Testar conexão" valida as credenciais do gateway (não salva nada).
        if request.form.get("acao") == "testar":
            try:
                get_gateway().ping()
                flash("Conexão com o emissor fiscal OK.", "success")
            except GatewayError as exc:
                flash(f"Falha na conexão: {exc}", "error")
            return redirect(url_for("configuracoes.fiscal"))

        # "Cadastrar emitente" registra a empresa no gateway (não exige certificado).
        if request.form.get("acao") == "cadastrar_emitente":
            if cfg is None:
                flash("Salve a configuração antes de cadastrar o emitente.", "error")
                return redirect(url_for("configuracoes.fiscal"))
            try:
                cfg.gateway_empresa_id = \
                    get_gateway(cfg.gateway).cadastrar_emitente(cfg)
                db.session.commit()
                audit(AuditLog.ACAO_FISCAL_CONFIG, recurso_tipo="config_fiscal",
                      recurso_id=cfg.id, detalhes="emitente_cadastrado")
                flash("Emitente cadastrado no emissor fiscal.", "success")
            except GatewayError as exc:
                flash(f"Falha ao cadastrar o emitente: {exc}", "error")
            return redirect(url_for("configuracoes.fiscal"))

        if cfg is None:
            cfg = ConfigFiscalClinica(clinica_id=clinica.id)
            db.session.add(cfg)

        cfg.cnpj = re.sub(r"\D", "", request.form.get("cnpj", ""))[:14] or None
        cfg.razao_social = request.form.get("razao_social", "").strip()[:160] or None
        cfg.email = request.form.get("email", "").strip()[:160] or None
        cfg.inscricao_municipal = \
            request.form.get("inscricao_municipal", "").strip()[:30] or None
        cfg.logradouro = request.form.get("logradouro", "").strip()[:160] or None
        cfg.numero = request.form.get("numero", "").strip()[:20] or None
        cfg.complemento = request.form.get("complemento", "").strip()[:80] or None
        cfg.bairro = request.form.get("bairro", "").strip()[:80] or None
        cfg.cidade = request.form.get("cidade", "").strip()[:80] or None
        cfg.uf = request.form.get("uf", "").strip().upper()[:2] or None
        cfg.cep = re.sub(r"\D", "", request.form.get("cep", ""))[:8] or None
        cfg.codigo_municipio_ibge = \
            re.sub(r"\D", "", request.form.get("codigo_municipio_ibge", ""))[:7] or None
        regime = request.form.get("regime_tributario", "").strip().lower()
        cfg.regime_tributario = regime if regime in ConfigFiscalClinica.REGIMES else None
        cfg.aliquota_iss = _parse_aliquota(request.form.get("aliquota_iss"))
        cfg.codigo_servico = request.form.get("codigo_servico", "").strip()[:20] or None
        cfg.cnae = re.sub(r"\D", "", request.form.get("cnae", ""))[:10] or None
        cfg.iss_retido_padrao = request.form.get("iss_retido_padrao") == "on"
        cfg.ativo = request.form.get("ativo") == "on"
        db.session.commit()
        audit(AuditLog.ACAO_FISCAL_CONFIG, recurso_tipo="config_fiscal",
              recurso_id=cfg.id, detalhes=f"ativo={cfg.ativo}")
        flash("Configuração fiscal salva.", "success")
        return redirect(url_for("configuracoes.fiscal"))

    return render_template("configuracoes/fiscal.html", cfg=cfg,
                           regimes=ConfigFiscalClinica.REGIMES, clinica=clinica)


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


@configuracoes_bp.route("/favicon.svg")
@login_required
def favicon():
    """Favicon SVG da clínica do usuário (cor de marca + inicial)."""
    cl = _minha_clinica()
    if not cl:
        abort(404)
    return Response(svg_favicon(cl.nome, cor_de_marca(cl)),
                    mimetype="image/svg+xml")


@configuracoes_bp.route("/slug", methods=["POST"])
@login_required
@admin_required
def slug_salvar():
    """Define/edita o identificador público (slug) da clínica — base do portal
    /c/<slug>. Único na plataforma."""
    import re
    clinica = _minha_clinica()
    if not clinica:
        flash("Clínica não encontrada.", "error")
        return redirect(url_for("main.dashboard"))
    bruto = (request.form.get("slug", "") or "").strip().lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", bruto).strip("-")
    if len(slug) < 3:
        flash("Identificador muito curto (mín. 3 letras/números).", "error")
        return redirect(url_for("configuracoes.aparencia"))
    existe = db.session.execute(
        select(Clinica).where(Clinica.slug == slug, Clinica.id != clinica.id)
        .execution_options(ignore_tenant=True)
    ).scalar_one_or_none()
    if existe:
        flash("Esse identificador já está em uso por outra clínica.", "error")
        return redirect(url_for("configuracoes.aparencia"))
    clinica.slug = slug
    db.session.commit()
    flash("Endereço público atualizado.", "success")
    return redirect(url_for("configuracoes.aparencia"))


@configuracoes_bp.route("/agendamento-online", methods=["POST"])
@login_required
@admin_required
def agendamento_toggle():
    """Liga/desliga o agendamento online público da clínica. Desligado por
    padrão: só quando o admin liga é que a clínica fica bookable/enumerável na
    rota pública (/agendar e portal /c/<slug>/agendar)."""
    clinica = _minha_clinica()
    if not clinica:
        flash("Clínica não encontrada.", "error")
        return redirect(url_for("main.dashboard"))
    ativar = request.form.get("ativar") == "1"
    clinica.agendamento_online_ativo = ativar
    db.session.commit()
    audit(AuditLog.ACAO_CLINICA_STATUS, recurso_tipo="clinica",
          recurso_id=clinica.id,
          detalhes=f"agendamento_online={'on' if ativar else 'off'}")
    flash("Agendamento online " + ("ligado." if ativar
          else "desligado."), "success")
    return redirect(url_for("configuracoes.aparencia"))


@configuracoes_bp.route("/qr-agendamento.svg")
@login_required
@admin_required
def qr_agendamento():
    """QR Code (SVG) do link público de agendamento da clínica (/c/<slug>/agendar)."""
    import io
    import segno
    clinica = _minha_clinica()
    if not clinica or not clinica.slug:
        abort(404)
    url = url_for("portal.agendar", slug=clinica.slug, _external=True)
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=6, border=2,
                                    dark="#1e293b", light=None)
    buf.seek(0)
    return send_file(buf, mimetype="image/svg+xml")


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
