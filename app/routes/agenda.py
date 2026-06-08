"""Agenda de consultas + registro de atendimento (prontuario).

- Listagem/criacao/status: recepcao ou admin (profissional ve a propria).
- Registro de atendimento clinico: profissional ou admin (clinico_required).
"""
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
)
from flask_login import login_required, current_user
from sqlalchemy import select

from app import db
from app.auth_decorators import recepcao_ou_admin, clinico_required
from app.models import (
    Agendamento, Atendimento, Paciente, Profissional, AuditLog,
    Procedimento, ItemAtendimento,
)
from app.services.audit import audit

agenda_bp = Blueprint("agenda", __name__, url_prefix="/agenda")

_BR_TZ = ZoneInfo("America/Sao_Paulo")
_STATUS_VALIDOS = {
    Agendamento.STATUS_AGENDADO, Agendamento.STATUS_CONFIRMADO,
    Agendamento.STATUS_ATENDIDO, Agendamento.STATUS_CANCELADO,
    Agendamento.STATUS_FALTOU,
}
# Status que a recepção pode setar manualmente na agenda. 'atendido' NUNCA é
# manual — vem só de agenda.atendimento (registro do prontuário), senão a
# consulta ficaria "atendida" sem prontuário e burlaria a trava de edição.
_STATUS_MANUAIS = {
    Agendamento.STATUS_AGENDADO, Agendamento.STATUS_CONFIRMADO,
    Agendamento.STATUS_CANCELADO, Agendamento.STATUS_FALTOU,
}


def _parse_dia(valor: str) -> date:
    """'YYYY-MM-DD' -> date. Default: hoje (fuso BR)."""
    if valor:
        try:
            return datetime.strptime(valor, "%Y-%m-%d").date()
        except ValueError:
            pass
    return datetime.now(_BR_TZ).date()


_RETORNO_DIAS = {"30": 30, "90": 90, "180": 180, "365": 365}


