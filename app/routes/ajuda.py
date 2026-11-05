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
from app.services.ajuda import responder, ia_disponivel, buscar_local
from app.services.audit import audit

ajuda_bp = Blueprint("ajuda", __name__, url_prefix="/ajuda")


def _chave_rate_limit():
    """Limita por USUÁRIO (não por IP) — numa clínica a equipe sai pelo mesmo IP
    público; o vetor de custo de API é o usuário logado. Cai pro IP se anônimo."""
    return f"u:{current_user.id}" if getattr(current_user, "id", None) \
        else (request.remote_addr or "anon")


@ajuda_bp.route("/buscar", methods=["POST"])
@login_required
@equipe_required
@limiter.limit("120 per hour", key_func=_chave_rate_limit)
def buscar():
    """Suporte de CUSTO ZERO: responde buscando na base de ajuda local (docs/ajuda/),
    sem nenhuma chamada de API. É o que o widget usa por padrão."""
    dados = request.get_json(silent=True) or {}
    pergunta = str(dados.get("pergunta", ""))[:500]
    ok, resposta, fonte = buscar_local(pergunta, current_user.tipo)
    return jsonify({"ok": ok, "resposta": resposta, "fonte": fonte})


@ajuda_bp.route("/chat", methods=["POST"])
@login_required
@equipe_required
@limiter.limit("20 per hour;4 per minute", key_func=_chave_rate_limit)
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
