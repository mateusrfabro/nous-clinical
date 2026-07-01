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
from sqlalchemy.orm import selectinload

from app import db
from app.models import Agendamento
from app.services.email import enviar_email, smtp_configurado
from app.services.tokens import gerar_token_confirmacao
from app.services.whatsapp import enviar_lembrete_whatsapp

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
    pac_nome = ag.paciente.nome_completo if ag.paciente else "paciente"
    prof_nome = ag.profissional.nome if ag.profissional else "seu profissional"
    linhas = [
        f"Olá, {pac_nome}.",
        "",
        f"Lembrete da sua consulta em {quando_br} com {prof_nome}.",
    ]
    link = _link_confirmacao(ag)
    if link:
        linhas += ["", f"Confirme sua presença: {link}"]
    linhas += ["", "Se precisar remarcar, entre em contato com a clínica."]
    return "\n".join(linhas)


def _claim(ag_id, agora):
    """Reserva o lembrete de forma ATÔMICA antes de enviar.

    UPDATE ... WHERE lembrete_enviado_em IS NULL trava a linha: se dois gatilhos
    (cron + POST /tarefas) rodarem juntos, só um casa o WHERE (o outro vê 0
    linhas). Isso impede o paciente receber lembrete em dobro. Retorna True se
    este processo pegou a reserva.
    """
    res = db.session.execute(
        db.update(Agendamento)
        .where(Agendamento.id == ag_id,
               Agendamento.lembrete_enviado_em.is_(None))
        .values(lembrete_enviado_em=agora)
    )
    db.session.commit()
    return res.rowcount == 1


def _release(ag_id):
    """Solta a reserva (volta a NULL) quando o envio falhou de forma
    transitória — assim a próxima rodada tenta de novo."""
    db.session.execute(
        db.update(Agendamento)
        .where(Agendamento.id == ag_id)
        .values(lembrete_enviado_em=None)
    )
    db.session.commit()


def enviar_lembretes(data_alvo=None):
    """Envia lembretes das consultas do dia-alvo (default: amanhã, fuso BR).

    Retorna dict com a contagem. Best-effort por consulta — uma falha não
    interrompe as demais. Cada lembrete é reservado atomicamente (`_claim`)
    antes do envio, então dois gatilhos concorrentes não duplicam a mensagem.
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
        ).options(selectinload(Agendamento.paciente),
                  selectinload(Agendamento.profissional))
    ).scalars().all()

    enviados = por_whatsapp = sem_canal = falhas = pulados = 0
    smtp_ok = smtp_configurado()
    agora = datetime.now(timezone.utc)

    for ag in ags:
        # Monta os dados ANTES de reservar (o commit do _claim expira o objeto).
        email = (ag.paciente.email or "").strip() if ag.paciente else ""
        corpo = _corpo(ag)

        # Reserva atômica: se outro processo já pegou, pula sem enviar.
        if not _claim(ag.id, agora):
            pulados += 1
            continue

        sucesso = False
        canal_indisponivel = False
        try:
            # 1) WhatsApp template (proativo correto) — preferido quando ativo.
            try:
                ok_wa, info_wa = enviar_lembrete_whatsapp(ag)
            except Exception:   # noqa: BLE001
                logger.warning("LEMBRETE_WA_EXC", exc_info=True)
                ok_wa, info_wa = False, "exc"
            if ok_wa:
                por_whatsapp += 1
                sucesso = True
            else:
                # Falha TRANSITÓRIA do WhatsApp (configurado mas a chamada caiu)
                # justifica retry; "inativo/sem template/sem telefone" não.
                wa_transitorio = (info_wa.startswith("erro")
                                  or info_wa == "falha de conexão")
                # 2) E-mail (fallback).
                if email and smtp_ok:
                    if enviar_email(email, "Lembrete de consulta", corpo):
                        enviados += 1
                        sucesso = True
                    else:
                        falhas += 1
                elif wa_transitorio:
                    falhas += 1
                else:
                    # Sem canal disponível: mantém a reserva pra não reprocessar
                    # todo dia.
                    sem_canal += 1
                    canal_indisponivel = True
        except Exception:   # noqa: BLE001
            logger.warning("LEMBRETE_EXC", exc_info=True)
            falhas += 1

        # Só solta a reserva em falha transitória (envio pendente de retry).
        # Sucesso e "sem canal" mantêm o carimbo.
        if not sucesso and not canal_indisponivel:
            _release(ag.id)

    resumo = {"alvo": alvo.isoformat(), "total": len(ags),
              "enviados": enviados, "whatsapp": por_whatsapp,
              "sem_canal": sem_canal, "falhas": falhas, "pulados": pulados}
    logger.info("LEMBRETES %s", resumo)
    return resumo
