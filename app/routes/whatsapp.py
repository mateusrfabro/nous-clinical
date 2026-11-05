"""WhatsApp Business (Cloud API) — webhook único + inbox + configuração.

- `/whatsapp/webhook` (GET handshake, POST eventos) — SEM login/CSRF (a Meta chama);
  protegido por verify_token (GET) e assinatura HMAC (POST).
- `/whatsapp/` inbox (lista de conversas), `/whatsapp/<id>` thread + responder —
  gate recepção/admin (atendimento, não é dado clínico).
- `/whatsapp/config` — só admin (gestora) conecta o número/token da clínica.

Inerte: se `WHATSAPP_ATIVO` (global) está off, as telas devolvem 404 (o menu nem
aparece). Ver docs/10-whatsapp-integracao.md.
"""
from flask import (Blueprint, request, render_template, redirect, url_for,
                   flash, abort)
from flask_login import login_required, current_user
from sqlalchemy import select

from app import db, csrf, limiter
from app.auth_decorators import recepcao_ou_admin, admin_required
from app.models import (AuditLog, WhatsAppConta, WhatsAppContato,
                        WhatsAppMensagem, _agora)
from app.services import whatsapp as wa
from app.services.audit import audit
from app.services.cripto import cifrar

whatsapp_bp = Blueprint("whatsapp", __name__, url_prefix="/whatsapp")


# ----------------------------------------------------------------------------
# Webhook (Meta -> nós). Sem login, sem CSRF; validado por token/assinatura.
# ----------------------------------------------------------------------------
@whatsapp_bp.route("/webhook", methods=["GET", "POST"])
@csrf.exempt
def webhook():
    if request.method == "GET":
        challenge = wa.verificar_handshake(
            request.args.get("hub.mode"),
            request.args.get("hub.verify_token"),
            request.args.get("hub.challenge"))
        return (challenge, 200) if challenge is not None else ("forbidden", 403)

    # POST: valida assinatura sobre o CORPO CRU antes de parsear.
    corpo = request.get_data()
    if not wa.validar_assinatura(corpo, request.headers.get("X-Hub-Signature-256")):
        return "bad signature", 403
    wa.processar_webhook(request.get_json(silent=True) or {})
    return "", 200          # 200 sempre (senão a Meta re-tenta e desativa o webhook)


# ----------------------------------------------------------------------------
# Inbox (equipe -> conversas). Gate recepção/admin.
# ----------------------------------------------------------------------------
@whatsapp_bp.route("/")
@login_required
@recepcao_ou_admin
def inbox():
    if not wa.feature_ativa():
        abort(404)
    conta = wa.conta_da_clinica(current_user.clinica_id)
    # Filtro EXPLÍCITO por clínica (defesa em profundidade — não depender só do
    # escopo automático): a inbox é o caminho mais usado, isolamento é crítico.
    contatos = db.session.execute(
        select(WhatsAppContato)
        .filter(WhatsAppContato.clinica_id == current_user.clinica_id)
        .order_by(WhatsAppContato.ultima_em.desc()).limit(100)
    ).scalars().all()
    return render_template("whatsapp/inbox.html", conta=conta, contatos=contatos)


@whatsapp_bp.route("/<int:contato_id>")
@login_required
@recepcao_ou_admin
def conversa(contato_id):
    if not wa.feature_ativa():
        abort(404)
    contato = db.session.get(WhatsAppContato, contato_id)
    if contato is None or contato.clinica_id != current_user.clinica_id:
        abort(404)
    mensagens = db.session.execute(
        select(WhatsAppMensagem).filter_by(contato_id=contato.id)
        .order_by(WhatsAppMensagem.criado_em)
    ).scalars().all()
    if contato.nao_lidas:
        contato.nao_lidas = 0
        db.session.commit()
    conta = wa.conta_da_clinica(current_user.clinica_id)
    return render_template("whatsapp/conversa.html",
                           contato=contato, mensagens=mensagens, conta=conta)


@whatsapp_bp.route("/<int:contato_id>/enviar", methods=["POST"])
@login_required
@recepcao_ou_admin
@limiter.limit("60 per hour;10 per minute",
               key_func=lambda: f"u:{getattr(current_user, 'id', 'anon')}")
@limiter.limit("300 per hour",     # teto por CLÍNICA: o custo das msgs é dela na Meta
               key_func=lambda: f"c:{getattr(current_user, 'clinica_id', 'anon')}")
def enviar(contato_id):
    if not wa.feature_ativa():
        abort(404)
    contato = db.session.get(WhatsAppContato, contato_id)
    if contato is None or contato.clinica_id != current_user.clinica_id:
        abort(404)
    texto = (request.form.get("texto") or "").strip()[:4000]
    if not texto:
        flash("Escreva uma mensagem.", "error")
        return redirect(url_for("whatsapp.conversa", contato_id=contato.id))

    conta = wa.conta_da_clinica(current_user.clinica_id)
    ok, info = wa.enviar_texto(conta, contato.wa_id, texto)
    if ok:
        db.session.add(WhatsAppMensagem(
            clinica_id=contato.clinica_id, contato_id=contato.id,
            direcao=WhatsAppMensagem.DIRECAO_OUT, wa_message_id=(info or None),
            texto=texto, status="enviada", enviado_por_id=current_user.id))
        contato.ultima_em = _agora()
        db.session.commit()
        audit(AuditLog.ACAO_WHATSAPP_ENVIADA, recurso_tipo="whatsapp",
              recurso_id=contato.id, detalhes=f"len={len(texto)}")
    else:
        flash(f"Não consegui enviar ({info}). Confira a conexão do WhatsApp.", "error")
    return redirect(url_for("whatsapp.conversa", contato_id=contato.id))


# ----------------------------------------------------------------------------
# Configuração (gestora -> conecta o número/token). Só admin.
# ----------------------------------------------------------------------------
@whatsapp_bp.route("/config", methods=["GET", "POST"])
@login_required
@admin_required
def config():
    if not wa.feature_ativa():
        abort(404)
    conta = wa.conta_da_clinica(current_user.clinica_id)
    if request.method == "POST":
        pnid = (request.form.get("phone_number_id") or "").strip()[:40]
        if pnid and not pnid.isdigit():
            flash("O Phone Number ID deve conter apenas números.", "error")
            return redirect(url_for("whatsapp.config"))
        if conta is None:
            conta = WhatsAppConta(clinica_id=current_user.clinica_id)
            db.session.add(conta)
        conta.phone_number_id = pnid
        conta.waba_id = (request.form.get("waba_id") or "").strip()[:40] or None
        conta.display_phone = (request.form.get("display_phone") or "").strip()[:20] or None
        conta.nome_exibicao = (request.form.get("nome_exibicao") or "").strip()[:120] or None
        # Token só é trocado se a gestora digitou um novo (campo vem vazio no GET).
        novo_token = (request.form.get("token") or "").strip()
        if novo_token:
            conta.token_cifrado = cifrar(novo_token)
        conta.ativo = request.form.get("ativo") == "on"
        db.session.commit()
        audit(AuditLog.ACAO_WHATSAPP_CONFIG, recurso_tipo="whatsapp",
              recurso_id=conta.id,
              detalhes=f"ativo={conta.ativo} tem_token={bool(conta.token_cifrado)}")
        flash("Conexão do WhatsApp salva.", "sucesso")
        return redirect(url_for("whatsapp.config"))

    webhook_url = url_for("whatsapp.webhook", _external=True)
    return render_template("whatsapp/config.html", conta=conta, webhook_url=webhook_url)
