"""Motor de lembretes de consulta — agnóstico de agendador.

Pode ser disparado por: `flask lembretes` (cron do sistema/PaaS) ou pelo
endpoint protegido POST /tarefas/lembretes (gatilho externo grátis, ex:
cron-job.org / GitHub Actions). Idempotente: marca `lembrete_enviado_em` e
não reenvia.

Canal atual: e-mail (SMTP já existente). WhatsApp automático exige API paga —
fica como link manual até plugarmos um provedor.
"""
import logging
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import current_app

from app import db
from app.models import Agendamento
from app.services.email import enviar_email, smtp_configurado
from app.services.tokens import gerar_token_confirmacao

logger = logging.getLogger(__name__)
_BR = ZoneInfo("America/Sao_Paulo")


def _link_confirmacao(ag):
    base = (current_app.config.get("PUBLIC_BASE_URL") or "").rstrip("/")
    if not base:
        return None
    return f"{base}/agenda/confirmar/{gerar_token_confirmacao(ag.id)}"


def _corpo(ag):
    quando = ag.inicio
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    quando_br = quando.astimezone(_BR).strftime("%d/%m/%Y às %H:%M")
    linhas = [
        f"Olá, {ag.paciente.nome_completo}.",
        "",
        f"Lembrete da sua consulta em {quando_br} "
        f"com {ag.profissional.nome}.",
    ]
    link = _link_confirmacao(ag)
    if link:
        linhas += ["", f"Confirme sua presença: {link}"]
    linhas += ["", "Se precisar remarcar, entre em contato com a clínica."]
    return "\n".join(linhas)


def enviar_lembretes(data_alvo=None):
    """Envia lembretes das consultas do dia-alvo (default: amanhã, fuso BR).

    Retorna dict com a contagem. Best-effort por consulta — uma falha não
    interrompe as demais.
    """
    alvo = data_alvo or (datetime.now(_BR).date() + timedelta(days=1))
    ini = datetime.combine(alvo, time.min, tzinfo=_BR).astimezone(timezone.utc)
    fim = ini + timedelta(days=1)

    ags = db.session.execute(
        db.select(Agendamento).where(
            Agendamento.inicio >= ini, Agendamento.inicio < fim,
            Agendamento.status.in_([Agendamento.STATUS_AGENDADO,
                                    Agendamento.STATUS_CONFIRMADO]),
            Agendamento.lembrete_enviado_em.is_(None),
        )
    ).scalars().all()

    enviados = sem_canal = falhas = 0
    smtp_ok = smtp_configurado()
    agora = datetime.now(timezone.utc)

    for ag in ags:
        email = (ag.paciente.email or "").strip() if ag.paciente else ""
        if not (email and smtp_ok):
            # Sem canal disponível: marca pra não reprocessar todo dia.
            ag.lembrete_enviado_em = agora
            sem_canal += 1
            continue
        ok = enviar_email(email, "Lembrete de consulta", _corpo(ag))
        if ok:
            ag.lembrete_enviado_em = agora
            enviados += 1
        else:
            falhas += 1   # deixa NULL pra tentar de novo no próximo disparo

    db.session.commit()
    resumo = {"alvo": alvo.isoformat(), "total": len(ags),
              "enviados": enviados, "sem_canal": sem_canal, "falhas": falhas}
    logger.info("LEMBRETES %s", resumo)
    return resumo
