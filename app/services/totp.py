"""2FA por TOTP (RFC 6238) — sem dependência externa (usa hmac/hashlib).

O segredo do usuário fica CIFRADO em repouso (services/cripto.py); este módulo
só cuida do algoritmo: gerar o segredo, montar a URI `otpauth://` pro QR, e
validar um código de 6 dígitos com tolerância de clock. Também gera/valida
códigos de RECUPERAÇÃO (uso único), guardados como hash.
"""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from urllib.parse import quote

_DIGITOS = 6
_PERIODO = 30      # segundos por código
_JANELA = 1        # aceita ±1 período (drift de relógio)


def gerar_secret() -> str:
    """Segredo base32 (sem padding) de 20 bytes — padrão dos apps TOTP."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _codigo(secret_b32: str, contador: int) -> str:
    chave = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    # digestmod por NOME ("sha1") — HMAC-SHA1 é o padrão do RFC 6238; passar a
    # string evita referenciar hashlib.sha1 (que o bandit sinaliza como B324).
    h = hmac.new(chave, struct.pack(">Q", contador), "sha1").digest()
    off = h[-1] & 0x0F
    trunc = struct.unpack(">I", h[off:off + 4])[0] & 0x7FFFFFFF
    return str(trunc % (10 ** _DIGITOS)).zfill(_DIGITOS)


def verificar(secret_b32: str, codigo: str, agora: float | None = None) -> bool:
    """True se `codigo` bate no período atual (±janela)."""
    codigo = (codigo or "").strip().replace(" ", "")
    if not (secret_b32 and codigo.isdigit() and len(codigo) == _DIGITOS):
        return False
    t = int((agora if agora is not None else time.time()) // _PERIODO)
    for delta in range(-_JANELA, _JANELA + 1):
        if hmac.compare_digest(_codigo(secret_b32, t + delta), codigo):
            return True
    return False


def uri_otpauth(secret_b32: str, email: str, emissor: str = "Nous Clinical") -> str:
    """URI otpauth:// pro QR (Google Authenticator, Authy, etc.)."""
    label = quote(f"{emissor}:{email}")
    return (f"otpauth://totp/{label}?secret={secret_b32}"
            f"&issuer={quote(emissor)}&digits={_DIGITOS}&period={_PERIODO}")


# ---- Códigos de recuperação (uso único, guardados como hash) ----

def gerar_recuperacao(n: int = 8) -> list[str]:
    """Lista de códigos legíveis (ex.: 'a1b2-c3d4') para o usuário guardar."""
    return ["-".join(secrets.token_hex(2) for _ in range(2)) for _ in range(n)]


def _hash(codigo: str) -> str:
    return hashlib.sha256(codigo.strip().lower().encode()).hexdigest()


def serializar_recuperacao(codigos: list[str]) -> str:
    """Lista de códigos em claro -> JSON de hashes (pra guardar no DB)."""
    return json.dumps([_hash(c) for c in codigos])


def consumir_recuperacao(codigo: str, blob: str | None):
    """Se `codigo` casar um hash não usado, retorna o novo JSON (sem ele);
    senão retorna None. O caller persiste o novo blob (uso único)."""
    if not (codigo and blob):
        return None
    try:
        hashes = json.loads(blob)
    except (ValueError, TypeError):
        return None
    alvo = _hash(codigo)
    for i, h in enumerate(hashes):
        if hmac.compare_digest(h, alvo):
            del hashes[i]
            return json.dumps(hashes)
    return None
