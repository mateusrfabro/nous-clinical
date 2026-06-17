"""Gestao de profissionais (admin). Cria o login (Usuario tipo=profissional)
junto com o registro Profissional."""
from datetime import time
from decimal import Decimal, InvalidOperation

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required
from sqlalchemy import select

from app import db
from app.auth_decorators import admin_required
from app.models import Usuario, Profissional, AuditLog
from app.services.passwords import hash_senha
from app.services.audit import audit

profissionais_bp = Blueprint("profissionais", __name__,
                             url_prefix="/profissionais")

# Dias da semana p/ disponibilidade (weekday(): 0=Seg .. 6=Dom).
DIAS_SEMANA = [(0, "Seg"), (1, "Ter"), (2, "Qua"), (3, "Qui"),
               (4, "Sex"), (5, "Sáb"), (6, "Dom")]


def _parse_horario(raw):
    """'HH:MM' -> time, ou None se vazio/inválido."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        h, m = (int(x) for x in raw.split(":")[:2])
        return time(h, m)
    except (ValueError, TypeError):
        return None


def _parse_dias(form):
    """Checkboxes 'dias' (weekday 0..6) -> CSV ordenado e deduplicado."""
    vals = {int(d) for d in form.getlist("dias")
            if d.isdigit() and 0 <= int(d) <= 6}
    return ",".join(str(x) for x in sorted(vals))


def _disp_ctx_novo(form):
    """Contexto de disponibilidade pro form de NOVO (defaults seg-sex 08-18,
    ou repopula do POST em caso de erro)."""
    if form:
        dias = [int(d) for d in form.getlist("dias")
                if d.isdigit() and 0 <= int(d) <= 6]
        return {"dias": dias,
                "hora_inicio": form.get("hora_inicio", "") or "08:00",
                "hora_fim": form.get("hora_fim", "") or "18:00",
                "intervalo_inicio": form.get("intervalo_inicio", ""),
                "intervalo_fim": form.get("intervalo_fim", "")}
    return {"dias": [0, 1, 2, 3, 4], "hora_inicio": "08:00",
            "hora_fim": "18:00", "intervalo_inicio": "", "intervalo_fim": ""}


def _disp_ctx_prof(prof):
    """Contexto de disponibilidade a partir do profissional (tela de edição)."""
    def hhmm(t):
        return t.strftime("%H:%M") if t else ""
    return {"dias": sorted(prof.dias_atendimento_set()),
            "hora_inicio": hhmm(prof.disp_hora_inicio()),
            "hora_fim": hhmm(prof.disp_hora_fim()),
            "intervalo_inicio": hhmm(prof.intervalo_inicio),
            "intervalo_fim": hhmm(prof.intervalo_fim)}


def _aplica_disponibilidade(prof, form):
    """Lê os campos de disponibilidade do form e aplica ao profissional.
    Retorna msg de erro (str) se inválido, senão None."""
    hi = _parse_horario(form.get("hora_inicio"))
    hf = _parse_horario(form.get("hora_fim"))
    ii = _parse_horario(form.get("intervalo_inicio"))
    iff = _parse_horario(form.get("intervalo_fim"))
    if hi and hf and hf <= hi:
        return "O horário final deve ser maior que o inicial."
    if (ii and not iff) or (iff and not ii):
        return "Informe início e fim do intervalo (ou deixe ambos vazios)."
    if ii and iff and iff <= ii:
        return "O fim do intervalo deve ser maior que o início."
    prof.dias_atendimento = _parse_dias(form)
    prof.hora_inicio = hi or Profissional.DISP_HORA_INI_PADRAO
    prof.hora_fim = hf or Profissional.DISP_HORA_FIM_PADRAO
    prof.intervalo_inicio = ii
    prof.intervalo_fim = iff
    return None


def _parse_comissao(raw):
    """Texto -> Decimal de comissão clampado em 0..100 (default 0)."""
    s = (raw or "").strip().replace("%", "").replace(",", ".")
    if not s:
        return Decimal("0")
    try:
        v = Decimal(s)
        if not v.is_finite():        # 'nan'/'inf' constroem mas quebram comparação
            return Decimal("0")
    except InvalidOperation:
        return Decimal("0")
    return min(max(v, Decimal("0")), Decimal("100"))


@profissionais_bp.route("/")
@login_required
@admin_required
def listar():
    profissionais = db.session.execute(
        select(Profissional).order_by(Profissional.nome)
    ).scalars().all()
    return render_template("profissionais/listar.html",
                           profissionais=profissionais)


@profissionais_bp.route("/novo", methods=["GET", "POST"])
@login_required
@admin_required
def novo():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        if not (nome and email and len(senha) >= 8):
            flash("Nome, e-mail e senha (mín. 8 caracteres) são obrigatórios.",
                  "error")
            return render_template("profissionais/form.html", form=request.form, dias_semana=DIAS_SEMANA, disp=_disp_ctx_novo(request.form))

        ja_existe = db.session.execute(
            select(Usuario).where(Usuario.email == email)
        ).scalar_one_or_none()
        if ja_existe:
            flash("Já existe um usuário com esse e-mail.", "error")
            return render_template("profissionais/form.html", form=request.form, dias_semana=DIAS_SEMANA, disp=_disp_ctx_novo(request.form))

        usuario = Usuario(
            email=email,
            senha_hash=hash_senha(senha),
            nome_responsavel=nome,
            telefone=request.form.get("telefone", "").strip() or None,
            tipo="profissional",
        )
        db.session.add(usuario)
        db.session.flush()

        prof = Profissional(
            usuario_id=usuario.id,
            nome=nome,
            especialidade=request.form.get("especialidade", "").strip() or None,
            registro_conselho=request.form.get("registro_conselho", "").strip()
            or None,
            cor_agenda=request.form.get("cor_agenda", "").strip() or "#43B8A5",
            duracao_padrao_min=request.form.get("duracao_padrao_min", type=int)
            or 30,
            sala=request.form.get("sala", "").strip() or None,
            comissao_percent=_parse_comissao(request.form.get("comissao_percent", "")),
        )
        erro_disp = _aplica_disponibilidade(prof, request.form)
        if erro_disp:
            db.session.rollback()
            flash(erro_disp, "error")
            return render_template("profissionais/form.html", form=request.form, dias_semana=DIAS_SEMANA, disp=_disp_ctx_novo(request.form))
        db.session.add(prof)
        db.session.commit()
        audit(AuditLog.ACAO_PROFISSIONAL_CRIADO, recurso_tipo="profissional",
              recurso_id=prof.id)
        flash("Profissional cadastrado com acesso ao sistema.", "success")
        return redirect(url_for("profissionais.listar"))

    return render_template("profissionais/form.html", form={}, dias_semana=DIAS_SEMANA, disp=_disp_ctx_novo(None))


@profissionais_bp.route("/<int:profissional_id>/editar", methods=["GET", "POST"])
@login_required
@admin_required
def editar(profissional_id):
    prof = db.session.get(Profissional, profissional_id)
    if not prof:
        flash("Profissional não encontrado.", "error")
        return redirect(url_for("profissionais.listar"))

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("Nome é obrigatório.", "error")
            return render_template("profissionais/editar.html", prof=prof, dias_semana=DIAS_SEMANA, disp=_disp_ctx_prof(prof))
        prof.nome = nome
        prof.especialidade = request.form.get("especialidade", "").strip() or None
        prof.registro_conselho = request.form.get("registro_conselho", "").strip() or None
        prof.cor_agenda = request.form.get("cor_agenda", "").strip() or prof.cor_agenda
        prof.duracao_padrao_min = (request.form.get("duracao_padrao_min", type=int)
                                   or prof.duracao_padrao_min)
        prof.sala = request.form.get("sala", "").strip() or None
        prof.comissao_percent = _parse_comissao(request.form.get("comissao_percent", ""))
        prof.ativo = bool(request.form.get("ativo"))
        erro_disp = _aplica_disponibilidade(prof, request.form)
        if erro_disp:
            db.session.rollback()
            flash(erro_disp, "error")
            return render_template("profissionais/editar.html", prof=prof,
                                   dias_semana=DIAS_SEMANA, disp=_disp_ctx_prof(prof))
        db.session.commit()
        audit(AuditLog.ACAO_PROFISSIONAL_EDITADO, recurso_tipo="profissional",
              recurso_id=prof.id)
        flash("Profissional atualizado.", "success")
        return redirect(url_for("profissionais.listar"))

    return render_template("profissionais/editar.html", prof=prof, dias_semana=DIAS_SEMANA, disp=_disp_ctx_prof(prof))