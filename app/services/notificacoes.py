"""Camada de notificacoes — best-effort, nunca derruba o fluxo principal.

Dois canais opcionais:
- E-mail (SMTP via app.services.email) — usado pro link de reset de senha.
- Telegram bot — se o usuario tiver telegram_chat_id e TELEGRAM_BOT_TOKEN
  estiver no ambiente. Util pra lembrete de consulta / OTP.

Toda funcao retorna bool (entregue ou nao) e jamais levanta excecao —
notificacao quebrada nao pode impedir cadastro, login ou agendamento.
"""
import logging
import os

import requests

from app.services.email import enviar_email, smtp_configurado
from app.services.pii import mask_email

logger = logging.getLogger(__name__)

_TELEGRAM_TIMEOUT_SEG = 5
_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def post_telegram_raw(chat_id, texto: str, contexto: str = "") -> bool:
    """Envia texto pra um chat_id. Retorna True se a API respondeu ok."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token or not chat_id:
        return False
    url = _TELEGRAM_API.format(token=token)
    payload = {"chat_id": chat_id, "text": texto, "parse_mode": "HTML"}
    ctx = f" {contexto}" if contexto else ""
    try:
        r = requests.post(url, json=payload, timeout=_TELEGRAM_TIMEOUT_SEG)
        if r.status_code == 200 and r.json().get("ok"):
            logger.info("TELEGRAM_OK%s chat=%s", ctx, chat_id)
            return True
        logger.warning("TELEGRAM_FAIL%s chat=%s status=%s",
                       ctx, chat_id, r.status_code)
    except requests.RequestException as e:
        logger.warning("TELEGRAM_EXC%s chat=%s err=%s", ctx, chat_id, e)
    return False


def enviar_telegram(usuario, texto: str, sensitive: bool = False) -> bool:
    """Envia mensagem pro chat do usuario. sensitive=True nunca loga o texto."""
    chat_id = getattr(usuario, "telegram_chat_id", None)
    if not chat_id:
        return False
    ctx = f"usuario={getattr(usuario, 'id', '?')}"
    if not sensitive:
        logger.debug("TELEGRAM_SEND %s texto=%r", ctx, texto[:80])
    return post_telegram_raw(chat_id, texto, contexto=ctx)


def enviar_link_recuperacao(usuario, link: str) -> bool:
    """Envia o link de redefinicao de senha. Tenta e-mail e Telegram.

    Retorna True se PELO MENOS um canal entregou. Conteudo marcado sensitive
    (o link carrega token de uso unico).
    """
    entregue = False

    if smtp_configurado() and getattr(usuario, "email", None):
        corpo = (
            f"Olá,\n\nRecebemos um pedido para redefinir sua senha.\n"
            f"Use o link abaixo (válido por 1 hora):\n\n{link}\n\n"
            f"Se você não solicitou, ignore este e-mail."
        )
        if enviar_email(usuario.email, "Redefinição de senha", corpo):
            entregue = True
            logger.info("RESET_EMAIL_OK usuario=%s", getattr(usuario, "id", "?"))

    texto = (
        "🔐 <b>Redefinição de senha</b>\n\n"
        f"Toque para criar uma nova senha (válido por 1h):\n{link}"
    )
    if enviar_telegram(usuario, texto, sensitive=True):
        entregue = True

    if not entregue:
        logger.info(
            "RESET_SEM_CANAL usuario=%s email=%s — reset manual pelo admin",
            getattr(usuario, "id", "?"),
            mask_email(getattr(usuario, "email", "") or ""),
        )
    return entregue


def notificar_evento(usuario, titulo: str, detalhes: str = "") -> bool:
    """Notificacao generica de evento (ex: lembrete de consulta) via Telegram."""
    corpo = f"<b>{titulo}</b>"
    if detalhes:
        corpo += f"\n{detalhes}"
    return enviar_telegram(usuario, corpo)