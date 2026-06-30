"""Agenda de consultas + registro de atendimento (prontuario).

- Listagem/criacao/status: recepcao ou admin (profissional ve a propria).
- Registro de atendimento clinico: profissional ou admin (clinico_required).
"""
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request, g,
)
from flask_login import login_required, current_user
from sqlalchemy import select

from app import db, limiter
from app.auth_decorators import (
    recepcao_ou_admin, clinico_required, equipe_required,
)
from app.models import (
    Agendamento, Atendimento, Paciente, Profissional, AuditLog,
    Procedimento, ItemAtendimento, Clinica, Convenio, Bloqueio,
)
from app.routes.pacientes import _valida_cpf, _parse_data
from app.services.audit import audit
from app.services.tokens import ler_token_confirmacao

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
# Durações de consulta selecionáveis (min). Default = duração do profissional.
_DURACOES = (30, 60, 90, 120)


def _duracao_escolhida(profissional):
    """Duração (min) do form se válida; senão a padrão do profissional."""
    d = request.form.get("duracao_min", type=int)
    if d in _DURACOES:
        return d
    return profissional.duracao_padrao_min or 30


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
        # Data BR (container roda em UTC; date.today() viraria 1 dia à noite).
        return datetime.now(_BR_TZ).date() + timedelta(days=_RETORNO_DIAS[opcao])
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


def _bloqueio_conflito(profissional_id, inicio, fim):
    """1º bloqueio de agenda que cobre [inicio, fim) do profissional (RF-05).
    Escopado por clínica (Bloqueio é tenant-scoped quando logado)."""
    return db.session.execute(
        select(Bloqueio).where(
            Bloqueio.profissional_id == profissional_id,
            Bloqueio.inicio < fim,
            Bloqueio.fim > inicio,
        )
    ).scalars().first()


def _msg_bloqueio(bloq):
    ini_br = _aware(bloq.inicio).astimezone(_BR_TZ).strftime("%d/%m %H:%M")
    fim_br = _aware(bloq.fim).astimezone(_BR_TZ).strftime("%d/%m %H:%M")
    motivo = (bloq.motivo or "indisponível").strip()
    return (f"Agenda bloqueada nesse horário ({motivo}, de {ini_br} a {fim_br}). "
            "Escolha outro horário.")


def _conflito_sala(sala, inicio, fim, excluir_id=None, clinica_id=None):
    """Outra consulta na MESMA sala sobrepondo [inicio, fim) (RF-03). Ignora
    canceladas. Sala vazia -> sem checagem (consultório não atribuído).

    clinica_id explícito é OBRIGATÓRIO no contexto público (sem escopo
    automático): o nome da sala NÃO é único entre clínicas, então sem o filtro
    haveria conflito cruzado. No contexto logado o tenant loader já escopa."""
    if not sala:
        return None
    q = select(Agendamento).where(
        Agendamento.sala == sala,
        Agendamento.status != Agendamento.STATUS_CANCELADO,
        Agendamento.inicio < fim,
        Agendamento.fim > inicio,
    )
    if clinica_id is not None:
        q = q.where(Agendamento.clinica_id == clinica_id)
    if excluir_id:
        q = q.where(Agendamento.id != excluir_id)
    return db.session.execute(q).scalars().first()


def _msg_conflito_sala(conflito):
    ini_br = _aware(conflito.inicio).astimezone(_BR_TZ).strftime("%H:%M")
    fim_br = _aware(conflito.fim).astimezone(_BR_TZ).strftime("%H:%M")
    sala = conflito.sala or "essa sala"
    return (f"Sala ocupada: já há consulta em {sala} das {ini_br} às {fim_br}. "
            "Escolha outra sala ou horário.")


def _meu_prof_id():
    """ID do profissional do usuário logado para escopar a agenda à PRÓPRIA.
    Retorna -1 (id inexistente) para um profissional SEM cadastro vinculado
    (órfão) — assim ele não herda a visão de admin: cai num filtro vazio.
    None quando o usuário não é profissional (admin/recepção veem tudo)."""
    if current_user.is_profissional:
        return current_user.profissional.id if current_user.profissional else -1
    return None


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
    meu_prof = _meu_prof_id()
    if meu_prof is not None:
        q = q.where(Agendamento.profissional_id == meu_prof)
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


# Colunas do quadro Kanban (ordem = jornada do paciente). Cada agendamento do
# dia cai na coluna do seu status. 'atendido' nunca é manual (vem do prontuário).
_KANBAN_COLUNAS = (
    (Agendamento.STATUS_AGENDADO, "Agendado"),
    (Agendamento.STATUS_CONFIRMADO, "Confirmado"),
    (Agendamento.STATUS_ATENDIDO, "Atendido"),
    (Agendamento.STATUS_FALTOU, "Faltou"),
    (Agendamento.STATUS_CANCELADO, "Cancelado"),
)


