"""CRM — painel de retornos pendentes (Fase 2, diferencial).

Lista pacientes cujo retorno recomendado (Atendimento.retorno_em) está
vencendo/vencido e que ainda NÃO reagendaram (sem consulta futura). Permite
agendar o retorno e disparar lembrete por WhatsApp. Gate: recepcao_ou_admin
(a recepção/gestor faz a retenção; o profissional recomenda no atendimento).
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from urllib.parse import quote

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, abort,
)
from flask_login import login_required
from sqlalchemy import select

from app import db
from app.auth_decorators import recepcao_ou_admin
from app.models import Atendimento, Agendamento, Paciente, AuditLog
from app.services.audit import audit

crm_bp = Blueprint("crm", __name__, url_prefix="/crm")
_BR_TZ = ZoneInfo("America/Sao_Paulo")


def _idade(nascimento, hoje):
    """Idade em anos. None se sem data ou se a data for futura (inválida)."""
    if not nascimento or nascimento > hoje:
        return None
    return (hoje.year - nascimento.year
            - ((hoje.month, hoje.day) < (nascimento.month, nascimento.day)))


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
    """Retornos due (<= hoje+janela) considerando só o ÚLTIMO atendimento.

    Regra (sócio): o paciente perde a flag toda vez que se consulta — o médico
    precisa marcar um novo retorno pra ele voltar ao CRM. Logo, olhamos apenas
    o atendimento mais recente de cada paciente: se ele não tem retorno_em (ou
    já está fora da janela, ou o paciente já reagendou), não aparece.
    """
    hoje = datetime.now(_BR_TZ).date()   # data BR (container em UTC)
    limite = hoje + timedelta(days=janela_dias)

    # Último atendimento por paciente (mais recente; id desempata de forma
    # determinística). Ignora atendimento "vazio" (ex: registro criado só pra
    # anexar exame) — não conta como consulta nem limpa um retorno legítimo.
    todos = db.session.execute(
        select(Atendimento).order_by(
            Atendimento.criado_em.desc(), Atendimento.id.desc())
    ).scalars().all()
    ultimo_por_paciente = {}
    for a in todos:
        if not (a.queixa or a.evolucao or a.prescricao or a.retorno_em):
            continue
        ultimo_por_paciente.setdefault(a.paciente_id, a)

    com_futuro = _pacientes_com_consulta_futura()
    linhas = []
    for a in ultimo_por_paciente.values():
        if a.retorno_em is None or a.retorno_em > limite:
            continue
        if a.paciente_id in com_futuro:
            continue
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
    linhas.sort(key=lambda x: x["atendimento"].retorno_em)
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


def _msg_aniversario(primeiro_nome):
    """Mensagem padrão de felicitação (editável pela recepção no WhatsApp)."""
    saudacao = f"Olá {primeiro_nome}! " if primeiro_nome else "Olá! "
    return (f"{saudacao}🎉 A equipe da clínica Nous passa para desejar um "
            "feliz aniversário e muita saúde! Conte com a gente.")


def _aniversariantes_do_dia():
    """Pacientes ativos que fazem aniversário hoje (fuso BR). Filtra em Python
    por (mês, dia) — portável entre SQLite (dev) e Postgres (prod)."""
    hoje = datetime.now(_BR_TZ).date()
    pacientes = db.session.execute(
        select(Paciente).where(
            Paciente.ativo.is_(True),
            Paciente.data_nascimento.is_not(None))
    ).scalars().all()
    linhas = []
    for p in pacientes:
        nasc = p.data_nascimento
        if (nasc.month, nasc.day) != (hoje.month, hoje.day):
            continue
        primeiro_nome = p.nome_completo.split()[0] if p.nome_completo else ""
        linhas.append({
            "paciente": p,
            "idade": _idade(nasc, hoje),
            "whatsapp": _wa_url(p.telefone, _msg_aniversario(primeiro_nome)),
        })
    linhas.sort(key=lambda x: x["paciente"].nome_completo or "")
    return linhas


def contar_aniversariantes_hoje():
    """KPI: nº de aniversariantes do dia (para badge no painel/menu)."""
    return len(_aniversariantes_do_dia())


@crm_bp.route("/aniversariantes")
@login_required
@recepcao_ou_admin
def aniversariantes():
    linhas = _aniversariantes_do_dia()
    hoje = datetime.now(_BR_TZ).date()
    return render_template("crm/aniversariantes.html", linhas=linhas, hoje=hoje)


@crm_bp.route("/aniversariantes/<int:paciente_id>/interagir", methods=["POST"])
@login_required
@recepcao_ou_admin
def registrar_interacao(paciente_id):
    """Registra que a clínica felicitou o paciente (trilha de CRM/auditoria).
    Escopo de clínica garantido pelo tenant loader (Paciente é escopado)."""
    paciente = db.session.get(Paciente, paciente_id)
    if paciente is None:
        abort(404)
    audit(AuditLog.ACAO_CRM_INTERACAO, recurso_tipo="paciente",
          recurso_id=paciente.id, detalhes="Felicitação de aniversário")
    flash(f"Interação registrada para {paciente.nome_completo}.", "success")
    return redirect(url_for("crm.aniversariantes"))
