"""CRM — painel de retornos pendentes (Fase 2, diferencial).

Lista pacientes cujo retorno recomendado (Atendimento.retorno_em) está
vencendo/vencido e que ainda NÃO reagendaram (sem consulta futura). Permite
agendar o retorno e disparar lembrete por WhatsApp. Gate: recepcao_ou_admin
(a recepção/gestor faz a retenção; o profissional recomenda no atendimento).
"""
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote

from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import select

from app import db
from app.auth_decorators import recepcao_ou_admin
from app.models import Atendimento, Agendamento

crm_bp = Blueprint("crm", __name__, url_prefix="/crm")


def _wa_url(telefone, texto):
    """Monta link wa.me com o telefone do paciente (BR). None se sem número."""
    if not telefone:
        return None
    digitos = "".join(c for c in telefone if c.isdigit())
    if not digitos:
        return None
    if len(digitos) <= 11:          # sem código do país -> assume Brasil (55)
        digitos = "55" + digitos
    return f"https://wa.me/{digitos}?text={quote(texto)}"


def _pacientes_com_consulta_futura():
    """IDs de pacientes com agendamento futuro não cancelado (já reagendaram)."""
    agora = datetime.now(timezone.utc)
    return set(db.session.execute(
        select(Agendamento.paciente_id).where(
            Agendamento.inicio >= agora,
            Agendamento.status != Agendamento.STATUS_CANCELADO,
        )
    ).scalars())


def _retornos_pendentes(janela_dias: int):
    """Lista de retornos due (<= hoje+janela) de pacientes sem consulta futura.

    Dedup por paciente (mantém o retorno mais antigo). Retorna dicts prontos
    pro template — sem lógica no Jinja.
    """
    hoje = date.today()
    limite = hoje + timedelta(days=janela_dias)
    atendimentos = db.session.execute(
        select(Atendimento)
        .where(Atendimento.retorno_em.is_not(None),
               Atendimento.retorno_em <= limite)
        .order_by(Atendimento.retorno_em)
    ).scalars().all()

    com_futuro = _pacientes_com_consulta_futura()
    linhas, vistos = [], set()
    for a in atendimentos:
        if a.paciente_id in com_futuro or a.paciente_id in vistos:
            continue
        vistos.add(a.paciente_id)
        dias = (a.retorno_em - hoje).days
        primeiro_nome = (a.paciente.nome_completo.split()[0]
                         if a.paciente and a.paciente.nome_completo else "")
        linhas.append({
            "atendimento": a,
            "paciente": a.paciente,
            "profissional": a.profissional,
            "dias": dias,
            "vencido": dias < 0,
            "whatsapp": _wa_url(
                a.paciente.telefone if a.paciente else None,
                f"Olá {primeiro_nome}, aqui é da clínica Nous. "
                f"Chegou a época do seu retorno — podemos agendar?",
            ),
        })
    return linhas


def contar_retornos_pendentes():
    """KPI: nº de retornos já vencidos (retorno_em <= hoje) sem reagendamento."""
    return sum(1 for x in _retornos_pendentes(0))


@crm_bp.route("/retornos")
@login_required
@recepcao_ou_admin
def retornos():
    try:
        janela = int(request.args.get("dias", 30))
    except (TypeError, ValueError):
        janela = 30
    janela = max(0, min(janela, 365))
    linhas = _retornos_pendentes(janela)
    return render_template("crm/retornos.html", linhas=linhas, janela=janela)
