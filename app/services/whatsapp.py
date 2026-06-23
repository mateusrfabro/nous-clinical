"""WhatsApp Business (Cloud API) — multi-tenant, inerte por padrão.

Cada clínica conecta seu número/token (ver `WhatsAppConta`); um único webhook
recebe os eventos de todas e roteia pela `phone_number_id` do payload pra clínica
dona (padrão confirmado em OpenBSP/Chatwoot — ver docs/10-whatsapp-integracao.md).

Princípios (iguais ao service de ajuda):
- **Best-effort:** envio e processamento de webhook NUNCA derrubam o request.
- **Sem PII em log:** logamos status/erro, nunca o texto da mensagem nem o número.
- **Inerte:** sem `WHATSAPP_ATIVO` global + conta `ativo`/token, nada sai nem entra.
- **Segredo:** o token fica cifrado em repouso (services/cripto.py).
"""
import hashlib
import hmac
import logging
import re

from flask import current_app
from sqlalchemy import select

from app import db

logger = logging.getLogger(__name__)


def feature_ativa():
    """Módulo ligado na plataforma (flag global). Não checa conta da clínica."""
    return bool(current_app.config.get("WHATSAPP_ATIVO"))


def _so_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def normaliza_br(numero):
    """Telefone -> wa_id internacional só dígitos. Assume Brasil (55) quando
    vier sem código de país. None se não houver dígitos."""
    d = _so_digitos(numero)
    if not d:
        return None
    if d.startswith("55"):
        return d
    if len(d) in (10, 11):     # DDD + número (com/sem 9)
        return "55" + d
    return d


def conta_da_clinica(clinica_id):
    from app.models import WhatsAppConta
    if not clinica_id:
        return None
    return db.session.execute(
        select(WhatsAppConta).filter_by(clinica_id=clinica_id)
    ).scalar_one_or_none()


# ----------------------------------------------------------------------------
# Envio (Cloud API). Meta não tem SDK Python oficial -> HTTP cru via requests.
# ----------------------------------------------------------------------------
def enviar_texto(conta, para_wa_id, texto):
    """Envia uma mensagem de texto. Retorna (ok: bool, info: str).
    `info` = wa_message_id em sucesso, ou um motivo curto em falha. Best-effort."""
    from app.services.cripto import decifrar

    if not (conta and conta.ativo and conta.phone_number_id):
        return False, "conta inativa"
    if not conta.phone_number_id.isdigit():     # entra na URL -> só dígitos
        return False, "phone_number_id inválido"
    token = decifrar(conta.token_cifrado)
    if not token:
        return False, "sem token"
    para = normaliza_br(para_wa_id)
    texto = (texto or "").strip()
    if not (para and texto):
        return False, "destino/texto vazio"

    import requests
    base = current_app.config.get("WHATSAPP_API_BASE",
                                  "https://graph.facebook.com/v21.0")
    url = f"{base}/{conta.phone_number_id}/messages"
    try:
        r = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json={"messaging_product": "whatsapp", "to": para,
                  "type": "text", "text": {"body": texto[:4000]}},
            timeout=15, allow_redirects=False,
        )
        if r.status_code >= 400:
            logger.warning("WA_SEND_FAIL status=%s", r.status_code)
            return False, f"erro {r.status_code}"
        data = r.json()
        wamid = (data.get("messages") or [{}])[0].get("id")
        return True, (wamid or "")
    except Exception:   # noqa: BLE001 — best-effort
        logger.warning("WA_SEND_EXC", exc_info=True)
        return False, "falha de conexão"


# ----------------------------------------------------------------------------
# Webhook (entrada). Handshake GET + eventos POST com assinatura.
# ----------------------------------------------------------------------------
def verificar_handshake(mode, token, challenge):
    """GET de verificação da Meta. Devolve o challenge se o verify_token bater
    (comparação constant-time)."""
    esperado = current_app.config.get("WHATSAPP_VERIFY_TOKEN")
    if mode == "subscribe" and esperado and hmac.compare_digest(token or "", esperado):
        return challenge
    return None


def validar_assinatura(corpo_bytes, header_sig):
    """Valida X-Hub-Signature-256 (HMAC-SHA256 do corpo cru com o App Secret).
    Sem App Secret configurado: aceita SÓ em debug/dev (fail-closed em produção —
    senão qualquer POST não-assinado injetaria mensagens falsas na inbox)."""
    seg = current_app.config.get("WHATSAPP_APP_SECRET")
    if not seg:
        # Aceita sem assinatura só em dev/testes; em produção, fail-closed.
        return bool(current_app.debug or current_app.testing)
    if not header_sig or not header_sig.startswith("sha256="):
        return False
    esperado = hmac.new(seg.encode(), corpo_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, header_sig.split("=", 1)[1])


