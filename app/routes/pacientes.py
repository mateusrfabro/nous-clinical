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


@pacientes_bp.route("/")
@login_required
@recepcao_ou_admin
def listar():
    busca = request.args.get("q", "").strip()
    q = select(Paciente).where(Paciente.ativo.is_(True))
    if busca:
        termo = f"%{busca}%"
        q = q.where(or_(
            Paciente.nome_completo.ilike(termo),
            Paciente.cpf.ilike(termo),
            Paciente.telefone.ilike(termo),
        ))
    q = q.order_by(Paciente.nome_completo)
    pacientes = db.session.execute(q).scalars().all()
    return render_template("pacientes/listar.html",
                           pacientes=pacientes, busca=busca)


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

        paciente = Paciente(
            nome_completo=nome,
            cpf=request.form.get("cpf", "").strip() or None,
            data_nascimento=_parse_data(request.form.get("data_nascimento", "")),
            sexo=request.form.get("sexo", "").strip() or None,
            telefone=request.form.get("telefone", "").strip() or None,
            email=request.form.get("email", "").strip().lower() or None,
            endereco=request.form.get("endereco", "").strip() or None,
            bairro=request.form.get("bairro", "").strip() or None,
            cidade=request.form.get("cidade", "").strip() or None,
            convenio=request.form.get("convenio", "").strip() or None,
            observacoes=request.form.get("observacoes", "").strip() or None,
            criado_por_id=current_user.id,
        )
        db.session.add(paciente)
        db.session.commit()
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
        paciente.nome_completo = nome
        paciente.cpf = request.form.get("cpf", "").strip() or None
        paciente.data_nascimento = _parse_data(
            request.form.get("data_nascimento", ""))
        paciente.sexo = request.form.get("sexo", "").strip() or None
        paciente.telefone = request.form.get("telefone", "").strip() or None
        paciente.email = request.form.get("email", "").strip().lower() or None
        paciente.endereco = request.form.get("endereco", "").strip() or None
        paciente.bairro = request.form.get("bairro", "").strip() or None
        paciente.cidade = request.form.get("cidade", "").strip() or None
        paciente.convenio = request.form.get("convenio", "").strip() or None
        paciente.observacoes = request.form.get("observacoes", "").strip() or None
        db.session.commit()
        audit(AuditLog.ACAO_PACIENTE_EDITADO, recurso_tipo="paciente",
              recurso_id=paciente.id)
        flash("Cadastro atualizado.", "success")
        return redirect(url_for("pacientes.detalhe", paciente_id=paciente.id))

    return render_template("pacientes/form.html", paciente=paciente, form={})