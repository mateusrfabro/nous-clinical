"""CRUD de pacientes. Acesso: recepcao ou admin.

O prontuario clinico (Atendimento) vive em /pacientes/<id> mas so e renderizado
pra profissional/admin — a recepcao ve cadastro + agendamentos, nunca a
evolucao clinica (dado sensivel LGPD).
"""
from datetime import datetime

from flask import (
    Blueprint, render_template, redirect, url_for, flash, request,
)
from flask_login import login_required, current_user
from sqlalchemy import select, or_
from sqlalchemy.exc import IntegrityError

from app import db
from app.auth_decorators import recepcao_ou_admin
from app.models import Paciente, AuditLog
from app.services.audit import audit

pacientes_bp = Blueprint("pacientes", __name__, url_prefix="/pacientes")


def _parse_data(valor: str):
    """'YYYY-MM-DD' (input type=date) -> date | None."""
    if not valor:
        return None
    try:
        return datetime.strptime(valor, "%Y-%m-%d").date()
    except ValueError:
        return None


def _valida_cpf(raw: str):
    """Valida CPF (dígitos verificadores). Retorna (cpf_formatado|None, ok).

    Vazio -> (None, True): CPF é opcional. Malformado/inválido -> (None, False).
    """
    s = (raw or "").strip()
    if not s:
        return None, True
    d = "".join(c for c in s if c.isdigit())
    if len(d) != 11 or len(set(d)) == 1:
        return None, False

    def _dv(base):
        soma = sum(int(n) * f for n, f in zip(base, range(len(base) + 1, 1, -1)))
        resto = (soma * 10) % 11
        return 0 if resto == 10 else resto

    if _dv(d[:9]) != int(d[9]) or _dv(d[:10]) != int(d[10]):
        return None, False
    return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}", True


@pacientes_bp.route("/")
@login_required
@recepcao_ou_admin
def listar():
    busca = request.args.get("q", "").strip()
    convenio = request.args.get("convenio", "").strip()
    q = select(Paciente).where(Paciente.ativo.is_(True))
    if busca:
        termo = f"%{busca}%"
        q = q.where(or_(
            Paciente.nome_completo.ilike(termo),
            Paciente.cpf.ilike(termo),
            Paciente.telefone.ilike(termo),
        ))
    if convenio:
        q = q.where(Paciente.convenio == convenio)
    q = q.order_by(Paciente.nome_completo)
    pacientes = db.session.execute(q).scalars().all()

    # Convênios distintos (não nulos) para o filtro.
    convenios = db.session.execute(
        select(Paciente.convenio).where(
            Paciente.ativo.is_(True), Paciente.convenio.is_not(None),
            Paciente.convenio != "",
        ).distinct().order_by(Paciente.convenio)
    ).scalars().all()

    return render_template("pacientes/listar.html",
                           pacientes=pacientes, busca=busca,
                           convenios=convenios, convenio_sel=convenio)


@pacientes_bp.route("/novo", methods=["GET", "POST"])
@login_required
@recepcao_ou_admin
def novo():
    if request.method == "POST":
        nome = request.form.get("nome_completo", "").strip()
        if not nome:
            flash("Nome do paciente é obrigatório.", "error")
            return render_template("pacientes/form.html", paciente=None,
                                   form=request.form)
        cpf, cpf_ok = _valida_cpf(request.form.get("cpf", ""))
        if not cpf_ok:
            flash("CPF inválido.", "error")
            return render_template("pacientes/form.html", paciente=None,
                                   form=request.form)

        paciente = Paciente(
            nome_completo=nome,
            cpf=cpf,
            data_nascimento=_parse_data(request.form.get("data_nascimento", "")),
            sexo=request.form.get("sexo", "").strip() or None,
            telefone=request.form.get("telefone", "").strip() or None,
            email=request.form.get("email", "").strip().lower() or None,
            cep=request.form.get("cep", "").strip() or None,
            endereco=request.form.get("endereco", "").strip() or None,
            bairro=request.form.get("bairro", "").strip() or None,
            cidade=request.form.get("cidade", "").strip() or None,
            convenio=request.form.get("convenio", "").strip() or None,
            observacoes=request.form.get("observacoes", "").strip() or None,
            criado_por_id=current_user.id,
        )
        db.session.add(paciente)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Já existe um paciente com este CPF.", "error")
            return render_template("pacientes/form.html", paciente=None,
                                   form=request.form)
        audit(AuditLog.ACAO_PACIENTE_CRIADO, recurso_tipo="paciente",
              recurso_id=paciente.id)
        flash("Paciente cadastrado.", "success")
        return redirect(url_for("pacientes.detalhe", paciente_id=paciente.id))

    return render_template("pacientes/form.html", paciente=None, form={})


@pacientes_bp.route("/<int:paciente_id>")
@login_required
@recepcao_ou_admin
def detalhe(paciente_id):
    paciente = db.session.get(Paciente, paciente_id)
    if not paciente:
        flash("Paciente não encontrado.", "error")
        return redirect(url_for("pacientes.listar"))
    # Prontuario so aparece pra clinico (profissional/admin).
    pode_ver_prontuario = current_user.is_profissional or current_user.is_admin
    return render_template("pacientes/detalhe.html", paciente=paciente,
                           pode_ver_prontuario=pode_ver_prontuario)


@pacientes_bp.route("/<int:paciente_id>/editar", methods=["GET", "POST"])
@login_required
@recepcao_ou_admin
def editar(paciente_id):
    paciente = db.session.get(Paciente, paciente_id)
    if not paciente:
        flash("Paciente não encontrado.", "error")
        return redirect(url_for("pacientes.listar"))

    if request.method == "POST":
        nome = request.form.get("nome_completo", "").strip()
        if not nome:
            flash("Nome do paciente é obrigatório.", "error")
            return render_template("pacientes/form.html", paciente=paciente,
                                   form=request.form)
        cpf, cpf_ok = _valida_cpf(request.form.get("cpf", ""))
        if not cpf_ok:
            flash("CPF inválido.", "error")
            return render_template("pacientes/form.html", paciente=paciente,
                                   form=request.form)
        paciente.nome_completo = nome
        paciente.cpf = cpf
        paciente.data_nascimento = _parse_data(
            request.form.get("data_nascimento", ""))
        paciente.sexo = request.form.get("sexo", "").strip() or None
        paciente.telefone = request.form.get("telefone", "").strip() or None
        paciente.email = request.form.get("email", "").strip().lower() or None
        paciente.cep = request.form.get("cep", "").strip() or None
        paciente.endereco = request.form.get("endereco", "").strip() or None
        paciente.bairro = request.form.get("bairro", "").strip() or None
        paciente.cidade = request.form.get("cidade", "").strip() or None
        paciente.convenio = request.form.get("convenio", "").strip() or None
        paciente.observacoes = request.form.get("observacoes", "").strip() or None
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            flash("Já existe um paciente com este CPF.", "error")
            return render_template("pacientes/form.html", paciente=paciente,
                                   form=request.form)
        audit(AuditLog.ACAO_PACIENTE_EDITADO, recurso_tipo="paciente",
              recurso_id=paciente.id)
        flash("Cadastro atualizado.", "success")
        return redirect(url_for("pacientes.detalhe", paciente_id=paciente.id))

    return render_template("pacientes/form.html", paciente=paciente, form={})