def _acha_paciente_id(clinica_id, wa_id):
    """Casa o wa_id (número internacional) a um Paciente da clínica pelo telefone.
    Escopo EXPLÍCITO por clinica_id (o webhook roda sem usuário logado -> sem
    escopo automático). Estreita no banco pelos últimos 4 dígitos (LIKE) pra não
    varrer a tabela toda, e compara tolerando o 9º dígito (últimos 8 dígitos).
    Só roda no PRIMEIRO contato de cada número (depois o contato já existe)."""
    from app.models import Paciente
    if not wa_id:
        return None
    ult4 = wa_id[-4:]
    pacientes = db.session.execute(
        select(Paciente.id, Paciente.telefone)
        .filter(Paciente.clinica_id == clinica_id,
                Paciente.telefone.like(f"%{ult4}"))
    ).all()
    for pid, tel in pacientes:
        n = normaliza_br(tel)
        if n and (n == wa_id or n[-8:] == wa_id[-8:]):
            return pid
    return None


def _upsert_contato(clinica_id, wa_id, nome):
    from app.models import WhatsAppContato
    contato = db.session.execute(
        select(WhatsAppContato).filter_by(clinica_id=clinica_id, wa_id=wa_id)
    ).scalar_one_or_none()
    if contato is None:
        contato = WhatsAppContato(clinica_id=clinica_id, wa_id=wa_id, nome=nome)
        contato.paciente_id = _acha_paciente_id(clinica_id, wa_id)
        db.session.add(contato)
        db.session.flush()
    elif nome and not contato.nome:
        contato.nome = nome
    return contato


def _ja_existe_msg(wa_message_id):
    """Dedupe: a Meta reenvia webhooks. Ignora wa_message_id já gravado."""
    if not wa_message_id:
        return False
    from app.models import WhatsAppMensagem
    return db.session.execute(
        select(WhatsAppMensagem.id).filter_by(wa_message_id=wa_message_id).limit(1)
    ).first() is not None


def processar_webhook(payload):
    """Lê o payload da Meta e grava mensagens recebidas / atualiza status de envio.
    Roteia por phone_number_id -> WhatsAppConta -> clínica. Best-effort (commita o
    que der; nunca levanta). Seta clinica_id EXPLÍCITO (sem usuário logado, o escopo
    automático não preenche)."""
    from app.models import (WhatsAppConta, WhatsAppMensagem)
    from app.models import _agora
    try:
        for entry in (payload or {}).get("entry", []):
            for ch in entry.get("changes", []):
                val = ch.get("value", {}) or {}
                pnid = (val.get("metadata") or {}).get("phone_number_id")
                if not pnid:
                    continue
                conta = db.session.execute(
                    select(WhatsAppConta).filter_by(phone_number_id=pnid)
                ).scalar_one_or_none()
                if conta is None:
                    continue
                cid = conta.clinica_id
                nomes = {c.get("wa_id"): (c.get("profile") or {}).get("name")
                         for c in val.get("contacts", [])}

                # Mensagens recebidas (inbound).
                for m in val.get("messages", []):
                    wamid = m.get("id")
                    if _ja_existe_msg(wamid):
                        continue
                    wa_id = m.get("from")
                    if not wa_id:
                        continue
                    tipo = m.get("type")
                    if tipo == "text":
                        texto = (m.get("text") or {}).get("body") or ""
                    else:
                        texto = f"[{tipo or 'mídia'}]"
                    contato = _upsert_contato(cid, wa_id, nomes.get(wa_id))
                    db.session.add(WhatsAppMensagem(
                        clinica_id=cid, contato_id=contato.id,
                        direcao=WhatsAppMensagem.DIRECAO_IN,
                        wa_message_id=wamid, texto=texto))
                    contato.nao_lidas = (contato.nao_lidas or 0) + 1
                    contato.ultima_em = _agora()

                # Status de mensagens enviadas (delivered/read/failed).
                for st in val.get("statuses", []):
                    st_id = st.get("id")
                    if not st_id:          # sem id não há como casar (evita NULL match)
                        continue
                    msg = db.session.execute(
                        select(WhatsAppMensagem).filter_by(wa_message_id=st_id)
                    ).scalar_one_or_none()
                    if msg is not None:
                        msg.status = _STATUS_MAP.get(st.get("status"), msg.status)
        db.session.commit()
    except Exception:   # noqa: BLE001 — best-effort
        try:
            db.session.rollback()
        except Exception:   # noqa: BLE001
            pass
        logger.warning("WA_WEBHOOK_EXC", exc_info=True)


_STATUS_MAP = {
    "sent": "enviada",
    "delivered": "entregue",
    "read": "lida",
    "failed": "falhou",
}
