"""Rota do chatbot de ajuda ("Nous Assistente").

A chave da Anthropic fica só no servidor (a chamada é servidor->Anthropic). Gate
de equipe + CSRF + rate-limit. A pergunta NÃO carrega dado de paciente; a auditoria
grava só metadado (papel + tamanho), nunca o texto, pra não criar novo repositório
de PII.
"""
from flask import Blueprint, request, jsonify
from flask_login import login_required, current_user

from app import db, limiter
from app.auth_decorators import equipe_required
from app.models import AuditLog, Clinica
from app.services.ajuda import responder, ia_disponivel
from app.services.audit import audit

ajuda_bp = Blueprint("ajuda", __name__, url_prefix="/ajuda")


@ajuda_bp.route("/chat", methods=["POST"])
@login_required
@equipe_required
@limiter.limit("20 per hour;4 per minute")
def chat():
    if not ia_disponivel():
        return jsonify({"ok": False,
                        "resposta": "O assistente não está ativo nesta clínica."}), 200

    dados = request.get_json(silent=True) or {}
    pergunta = str(dados.get("pergunta", ""))[:2000]
    historico = dados.get("historico")
    if not isinstance(historico, list):
        historico = None

    clinica_nome = None
    if getattr(current_user, "clinica_id", None):
        c = db.session.get(Clinica, current_user.clinica_id)
        clinica_nome = c.nome if c else None

    ok, resposta = responder(pergunta, current_user.tipo, clinica_nome, historico)
    if ok:
        # Só metadado — nunca o texto da pergunta (LGPD).
        audit(AuditLog.ACAO_AJUDA_CONSULTA, recurso_tipo="ajuda",
              detalhes=f"papel={current_user.tipo} len={len(pergunta)}")
    return jsonify({"ok": ok, "resposta": resposta})
