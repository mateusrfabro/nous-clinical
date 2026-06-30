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
from datetime import timezone
from zoneinfo import ZoneInfo

from flask import current_app
from sqlalchemy import select

from app import db

_BR = ZoneInfo("America/Sao_Paulo")

logger = logging.getLogger(__name__)


def feature_ativa():
    """Módulo ligado na plataforma (flag global). Não checa conta da clínica."""
    return bool(current_app.config.get("WHATSAPP_ATIVO"))


def _so_digitos(valor):
    return re.sub(r"\D", "", valor or "")


def normaliza_br(numero):
    """Telefone -> wa_id internacional só dígitos. Assume Brasil (55) quando
    vier sem código de país. None se inválido (evita mandar pra número-lixo, o
    que marcaria o lembrete como enviado e bloquearia o fallback de e-mail)."""
    d = _so_digitos(numero)
    if len(d) in (10, 11):              # DDD + número (com/sem 9) -> Brasil
        return "55" + d
    if len(d) in (12, 13) and d.startswith("55"):   # já com código do país
        return d
    return None


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


def enviar_template(conta, para_wa_id, template, lang, params):
    """Envia uma mensagem de TEMPLATE (HSM) — único caminho permitido p/ mensagem
    proativa fora da janela de 24h (lembrete). `params` = variáveis do corpo, na
    ordem. Retorna (ok, info=wamid|motivo). Best-effort."""
    from app.services.cripto import decifrar

    if not (conta and conta.ativo and conta.phone_number_id):
        return False, "conta inativa"
    if not conta.phone_number_id.isdigit():
        return False, "phone_number_id inválido"
    token = decifrar(conta.token_cifrado)
    if not token:
        return False, "sem token"
    para = normaliza_br(para_wa_id)
    if not (para and template):
        return False, "destino/template vazio"

    componentes = []
    if params:
        componentes = [{"type": "body", "parameters": [
            {"type": "text", "text": str(p)[:200]} for p in params]}]

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
                  "type": "template",
                  "template": {"name": template, "language": {"code": lang},
                               "components": componentes}},
            timeout=15, allow_redirects=False,
        )
        if r.status_code >= 400:
            logger.warning("WA_TEMPLATE_FAIL status=%s", r.status_code)
            return False, f"erro {r.status_code}"
        data = r.json()
        wamid = (data.get("messages") or [{}])[0].get("id")
        return True, (wamid or "")
    except Exception:   # noqa: BLE001 — best-effort
        logger.warning("WA_TEMPLATE_EXC", exc_info=True)
        return False, "falha de conexão"


def _registrar_saida(conta, wa_id, texto, wamid, paciente_id=None,
                     enviado_por_id=None):
    """Grava uma mensagem OUT na inbox (NÃO commita — quem chama commita)."""
    from app.models import WhatsAppMensagem, _agora
    contato = _upsert_contato(conta.clinica_id, wa_id, None)
    if paciente_id and not contato.paciente_id:
        contato.paciente_id = paciente_id
    db.session.add(WhatsAppMensagem(
        clinica_id=conta.clinica_id, contato_id=contato.id,
        direcao=WhatsAppMensagem.DIRECAO_OUT, wa_message_id=wamid or None,
        texto=texto, status="enviada", enviado_por_id=enviado_por_id))
    contato.ultima_em = _agora()


def enviar_lembrete_whatsapp(ag):
    """Lembrete de UMA consulta via WhatsApp template (proativo, correto). Loga
    a saída na inbox (sem commit). Retorna (ok, info). Inerte/best-effort: só
    age com módulo ativo + conta da clínica ativa + template configurado."""
    if not feature_ativa():
        return False, "modulo inativo"
    conta = conta_da_clinica(ag.clinica_id)
    if not (conta and conta.ativo):
        return False, "conta inativa"
    template = current_app.config.get("WHATSAPP_TEMPLATE_LEMBRETE")
    if not template:
        return False, "sem template"
    lang = current_app.config.get("WHATSAPP_TEMPLATE_LEMBRETE_LANG", "pt_BR")
    pac = ag.paciente
    wa_id = normaliza_br(pac.telefone if pac else None)
    if not wa_id:
        return False, "sem telefone"

    quando = ag.inicio
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    quando_br = quando.astimezone(_BR).strftime("%d/%m às %H:%M")
    primeiro = (pac.nome_completo or "").split()[0] if pac else ""
    prof = ag.profissional.nome if ag.profissional else ""
    ok, info = enviar_template(conta, wa_id, template, lang,
                               [primeiro, quando_br, prof])
    if ok:
        _registrar_saida(conta, wa_id, f"Lembrete de consulta ({quando_br})",
                         info, paciente_id=pac.id if pac else None)
    return ok, info


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
