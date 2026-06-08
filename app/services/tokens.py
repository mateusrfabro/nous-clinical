"""Tokens assinados (itsdangerous) para links públicos sem login.

Usado na confirmação de consulta por WhatsApp: o link carrega um token
assinado com a SECRET_KEY (inforjável e com expiração), nunca o id cru —
elimina IDOR. Mesmo padrão do reset de senha (app/routes/auth.py).
"""
from flask import current_app
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

_SALT_CONFIRMA = "confirma-consulta-v1"
_MAX_AGE = 14 * 24 * 3600   # 14 dias


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def gerar_token_confirmacao(agendamento_id: int) -> str:
    return _serializer().dumps(agendamento_id, salt=_SALT_CONFIRMA)


def ler_token_confirmacao(token: str, max_age: int = _MAX_AGE):
    """Retorna o agendamento_id ou None (assinatura inválida/expirada)."""
    try:
        return _serializer().loads(token, salt=_SALT_CONFIRMA, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