def _calcular_retorno(opcao: str, data_str: str):
    """Opcao 30/90/180/365 -> hoje+N dias; 'personalizado' -> data_str; senao None."""
    opcao = (opcao or "").strip()
    if opcao in _RETORNO_DIAS:
        return date.today() + timedelta(days=_RETORNO_DIAS[opcao])
    if opcao == "personalizado" and data_str:
        try:
            return datetime.strptime(data_str.strip(), "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _br_para_utc(dia: date, hora_str: str) -> datetime | None:
    """Combina dia + 'HH:MM' no fuso BR e converte pra UTC aware."""
    try:
        h, m = map(int, hora_str.split(":"))
    except (ValueError, AttributeError):
        return None
    local = datetime.combine(dia, time(h, m), tzinfo=_BR_TZ)
    return local.astimezone(timezone.utc)


def _conflito_horario(profissional_id, inicio, fim, excluir_id=None):
    """Agendamento sobreposto do mesmo profissional (ignora cancelados).

    excluir_id permite ignorar o proprio agendamento ao reagendar.
    """
    q = select(Agendamento).where(
        Agendamento.profissional_id == profissional_id,
        Agendamento.status != Agendamento.STATUS_CANCELADO,
        Agendamento.inicio < fim,
        Agendamento.fim > inicio,
    )
    if excluir_id:
        q = q.where(Agendamento.id != excluir_id)
    return db.session.execute(q).scalars().first()


def _msg_conflito(conflito):
    ini_br = conflito.inicio.astimezone(_BR_TZ).strftime("%H:%M")
    fim_br = conflito.fim.astimezone(_BR_TZ).strftime("%H:%M")
    nome = conflito.profissional.nome if conflito.profissional else "O profissional"
    return f"Conflito de horário: {nome} já tem consulta das {ini_br} às {fim_br}."


@agenda_bp.route("/")
@login_required
def listar():
    dia = _parse_dia(request.args.get("dia", ""))
    ini = datetime.combine(dia, time.min, tzinfo=_BR_TZ).astimezone(timezone.utc)
    fim = ini + timedelta(days=1)

    q = (
        select(Agendamento)
        .where(Agendamento.inicio >= ini, Agendamento.inicio < fim)
        .order_by(Agendamento.inicio)
    )
    # Profissional ve so a propria agenda. Recepcao/admin veem tudo, com
    # filtro opcional por profissional.
    filtro_prof = request.args.get("profissional_id", type=int)
    if current_user.is_profissional and current_user.profissional:
        q = q.where(Agendamento.profissional_id == current_user.profissional.id)
    elif filtro_prof:
        q = q.where(Agendamento.profissional_id == filtro_prof)

    agendamentos = db.session.execute(q).scalars().all()
    profissionais = db.session.execute(
        select(Profissional).where(Profissional.ativo.is_(True))
        .order_by(Profissional.nome)
    ).scalars().all()

    return render_template(
        "agenda/listar.html",
        agendamentos=agendamentos, dia=dia,
        profissionais=profissionais, filtro_prof=filtro_prof,
        dia_anterior=(dia - timedelta(days=1)).isoformat(),
        dia_seguinte=(dia + timedelta(days=1)).isoformat(),
    )


_SEMANA_HORA_INI = 7      # janela visível da grade (07:00)
_SEMANA_HORA_FIM = 21     # ...até 21:00
_SEMANA_PX_HORA = 52      # altura de 1h na grade (px)
_SEMANA_DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@agenda_bp.route("/semana")
@login_required
def semana():
    """Agenda em grade semanal (Seg–Dom), com blocos posicionados por horário.

    Posicionamento via data-* (CSP-safe, aplicado por agenda-week.js). Eventos
    sobrepostos (ex.: profissionais diferentes na visão 'Todos') são divididos
    em pistas lado a lado.
    """
    ref = _parse_dia(request.args.get("ref", ""))
    seg = ref - timedelta(days=ref.weekday())          # segunda-feira
    dias = [seg + timedelta(days=i) for i in range(7)]
    ini = datetime.combine(seg, time.min, tzinfo=_BR_TZ).astimezone(timezone.utc)
    fim = datetime.combine(seg + timedelta(days=7), time.min,
                           tzinfo=_BR_TZ).astimezone(timezone.utc)

    q = (select(Agendamento)
         .where(Agendamento.inicio >= ini, Agendamento.inicio < fim)
         .order_by(Agendamento.inicio))
    filtro_prof = request.args.get("profissional_id", type=int)
    if current_user.is_profissional and current_user.profissional:
        q = q.where(Agendamento.profissional_id == current_user.profissional.id)
    elif filtro_prof:
        q = q.where(Agendamento.profissional_id == filtro_prof)
    ags = db.session.execute(q).scalars().all()

    profissionais = db.session.execute(
        select(Profissional).where(Profissional.ativo.is_(True))
        .order_by(Profissional.nome)
    ).scalars().all()

    janela_min = (_SEMANA_HORA_FIM - _SEMANA_HORA_INI) * 60

    # Agrupa por dia da semana (0=Seg) com minutos relativos à janela.
    por_dia = {i: [] for i in range(7)}
    for ag in ags:
        ini_br = _aware(ag.inicio).astimezone(_BR_TZ)
        fim_br = _aware(ag.fim).astimezone(_BR_TZ)
        di = ini_br.weekday()
        s = (ini_br.hour - _SEMANA_HORA_INI) * 60 + ini_br.minute
        e = (fim_br.hour - _SEMANA_HORA_INI) * 60 + fim_br.minute
        s = max(0, min(s, janela_min))
        e = max(0, min(e, janela_min))
        if e <= s:
            e = min(s + 20, janela_min)   # altura mínima visual
        por_dia[di].append({"ag": ag, "s": s, "e": e,
                            "ini_br": ini_br, "fim_br": fim_br})

    # Lane-packing por dia: clusters de eventos sobrepostos -> pistas lado a lado.
    colunas = []
    for di in range(7):
        evs = sorted(por_dia[di], key=lambda x: (x["s"], x["e"]))
        i = 0
        while i < len(evs):
            cluster = [evs[i]]
            max_e = evs[i]["e"]
            j = i + 1
            while j < len(evs) and evs[j]["s"] < max_e:
                cluster.append(evs[j])
                max_e = max(max_e, evs[j]["e"])
                j += 1
            lanes = []
            for ev in cluster:
                colocado = False
                for li, last_e in enumerate(lanes):
                    if ev["s"] >= last_e:
                        ev["lane"], lanes[li], colocado = li, ev["e"], True
                        break
                if not colocado:
                    ev["lane"] = len(lanes)
                    lanes.append(ev["e"])
            for ev in cluster:
                ev["n"] = len(lanes)
            i = j

        coluna = []
        for ev in evs:
            n, lane = ev["n"], ev["lane"]
            ag = ev["ag"]
            cor = (ag.profissional.cor_agenda if ag.profissional else None) or "#43B8A5"
            coluna.append({
                "ag": ag, "ini_br": ev["ini_br"], "fim_br": ev["fim_br"],
                "top": round(ev["s"] * _SEMANA_PX_HORA / 60),
                "height": max(22, round((ev["e"] - ev["s"]) * _SEMANA_PX_HORA / 60) - 2),
                "left": round(lane * 100 / n, 2),
                "width": round(100 / n, 2),
                "accent": cor,
            })
        colunas.append(coluna)

    hoje_br = datetime.now(_BR_TZ).date()
    return render_template(
        "agenda/semana.html",
        dias=dias, dias_label=_SEMANA_DIAS, colunas=colunas,
        horas=list(range(_SEMANA_HORA_INI, _SEMANA_HORA_FIM)),
        px_hora=_SEMANA_PX_HORA, altura_grade=janela_min * _SEMANA_PX_HORA // 60,
        hoje=hoje_br, profissionais=profissionais, filtro_prof=filtro_prof,
        ref=ref.isoformat(),
        semana_anterior=(seg - timedelta(days=7)).isoformat(),
        semana_seguinte=(seg + timedelta(days=7)).isoformat(),
        semana_atual=datetime.now(_BR_TZ).date().isoformat(),
    )


@agenda_bp.route("/novo", methods=["GET", "POST"])
@login_required
@recepcao_ou_admin
def novo():
    profissionais = db.session.execute(
        select(Profissional).where(Profissional.ativo.is_(True))
        .order_by(Profissional.nome)
    ).scalars().all()
    pacientes = db.session.execute(
        select(Paciente).where(Paciente.ativo.is_(True))
        .order_by(Paciente.nome_completo)
    ).scalars().all()

    if request.method == "POST":
        paciente_id = request.form.get("paciente_id", type=int)
        profissional_id = request.form.get("profissional_id", type=int)
        dia = _parse_dia(request.form.get("dia", ""))
        hora = request.form.get("hora", "").strip()

        paciente = db.session.get(Paciente, paciente_id) if paciente_id else None
        profissional = (db.session.get(Profissional, profissional_id)
                        if profissional_id else None)
        inicio = _br_para_utc(dia, hora)

        if not (paciente and profissional and inicio):
            flash("Selecione paciente, profissional e horário válidos.", "error")
            return render_template("agenda/form.html",
                                   profissionais=profissionais,
                                   pacientes=pacientes, form=request.form,
                                   dia=dia.isoformat())

        if dia < datetime.now(_BR_TZ).date():
            flash("Não é possível agendar em data passada.", "error")
            return render_template("agenda/form.html",
                                   profissionais=profissionais,
                                   pacientes=pacientes, form=request.form,
                                   dia=dia.isoformat())

        # Duracao vem do cadastro do profissional (sem campo no agendamento).
        duracao = profissional.duracao_padrao_min or 30
        fim = inicio + timedelta(minutes=duracao)
        conflito = _conflito_horario(profissional.id, inicio, fim)
        if conflito:
            flash(_msg_conflito(conflito), "error")
            return render_template("agenda/form.html",
                                   profissionais=profissionais,
                                   pacientes=pacientes, form=request.form,
                                   dia=dia.isoformat())

        ag = Agendamento(
            paciente_id=paciente.id,
            profissional_id=profissional.id,
            inicio=inicio,
            fim=fim,
            status=Agendamento.STATUS_AGENDADO,
            convenio=request.form.get("convenio", "").strip() or None,
            observacoes=request.form.get("observacoes", "").strip() or None,
            criado_por_id=current_user.id,
        )
        db.session.add(ag)
        db.session.commit()
        audit(AuditLog.ACAO_AGENDAMENTO_CRIADO, recurso_tipo="agendamento",
              recurso_id=ag.id)
        flash("Consulta agendada.", "success")
        return redirect(url_for("agenda.listar", dia=dia.isoformat()))

    dia_default = _parse_dia(request.args.get("dia", "")).isoformat()
    # Pre-seleciona paciente quando vem do painel de retornos (CRM).
    form_inicial = {}
    pid = request.args.get("paciente_id", type=int)
    if pid:
        form_inicial["paciente_id"] = pid
    return render_template("agenda/form.html", profissionais=profissionais,
                           pacientes=pacientes, form=form_inicial, dia=dia_default)


@agenda_bp.route("/<int:agendamento_id>/status", methods=["POST"])
@login_required
@recepcao_ou_admin
def mudar_status(agendamento_id):
    ag = db.session.get(Agendamento, agendamento_id)
    if not ag:
        flash("Agendamento não encontrado.", "error")
        return redirect(url_for("agenda.listar"))
    novo_status = request.form.get("status", "").strip()
    if novo_status not in _STATUS_MANUAIS:
        flash("Status inválido.", "error")
        return redirect(url_for("agenda.listar"))
    # Consulta já atendida é imutável aqui (só o prontuário a tornou atendida).
    if ag.status == Agendamento.STATUS_ATENDIDO:
        flash("Consulta já atendida não pode mudar de status.", "error")
        dia = ag.inicio.astimezone(_BR_TZ).date().isoformat()
        return redirect(url_for("agenda.listar", dia=dia))
    ag.status = novo_status
    db.session.commit()
    audit(AuditLog.ACAO_AGENDAMENTO_STATUS, recurso_tipo="agendamento",
          recurso_id=ag.id, detalhes=f"status={novo_status}")
    flash("Status atualizado.", "success")
    dia = ag.inicio.astimezone(_BR_TZ).date().isoformat()
    return redirect(url_for("agenda.listar", dia=dia))


@agenda_bp.route("/<int:agendamento_id>/checkin", methods=["POST"])
@login_required
@recepcao_ou_admin
def checkin(agendamento_id):
    """Marca/desmarca a chegada do paciente (fila do dia). Chegar confirma a
    presença (agendado -> confirmado)."""
    ag = db.session.get(Agendamento, agendamento_id)
    if not ag:
        flash("Agendamento não encontrado.", "error")
        return redirect(url_for("agenda.listar"))
    if ag.checkin_em:
        ag.checkin_em = None
        msg = "Check-in desfeito."
    else:
        ag.checkin_em = datetime.now(timezone.utc)
        if ag.status == Agendamento.STATUS_AGENDADO:
            ag.status = Agendamento.STATUS_CONFIRMADO
        msg = "Paciente em atendimento na recepção."
    db.session.commit()
    audit(AuditLog.ACAO_AGENDAMENTO_CHECKIN, recurso_tipo="agendamento",
          recurso_id=ag.id)
    flash(msg, "success")
    dia = ag.inicio.astimezone(_BR_TZ).date().isoformat()
    return redirect(url_for("agenda.listar", dia=dia))


@agenda_bp.route("/<int:agendamento_id>/editar", methods=["GET", "POST"])
@login_required
@recepcao_ou_admin
def editar(agendamento_id):
    """Reagenda a consulta (profissional/dia/hora/convênio/obs) com checagem
    de conflito (ignorando o próprio agendamento)."""
    ag = db.session.get(Agendamento, agendamento_id)
    if not ag:
        flash("Agendamento não encontrado.", "error")
        return redirect(url_for("agenda.listar"))
    if ag.status == Agendamento.STATUS_ATENDIDO:
        flash("Consulta já atendida não pode ser reagendada.", "error")
        dia = ag.inicio.astimezone(_BR_TZ).date().isoformat()
        return redirect(url_for("agenda.listar", dia=dia))

    profissionais = db.session.execute(
        select(Profissional).where(Profissional.ativo.is_(True))
        .order_by(Profissional.nome)
    ).scalars().all()

    if request.method == "POST":
        profissional_id = request.form.get("profissional_id", type=int)
        dia = _parse_dia(request.form.get("dia", ""))
        hora = request.form.get("hora", "").strip()
        profissional = (db.session.get(Profissional, profissional_id)
                        if profissional_id else None)
        inicio = _br_para_utc(dia, hora)

        if not (profissional and inicio):
            flash("Selecione profissional e horário válidos.", "error")
            return render_template("agenda/editar.html", ag=ag,
                                   profissionais=profissionais, form=request.form)

        if dia < datetime.now(_BR_TZ).date():
            flash("Não é possível reagendar para data passada.", "error")
            return render_template("agenda/editar.html", ag=ag,
                                   profissionais=profissionais, form=request.form)

        duracao = profissional.duracao_padrao_min or 30
        fim = inicio + timedelta(minutes=duracao)
        conflito = _conflito_horario(profissional.id, inicio, fim, excluir_id=ag.id)
        if conflito:
            flash(_msg_conflito(conflito), "error")
            return render_template("agenda/editar.html", ag=ag,
                                   profissionais=profissionais, form=request.form)

        ag.profissional_id = profissional.id
        ag.inicio = inicio
        ag.fim = fim
        ag.convenio = request.form.get("convenio", "").strip() or None
        ag.observacoes = request.form.get("observacoes", "").strip() or None
        db.session.commit()
        audit(AuditLog.ACAO_AGENDAMENTO_EDITADO, recurso_tipo="agendamento",
              recurso_id=ag.id)
        flash("Consulta reagendada.", "success")
        return redirect(url_for("agenda.listar", dia=dia.isoformat()))

    form_inicial = {
        "profissional_id": ag.profissional_id,
        "dia": ag.inicio.astimezone(_BR_TZ).date().isoformat(),
        "hora": ag.inicio.astimezone(_BR_TZ).strftime("%H:%M"),
        "convenio": ag.convenio or "",
        "observacoes": ag.observacoes or "",
    }
    return render_template("agenda/editar.html", ag=ag,
                           profissionais=profissionais, form=form_inicial)


@agenda_bp.route("/<int:agendamento_id>/atendimento", methods=["GET", "POST"])
@login_required
@clinico_required
def atendimento(agendamento_id):
    """Registra/edita o prontuario de uma consulta. Dado sensivel (LGPD)."""
    ag = db.session.get(Agendamento, agendamento_id)
    if not ag:
        flash("Agendamento não encontrado.", "error")
        return redirect(url_for("agenda.listar"))

    # Profissional so registra atendimento da PROPRIA agenda.
    if (current_user.is_profissional and current_user.profissional
            and ag.profissional_id != current_user.profissional.id):
        flash("Você só pode registrar atendimentos da sua agenda.", "error")
        return redirect(url_for("agenda.listar"))

    registro = ag.atendimento

    if request.method == "POST":
        if registro is None:
            registro = Atendimento(
                agendamento_id=ag.id,
                paciente_id=ag.paciente_id,
                profissional_id=ag.profissional_id,
            )
            db.session.add(registro)
        registro.queixa = request.form.get("queixa", "").strip() or None
        registro.evolucao = request.form.get("evolucao", "").strip() or None
        registro.prescricao = request.form.get("prescricao", "").strip() or None
        # CRM Retorno: data recomendada a partir da opcao (30/90/180/365) ou
        # data personalizada. Vazio = sem retorno previsto.
        registro.retorno_em = _calcular_retorno(
            request.form.get("retorno_opcao", ""),
            request.form.get("retorno_data", ""),
        )
        # Itens/procedimentos consumidos (flagbox do medico). Recria a lista
        # com snapshot de nome+valor do catalogo (cascade remove os antigos).
        registro.itens.clear()
        # Convênio da consulta -> preço da tabela por convênio (ou padrão).
        # Fonte única: o convênio do agendamento (igual ao lançamento financeiro).
        conv = ag.convenio
        for sid in request.form.getlist("procedimentos"):
            try:
                proc = db.session.get(Procedimento, int(sid))
            except (TypeError, ValueError):
                proc = None
            if proc:
                registro.itens.append(ItemAtendimento(
                    procedimento_id=proc.id, descricao=proc.nome,
                    valor=proc.preco_para(conv), quantidade=1,
                ))
        # Marca a consulta como atendida ao registrar.
        ag.status = Agendamento.STATUS_ATENDIDO
        db.session.commit()
        audit(AuditLog.ACAO_ATENDIMENTO_REGISTRADO, recurso_tipo="atendimento",
              recurso_id=registro.id)
        flash("Atendimento registrado.", "success")
        return redirect(url_for("pacientes.detalhe", paciente_id=ag.paciente_id))

    # Historico clinico do paciente (consultas anteriores) — acesso facil
    # sem sair da tela. Exclui o registro atual.
    atual_id = registro.id if registro else None
    # Histórico clínico: o profissional só vê os SEUS atendimentos do paciente
    # (não a evolução escrita por outros médicos). Admin vê tudo. (LGPD)
    hist = ag.paciente.atendimentos
    if current_user.is_profissional and current_user.profissional:
        hist = [a for a in hist if a.profissional_id == current_user.profissional.id]
    historico = [a for a in hist if a.id != atual_id]
    procedimentos = db.session.execute(
        select(Procedimento).where(Procedimento.ativo.is_(True))
        .order_by(Procedimento.nome)
    ).scalars().all()
    selecionados = {i.procedimento_id for i in registro.itens} if registro else set()
    # Abrir o prontuario (com historico clinico) e' acesso a dado sensivel —
    # registra a leitura na trilha de auditoria (LGPD art. 37).
    audit(AuditLog.ACAO_PRONTUARIO_VISUALIZADO, recurso_tipo="paciente",
          recurso_id=ag.paciente_id)
    return render_template("agenda/atendimento.html", ag=ag, registro=registro,
                           historico=historico, procedimentos=procedimentos,
                           selecionados=selecionados)