"""Cifragem simétrica em repouso (Fernet) para segredos por-tenant.

Hoje guarda o **token de acesso do WhatsApp** de cada clínica (a clínica cola o
token; ele nunca pode ficar em claro no banco nem aparecer em log/UI). A chave de
cifragem vem de `WHATSAPP_ENC_KEY` (uma chave Fernet válida) ou, se vazia, é
DERIVADA do `SECRET_KEY` — assim funciona sem config extra em dev. Trocar o
`SECRET_KEY` invalida os tokens cifrados sob a chave derivada (basta recolar).

Best-effort na leitura: `decifrar` devolve None se o texto não for decifrável
(chave trocada, dado corrompido) em vez de levantar — o caller trata como
"sem token configurado".
"""
import base64
import hashlib
import logging

from flask import current_app

logger = logging.getLogger(__name__)


def _fernet():
    from cryptography.fernet import Fernet
    chave = current_app.config.get("WHATSAPP_ENC_KEY")
    if chave:
        return Fernet(chave.encode() if isinstance(chave, str) else chave)
    # Deriva uma chave Fernet (32 bytes urlsafe-b64) do SECRET_KEY.
    seg = current_app.config["SECRET_KEY"]
    raw = hashlib.sha256(seg.encode() if isinstance(seg, str) else seg).digest()
    return Fernet(base64.urlsafe_b64encode(raw))


def cifrar(texto):
    """str em claro -> str cifrada (ou None se entrada vazia)."""
    if not texto:
        return None
    return _fernet().encrypt(texto.encode()).decode()


def decifrar(token_cifrado):
    """str cifrada -> str em claro (ou None se vazio/indecifrável)."""
    if not token_cifrado:
        return None
    try:
        return _fernet().decrypt(token_cifrado.encode()).decode()
    except Exception:   # noqa: BLE001 — chave trocada / dado inválido = sem token
        logger.warning("CRIPTO: token nao pode ser decifrado (chave trocada?)")
        return None