@agenda_bp.route("/quadro")
@login_required
def kanban():
    """Quadro Kanban do dia: uma coluna por status (agendado/confirmado/
    atendido/faltou/cancelado), cada consulta como card com ações rápidas.
    Mesma janela/escopo da visão de lista (dia, filtro por profissional,
    profissional vê só a própria agenda). Reusa agenda.mudar_status (auditado)."""
    dia = _parse_dia(request.args.get("dia", ""))
    ini = datetime.combine(dia, time.min, tzinfo=_BR_TZ).astimezone(timezone.utc)
    fim = ini + timedelta(days=1)

    q = (select(Agendamento)
         .where(Agendamento.inicio >= ini, Agendamento.inicio < fim)
         .order_by(Agendamento.inicio))
    filtro_prof = request.args.get("profissional_id", type=int)
    meu_prof = _meu_prof_id()
    if meu_prof is not None:
        q = q.where(Agendamento.profissional_id == meu_prof)
    elif filtro_prof:
        q = q.where(Agendamento.profissional_id == filtro_prof)
    ags = db.session.execute(q).scalars().all()

    # Agrupa por status preservando a ordem por horário da query.
    por_status = {chave: [] for chave, _ in _KANBAN_COLUNAS}
    for ag in ags:
        if ag.status in por_status:
            por_status[ag.status].append(ag)
    colunas = [
        {"chave": chave, "titulo": titulo, "ags": por_status[chave]}
        for chave, titulo in _KANBAN_COLUNAS
    ]

    profissionais = db.session.execute(
        select(Profissional).where(Profissional.ativo.is_(True))
        .order_by(Profissional.nome)
    ).scalars().all()

    return render_template(
        "agenda/kanban.html",
        colunas=colunas, dia=dia, total=len(ags),
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
    meu_prof = _meu_prof_id()
    if meu_prof is not None:
        q = q.where(Agendamento.profissional_id == meu_prof)
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

    # Faixas de bloqueio por dia (recortadas à janela visível de cada coluna).
    bq = (select(Bloqueio).where(Bloqueio.inicio < fim, Bloqueio.fim > ini)
          .order_by(Bloqueio.inicio))
    if meu_prof is not None:
        bq = bq.where(Bloqueio.profissional_id == meu_prof)
    elif filtro_prof:
        bq = bq.where(Bloqueio.profissional_id == filtro_prof)
    blqs = db.session.execute(bq).scalars().all()
    blocos_semana = []
    for di in range(7):
        wi = datetime.combine(dias[di], time(_SEMANA_HORA_INI, 0),
                              tzinfo=_BR_TZ).astimezone(timezone.utc)
        wf = datetime.combine(dias[di], time(_SEMANA_HORA_FIM, 0),
                              tzinfo=_BR_TZ).astimezone(timezone.utc)
        faixas = []
        for b in blqs:
            bs = max(_aware(b.inicio), wi)
            be = min(_aware(b.fim), wf)
            if be <= bs:
                continue
            s_min = (bs - wi).total_seconds() / 60
            e_min = (be - wi).total_seconds() / 60
            faixas.append({
                "top": round(s_min * _SEMANA_PX_HORA / 60),
                "height": max(16, round((e_min - s_min) * _SEMANA_PX_HORA / 60) - 2),
                "motivo": b.motivo or "Bloqueio",
                "prof": b.profissional.nome if b.profissional else "",
            })
        blocos_semana.append(faixas)

    hoje_br = datetime.now(_BR_TZ).date()
    return render_template(
        "agenda/semana.html",
        dias=dias, dias_label=_SEMANA_DIAS, colunas=colunas,
        blocos_semana=blocos_semana,
        horas=list(range(_SEMANA_HORA_INI, _SEMANA_HORA_FIM)),
        px_hora=_SEMANA_PX_HORA, altura_grade=janela_min * _SEMANA_PX_HORA // 60,
        hoje=hoje_br, profissionais=profissionais, filtro_prof=filtro_prof,
        ref=ref.isoformat(),
        semana_anterior=(seg - timedelta(days=7)).isoformat(),
        semana_seguinte=(seg + timedelta(days=7)).isoformat(),
        semana_atual=datetime.now(_BR_TZ).date().isoformat(),
    )


def _lane_packing(evs):
    """Distribui eventos sobrepostos em pistas lado a lado (Google Calendar).
    Muta cada ev adicionando 'lane' e 'n' (nº de pistas do cluster)."""
    evs.sort(key=lambda x: (x["s"], x["e"]))
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
    return evs


@agenda_bp.route("/grade")
@login_required
def dia_grade():
    """Grade DIÁRIA visual (RF-01): coluna de horários com os agendamentos
    posicionados por horário (estilo Google Calendar/Teams) e faixas de
    bloqueio. Reusa o motor de posicionamento de agenda-week.js (data-*)."""
    dia = _parse_dia(request.args.get("dia", ""))
    ini = datetime.combine(dia, time.min, tzinfo=_BR_TZ).astimezone(timezone.utc)
    fim = ini + timedelta(days=1)

    q = (select(Agendamento)
         .where(Agendamento.inicio >= ini, Agendamento.inicio < fim)
         .order_by(Agendamento.inicio))
    filtro_prof = request.args.get("profissional_id", type=int)
    meu_prof = _meu_prof_id()
    if meu_prof is not None:
        q = q.where(Agendamento.profissional_id == meu_prof)
    elif filtro_prof:
        q = q.where(Agendamento.profissional_id == filtro_prof)
    ags = db.session.execute(q).scalars().all()

    profissionais = db.session.execute(
        select(Profissional).where(Profissional.ativo.is_(True))
        .order_by(Profissional.nome)
    ).scalars().all()

    janela_min = (_SEMANA_HORA_FIM - _SEMANA_HORA_INI) * 60
    win_ini = datetime.combine(dia, time(_SEMANA_HORA_INI, 0),
                               tzinfo=_BR_TZ).astimezone(timezone.utc)
    win_fim = datetime.combine(dia, time(_SEMANA_HORA_FIM, 0),
                               tzinfo=_BR_TZ).astimezone(timezone.utc)

    evs = []
    for ag in ags:
        ini_br = _aware(ag.inicio).astimezone(_BR_TZ)
        fim_br = _aware(ag.fim).astimezone(_BR_TZ)
        # Offset por subtração UTC aware contra a janela (robusto a evento que
        # cruza a meia-noite — não depende de fim_br.hour virar 0).
        s = (_aware(ag.inicio) - win_ini).total_seconds() / 60
        e = (_aware(ag.fim) - win_ini).total_seconds() / 60
        s = max(0, min(s, janela_min))
        e = max(0, min(e, janela_min))
        if e <= s:
            e = min(s + 20, janela_min)
        evs.append({"ag": ag, "s": s, "e": e, "ini_br": ini_br, "fim_br": fim_br})
    _lane_packing(evs)
    eventos = []
    for ev in evs:
        n, lane, ag = ev["n"], ev["lane"], ev["ag"]
        cor = (ag.profissional.cor_agenda if ag.profissional else None) or "#43B8A5"
        eventos.append({
            "ag": ag, "ini_br": ev["ini_br"], "fim_br": ev["fim_br"],
            "top": round(ev["s"] * _SEMANA_PX_HORA / 60),
            "height": max(22, round((ev["e"] - ev["s"]) * _SEMANA_PX_HORA / 60) - 2),
            "left": round(lane * 100 / n, 2), "width": round(100 / n, 2),
            "accent": cor,
        })

    # Faixas de bloqueio do dia (recortadas à janela visível — robusto p/
    # bloqueio de dia inteiro/multidias).
    bq = (select(Bloqueio).where(Bloqueio.inicio < fim, Bloqueio.fim > ini)
          .order_by(Bloqueio.inicio))
    meu_prof = _meu_prof_id()
    if meu_prof is not None:
        bq = bq.where(Bloqueio.profissional_id == meu_prof)
    elif filtro_prof:
        bq = bq.where(Bloqueio.profissional_id == filtro_prof)
    blocos = []
    for b in db.session.execute(bq).scalars().all():
        bs = max(_aware(b.inicio), win_ini)
        be = min(_aware(b.fim), win_fim)
        if be <= bs:
            continue
        s_min = (bs - win_ini).total_seconds() / 60
        e_min = (be - win_ini).total_seconds() / 60
        blocos.append({
            "bloq": b,
            "top": round(s_min * _SEMANA_PX_HORA / 60),
            "height": max(16, round((e_min - s_min) * _SEMANA_PX_HORA / 60) - 2),
        })

    return render_template(
        "agenda/dia_grade.html",
        dia=dia, eventos=eventos, blocos=blocos,
        horas=list(range(_SEMANA_HORA_INI, _SEMANA_HORA_FIM)),
        px_hora=_SEMANA_PX_HORA, altura_grade=janela_min * _SEMANA_PX_HORA // 60,
        profissionais=profissionais, filtro_prof=filtro_prof,
        hoje=datetime.now(_BR_TZ).date(),
        dia_anterior=(dia - timedelta(days=1)).isoformat(),
        dia_seguinte=(dia + timedelta(days=1)).isoformat(),
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

        # Duração: escolhida no form (30/60/90/120) ou a padrão do profissional.
        duracao = _duracao_escolhida(profissional)
        fim = inicio + timedelta(minutes=duracao)
        conflito = _conflito_horario(profissional.id, inicio, fim)
        if conflito:
            flash(_msg_conflito(conflito), "error")
            return render_template("agenda/form.html",
                                   profissionais=profissionais,
                                   pacientes=pacientes, form=request.form,
                                   dia=dia.isoformat())
        bloq = _bloqueio_conflito(profissional.id, inicio, fim)
        if bloq:
            flash(_msg_bloqueio(bloq), "error")
            return render_template("agenda/form.html",
                                   profissionais=profissionais,
                                   pacientes=pacientes, form=request.form,
                                   dia=dia.isoformat())
        # Sala: a escolhida ou, se vazia, a sala padrão do profissional.
        sala_final = (request.form.get("sala", "").strip()
                      or profissional.sala or None)
        conflito_sala = _conflito_sala(sala_final, inicio, fim)
        if conflito_sala:
            flash(_msg_conflito_sala(conflito_sala), "error")
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
            sala=sala_final,
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


def _profissionais_para_bloqueio():
    """Profissionais que o usuário atual pode bloquear: profissional só a si
    mesmo; admin/recepção veem todos os ativos da clínica (RF-06)."""
    if current_user.is_profissional:
        # Profissional órfão (sem cadastro) não pode bloquear ninguém.
        return [current_user.profissional] if current_user.profissional else []
    return db.session.execute(
        select(Profissional).where(Profissional.ativo.is_(True))
        .order_by(Profissional.nome)
    ).scalars().all()


@agenda_bp.route("/bloqueios", methods=["GET", "POST"])
@login_required
@equipe_required
def bloqueios():
    """Bloqueio de agenda (RF-05/06): férias, congresso, reunião, ausência.
    Todos os perfis da equipe podem bloquear; o profissional só a própria
    agenda. Criação auditada (RF-07)."""
    profissionais = _profissionais_para_bloqueio()
    ids_permitidos = {p.id for p in profissionais}

    if request.method == "POST":
        prof_id = request.form.get("profissional_id", type=int)
        # Profissional só bloqueia a própria agenda (ignora o que vier no form).
        if current_user.is_profissional and current_user.profissional:
            prof_id = current_user.profissional.id
        profissional = db.session.get(Profissional, prof_id) if prof_id else None
        if not profissional or profissional.id not in ids_permitidos:
            flash("Selecione um profissional válido.", "error")
            return redirect(url_for("agenda.bloqueios"))

        data_ini = _parse_data(request.form.get("data_inicio", ""))
        data_fim = _parse_data(request.form.get("data_fim", "")) or data_ini
        hora_ini = request.form.get("hora_inicio", "").strip()
        hora_fim = request.form.get("hora_fim", "").strip()
        motivo = (request.form.get("motivo", "").strip() or "Ausência")[:120]

        if not data_ini:
            flash("Informe a data do bloqueio.", "error")
            return redirect(url_for("agenda.bloqueios"))

        if hora_ini and hora_fim:
            # Faixa de horário num dia (ex.: reunião 14:00–16:00).
            inicio = _br_para_utc(data_ini, hora_ini)
            fim = _br_para_utc(data_ini, hora_fim)
            if not inicio or not fim or fim <= inicio:
                flash("Horário do bloqueio inválido (fim deve ser após o início).",
                      "error")
                return redirect(url_for("agenda.bloqueios"))
        else:
            # Dia(s) inteiro(s) (ex.: férias, congresso).
            if data_fim < data_ini:
                flash("A data final deve ser igual ou após a inicial.", "error")
                return redirect(url_for("agenda.bloqueios"))
            inicio = datetime.combine(data_ini, time.min,
                                      tzinfo=_BR_TZ).astimezone(timezone.utc)
            fim = datetime.combine(data_fim + timedelta(days=1), time.min,
                                   tzinfo=_BR_TZ).astimezone(timezone.utc)

        bloq = Bloqueio(profissional_id=profissional.id, inicio=inicio, fim=fim,
                        motivo=motivo, criado_por_id=current_user.id)
        db.session.add(bloq)
        db.session.commit()
        audit(AuditLog.ACAO_BLOQUEIO_CRIADO, recurso_tipo="bloqueio",
              recurso_id=bloq.id, detalhes=f"prof={profissional.id} {motivo}")
        flash("Bloqueio criado.", "success")
        return redirect(url_for("agenda.bloqueios"))

    # GET — lista os bloqueios vigentes/futuros (fim >= agora).
    agora = datetime.now(timezone.utc)
    q = (select(Bloqueio).where(Bloqueio.fim >= agora)
         .order_by(Bloqueio.inicio))
    meu_prof = _meu_prof_id()
    filtro_prof = request.args.get("profissional_id", type=int)
    if meu_prof is not None:
        q = q.where(Bloqueio.profissional_id == meu_prof)
    elif filtro_prof:
        q = q.where(Bloqueio.profissional_id == filtro_prof)
    lista = db.session.execute(q).scalars().all()
    return render_template("agenda/bloqueios.html", bloqueios=lista,
                           profissionais=profissionais,
                           motivos=Bloqueio.MOTIVOS,
                           hoje=datetime.now(_BR_TZ).date().isoformat())


@agenda_bp.route("/bloqueios/<int:bloqueio_id>/remover", methods=["POST"])
@login_required
@equipe_required
def remover_bloqueio(bloqueio_id):
    """Desbloqueia a agenda (RF-05/07). Profissional só remove os próprios."""
    bloq = db.session.get(Bloqueio, bloqueio_id)   # auto-escopado por clínica
    if not bloq:
        flash("Bloqueio não encontrado.", "error")
        return redirect(url_for("agenda.bloqueios"))
    if current_user.is_profissional and (
            not current_user.profissional
            or bloq.profissional_id != current_user.profissional.id):
        flash("Você só pode remover bloqueios da sua agenda.", "error")
        return redirect(url_for("agenda.bloqueios"))
    bid = bloq.id
    db.session.delete(bloq)
    db.session.commit()
    audit(AuditLog.ACAO_BLOQUEIO_REMOVIDO, recurso_tipo="bloqueio", recurso_id=bid)
    flash("Bloqueio removido.", "success")
    return redirect(url_for("agenda.bloqueios"))


def _normalizar_tel(t):
    """Só dígitos, no máx. 13 (DDI+DDD+numero). '' se vazio."""
    import re
    return re.sub(r"\D", "", t or "")[:13]


def _clinicas_ativas():
    """Todas as clínicas ativas (sem escopo — contexto público)."""
    return db.session.execute(
        select(Clinica).where(Clinica.ativo.is_(True))
        .execution_options(ignore_tenant=True).order_by(Clinica.nome)
    ).scalars().all()


def _clinica_publica():
    """Clínica do agendamento público. Prioridade: slug do portal
    (g.portal_clinica) > clinica_id escolhida no form/query > clínica única.
    None quando há várias clínicas e nenhuma foi escolhida (mostra o seletor)."""
    cl = getattr(g, "portal_clinica", None)
    if cl is not None:
        return cl
    cid = request.values.get("clinica_id", type=int)
    if cid:
        c = db.session.execute(
            select(Clinica).where(Clinica.id == cid, Clinica.ativo.is_(True))
            .execution_options(ignore_tenant=True)
        ).scalars().first()
        if c:
            return c
    ativas = db.session.execute(
        select(Clinica).where(Clinica.ativo.is_(True))
        .execution_options(ignore_tenant=True).limit(2)
    ).scalars().all()
    return ativas[0] if len(ativas) == 1 else None


# Mantido por compatibilidade (nome antigo).
_portal_clinica = _clinica_publica


def _intervalo_utc(profissional, dia):
    """Janela de pausa/almoço do profissional no dia, em UTC. None se sem pausa."""
    ii, iff = profissional.intervalo_inicio, profissional.intervalo_fim
    if not (ii and iff):
        return None
    a = datetime.combine(dia, ii, tzinfo=_BR_TZ).astimezone(timezone.utc)
    b = datetime.combine(dia, iff, tzinfo=_BR_TZ).astimezone(timezone.utc)
    return (a, b)


def _bloqueios_no_intervalo(profissional_id, ini_utc, fim_utc):
    """Bloqueios do profissional que tocam [ini_utc, fim_utc)."""
    return db.session.execute(
        select(Bloqueio).where(
            Bloqueio.profissional_id == profissional_id,
            Bloqueio.inicio < fim_utc, Bloqueio.fim > ini_utc)
    ).scalars().all()


def _slots_livres(profissional, dia):
    """Horários livres ('HH:MM') do profissional no dia, respeitando a
    disponibilidade configurada (RF-03/04): dias de atendimento, horário de
    início/fim, pausa (almoço), agendamentos existentes e bloqueios de agenda.
    Passo = duração padrão do profissional."""
    if dia.weekday() not in profissional.dias_atendimento_set():
        return []
    passo = profissional.duracao_padrao_min or 30
    ini_dia = datetime.combine(dia, profissional.disp_hora_inicio(),
                               tzinfo=_BR_TZ).astimezone(timezone.utc)
    fim_dia = datetime.combine(dia, profissional.disp_hora_fim(),
                               tzinfo=_BR_TZ).astimezone(timezone.utc)
    pausa = _intervalo_utc(profissional, dia)
    ocupados = db.session.execute(
        select(Agendamento).where(
            Agendamento.profissional_id == profissional.id,
            Agendamento.status != Agendamento.STATUS_CANCELADO,
            Agendamento.inicio < fim_dia, Agendamento.fim > ini_dia)
    ).scalars().all()
    bloqueios = _bloqueios_no_intervalo(profissional.id, ini_dia, fim_dia)
    agora = datetime.now(timezone.utc)
    livres, t = [], ini_dia
    while t + timedelta(minutes=passo) <= fim_dia:
        fimslot = t + timedelta(minutes=passo)
        na_pausa = bool(pausa) and t < pausa[1] and fimslot > pausa[0]
        ocupado = any(_aware(o.inicio) < fimslot and _aware(o.fim) > t
                      for o in ocupados)
        bloqueado = any(_aware(b.inicio) < fimslot and _aware(b.fim) > t
                        for b in bloqueios)
        if t >= agora and not na_pausa and not ocupado and not bloqueado:
            livres.append(t.astimezone(_BR_TZ).strftime("%H:%M"))
        t = fimslot
    return livres


def _profissionais_da_clinica(clinica, especialidade=None):
    """Profissionais ativos da clínica (sem escopo — público), opcionalmente
    filtrados por especialidade."""
    q = (select(Profissional).where(
            Profissional.ativo.is_(True),
            Profissional.clinica_id == clinica.id)
         .execution_options(ignore_tenant=True).order_by(Profissional.nome))
    if especialidade:
        q = q.where(Profissional.especialidade == especialidade)
    return db.session.execute(q).scalars().all()


def _especialidades_da_clinica(clinica):
    """Especialidades distintas (não vazias) dos profissionais da clínica."""
    return db.session.execute(
        select(Profissional.especialidade).where(
            Profissional.ativo.is_(True),
            Profissional.clinica_id == clinica.id,
            Profissional.especialidade.is_not(None),
            Profissional.especialidade != "")
        .execution_options(ignore_tenant=True)
        .distinct().order_by(Profissional.especialidade)
    ).scalars().all()


def _cria_ou_reusa_paciente(clinica, nome, telefone, cpf_fmt, data_nasc, convenio):
    """Cria o cadastro do paciente do agendamento online (ou reusa o existente
    de MESMO CPF na MESMA clínica). CPF é único global: se pertencer a outra
    clínica, cadastra sem CPF (a recepção concilia) — evita vínculo cross-tenant.
    Nunca SOBRESCREVE dados de um cadastro existente (fonte anônima)."""
    existente = db.session.execute(
        select(Paciente).where(Paciente.cpf == cpf_fmt)
        .execution_options(ignore_tenant=True)
    ).scalars().first() if cpf_fmt else None
    if existente is not None:
        if existente.clinica_id == clinica.id:
            return existente            # paciente recorrente -> reusa
        cpf_fmt = None                  # CPF de outra clínica -> não vincula
    paciente = Paciente(
        nome_completo=nome, telefone=telefone, cpf=cpf_fmt,
        data_nascimento=data_nasc,
        convenio=convenio or None,
        origem="Site",   # veio pelo agendamento online da clínica
        observacoes="Cadastro via agendamento online (a verificar).",
        clinica_id=clinica.id)
    db.session.add(paciente)
    db.session.flush()
    return paciente


@agenda_bp.route("/agendar", methods=["GET", "POST"])
@limiter.limit("5 per hour;1 per minute", methods=["POST"])
def agendar_online():
    """Agendamento online PÚBLICO (portal do paciente). Sem login.

    Passo 0 (multi-clínica): escolhe a clínica. Passo 1: especialidade
    (opcional) + profissional + dia. Passo 2: escolhe um horário livre e informa
    nome, CPF, data de nascimento e WhatsApp. Cria a consulta como 'agendado'.
    ESCOPADO por clínica (slug do portal, clinica_id escolhido ou clínica única).
    """
    hoje = datetime.now(_BR_TZ).date()
    clinica = _clinica_publica()

    # Passo 0: várias clínicas e nenhuma escolhida -> mostra o seletor.
    if clinica is None:
        return render_template("agenda/agendar.html",
                               clinicas=_clinicas_ativas(), hoje=hoje)

    especialidade = (request.values.get("especialidade", "") or "").strip() or None
    especialidades = _especialidades_da_clinica(clinica)
    profissionais = _profissionais_da_clinica(clinica, especialidade)
    convenios = db.session.execute(
        select(Convenio.nome).where(Convenio.clinica_id == clinica.id,
                                    Convenio.ativo.is_(True))
        .execution_options(ignore_tenant=True).order_by(Convenio.nome)
    ).scalars().all()

    def _ctx(**extra):
        base = dict(clinica=clinica, profissionais=profissionais,
                    especialidades=especialidades, especialidade=especialidade,
                    convenios=convenios, hoje=hoje)
        base.update(extra)
        return base

    if request.method == "POST":
        # Honeypot anti-bot: campo oculto que humano não preenche.
        if request.form.get("website", "").strip():
            flash("Não foi possível processar a solicitação.", "error")
            return render_template("agenda/agendar.html",
                                   **_ctx(prof_sel=None, dia=None, slots=None,
                                          form={}))

        profissional = db.session.get(
            Profissional, request.form.get("profissional_id", type=int))
        dia = _parse_dia(request.form.get("dia", ""))
        hora = request.form.get("hora", "").strip()
        nome = request.form.get("nome", "").strip()[:150]
        telefone = _normalizar_tel(request.form.get("telefone", ""))
        cpf_fmt, cpf_ok = _valida_cpf(request.form.get("cpf", ""))
        data_nasc = _parse_data(request.form.get("data_nascimento", ""))

        def _reexibe(msg):
            flash(msg, "error")
            slots = (_slots_livres(profissional, dia)
                     if profissional and dia and dia >= hoje else None)
            return render_template("agenda/agendar.html",
                                   **_ctx(prof_sel=profissional, dia=dia,
                                          slots=slots, form=request.form))

        if not profissional or profissional.clinica_id != clinica.id:
            return _reexibe("Selecione um profissional.")
        if len(nome) < 2:
            return _reexibe("Informe seu nome completo.")
        if not cpf_ok or not cpf_fmt:
            return _reexibe("Informe um CPF válido.")
        if not data_nasc:
            return _reexibe("Informe sua data de nascimento.")
        if not (10 <= len(telefone) <= 13):
            return _reexibe("Informe um WhatsApp válido com DDD.")
        if dia < hoje:
            return _reexibe("Escolha uma data futura.")
        # O horário precisa ser um dos slots livres (barra hora arbitrária,
        # fora do expediente e fim de semana — fonte única com o GET).
        if hora not in _slots_livres(profissional, dia):
            return _reexibe("Horário indisponível. Escolha um dos livres.")

        inicio = _br_para_utc(dia, hora)
        fim = inicio + timedelta(minutes=profissional.duracao_padrao_min or 30)
        # Sala da consulta online = sala padrão do profissional. Checa conflito
        # de sala escopado à clínica (contexto público não tem escopo auto).
        sala_online = profissional.sala or None
        if (not inicio or _conflito_horario(profissional.id, inicio, fim)
                or _bloqueio_conflito(profissional.id, inicio, fim)
                or _conflito_sala(sala_online, inicio, fim,
                                  clinica_id=clinica.id)):
            return _reexibe("Esse horário acabou de ser ocupado. Escolha outro.")

        convenio = request.form.get("convenio", "").strip() or None
        # Rota pública (sem login): convênio só vale se for um da lista CONTROLADA
        # da clínica. POST forjado com convênio arbitrário vira "particular".
        if convenio and convenio not in convenios:
            convenio = None
        paciente = _cria_ou_reusa_paciente(
            clinica, nome, telefone, cpf_fmt, data_nasc, convenio)

        ag = Agendamento(
            paciente_id=paciente.id, profissional_id=profissional.id,
            inicio=inicio, fim=fim, status=Agendamento.STATUS_AGENDADO,
            convenio=convenio, sala=sala_online,
            observacoes=request.form.get("observacoes", "").strip()[:500] or None,
            clinica_id=clinica.id)
        db.session.add(ag)
        db.session.commit()
        audit(AuditLog.ACAO_AGENDAMENTO_CRIADO, recurso_tipo="agendamento",
              recurso_id=ag.id, detalhes="online")
        return render_template("agenda/agendar.html", sucesso=ag, **_ctx())

    # GET — passo 1 (escolher prof/dia) e, se válidos, passo 2 (slots).
    prof_sel = db.session.get(
        Profissional, request.args.get("profissional_id", type=int)) \
        if request.args.get("profissional_id") else None
    if prof_sel and prof_sel.clinica_id != clinica.id:
        prof_sel = None
    dia = _parse_dia(request.args.get("dia", "")) if request.args.get("dia") else None
    slots = None
    if prof_sel and dia and dia >= hoje:
        slots = _slots_livres(prof_sel, dia)
    return render_template("agenda/agendar.html",
                           **_ctx(prof_sel=prof_sel, dia=dia, slots=slots,
                                  form={}))


@agenda_bp.route("/confirmar/<token>", methods=["GET", "POST"])
@limiter.limit("30 per hour")
def confirmar_publico(token):
    """Página PÚBLICA de confirmação de consulta (link do WhatsApp).

    O token é assinado (itsdangerous) — sem login, sem IDOR. GET mostra os
    dados e um botão; POST confirma a presença (agendado -> confirmado).
    """
    ag_id = ler_token_confirmacao(token)
    ag = db.session.get(Agendamento, ag_id) if ag_id else None
    if not ag:
        return render_template("agenda/confirmar.html", ag=None, erro="link"), 400
    if ag.status in (Agendamento.STATUS_CANCELADO, Agendamento.STATUS_ATENDIDO):
        return render_template("agenda/confirmar.html", ag=ag, erro="estado")

    if request.method == "POST":
        if ag.status == Agendamento.STATUS_AGENDADO:
            ag.status = Agendamento.STATUS_CONFIRMADO
            db.session.commit()
            audit(AuditLog.ACAO_AGENDAMENTO_CONFIRMADO_PUB,
                  recurso_tipo="agendamento", recurso_id=ag.id)
        return render_template("agenda/confirmar.html", ag=ag, confirmado=True)

    confirmado = ag.status == Agendamento.STATUS_CONFIRMADO
    return render_template("agenda/confirmar.html", ag=ag, confirmado=confirmado)


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

        duracao = _duracao_escolhida(profissional)
        fim = inicio + timedelta(minutes=duracao)
        conflito = _conflito_horario(profissional.id, inicio, fim, excluir_id=ag.id)
        if conflito:
            flash(_msg_conflito(conflito), "error")
            return render_template("agenda/editar.html", ag=ag,
                                   profissionais=profissionais, form=request.form)
        bloq = _bloqueio_conflito(profissional.id, inicio, fim)
        if bloq:
            flash(_msg_bloqueio(bloq), "error")
            return render_template("agenda/editar.html", ag=ag,
                                   profissionais=profissionais, form=request.form)
        sala_final = (request.form.get("sala", "").strip()
                      or profissional.sala or None)
        conflito_sala = _conflito_sala(sala_final, inicio, fim, excluir_id=ag.id)
        if conflito_sala:
            flash(_msg_conflito_sala(conflito_sala), "error")
            return render_template("agenda/editar.html", ag=ag,
                                   profissionais=profissionais, form=request.form)

        ag.profissional_id = profissional.id
        ag.inicio = inicio
        ag.fim = fim
        ag.convenio = request.form.get("convenio", "").strip() or None
        ag.sala = sala_final
        ag.observacoes = request.form.get("observacoes", "").strip() or None
        # Reagendou p/ outra data -> precisa reenviar lembrete da NOVA data.
        ag.lembrete_enviado_em = None
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
        "sala": ag.sala or "",
        "duracao_min": int((ag.fim - ag.inicio).total_seconds() // 60),
        "observacoes": ag.observacoes or "",
    }
    return render_template("agenda/editar.html", ag=ag,
                           profissionais=profissionais, form=form_inicial)


def aplicar_campos_prontuario(registro, ag):
    """Aplica os campos do form ao registro de atendimento (queixa, evolução,
    prescrição, retorno, itens e atestado). NÃO altera o status do agendamento
    — por isso pode ser chamado tanto pelo 'Salvar atendimento' quanto pelo
    upload de exame (preserva o rascunho ao anexar, evitando perda de dados)."""
    registro.queixa = request.form.get("queixa", "").strip() or None
    registro.evolucao = request.form.get("evolucao", "").strip() or None
    registro.prescricao = request.form.get("prescricao", "").strip() or None
    # CRM Retorno: data recomendada (30/90/180/365) ou personalizada.
    registro.retorno_em = _calcular_retorno(
        request.form.get("retorno_opcao", ""),
        request.form.get("retorno_data", ""),
    )
    # Atestado (opcional): dias de afastamento + CID.
    dias = request.form.get("atestado_dias", type=int)
    registro.atestado_dias = dias if (dias and dias > 0) else None
    registro.atestado_cid = request.form.get("atestado_cid", "").strip()[:20] or None
    # Itens/procedimentos consumidos. Recria a lista com snapshot nome+valor.
    registro.itens.clear()
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
        # Era edição (prontuário já existia) ou primeiro registro? Define a
        # ação de auditoria (req. do sócio: registrar ALTERAÇÕES de prontuário).
        era_edicao = registro is not None
        if registro is None:
            registro = Atendimento(
                agendamento_id=ag.id,
                paciente_id=ag.paciente_id,
                profissional_id=ag.profissional_id,
            )
            db.session.add(registro)
        aplicar_campos_prontuario(registro, ag)
        # Marca a consulta como atendida ao registrar.
        ag.status = Agendamento.STATUS_ATENDIDO
        db.session.commit()
        audit(AuditLog.ACAO_ATENDIMENTO_EDITADO if era_edicao
              else AuditLog.ACAO_ATENDIMENTO_REGISTRADO,
              recurso_tipo="atendimento", recurso_id=registro.id,
              detalhes="edicao" if era_edicao else "registro")
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