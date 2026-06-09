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
from app.auth_decorators import recepcao_ou_admin, equipe_required
from app.models import Paciente, Agendamento, AuditLog
from app.services.audit import audit

pacientes_bp = Blueprint("pacientes", __name__, url_prefix="/pacientes")


def _ids_pacientes_do_profissional():
    """IDs dos pacientes que o profissional logado atende (tem agendamento com
    ele). Usado pra limitar a visão do médico aos seus próprios pacientes."""
    prof = current_user.profissional
    if not prof:
        return []
    return db.session.execute(
        select(Agendamento.paciente_id)
        .where(Agendamento.profissional_id == prof.id).distinct()
    ).scalars().all()


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


def _valida_obrigatorios(form):
    """Nome, CPF e Data de nascimento são obrigatórios (req. do sócio).

    Retorna (nome, cpf_formatado, data, erro|None)."""
    nome = form.get("nome_completo", "").strip()
    cpf_raw = (form.get("cpf", "") or "").strip()
    data = _parse_data(form.get("data_nascimento", ""))
    if not nome:
        return nome, None, data, "Nome do paciente é obrigatório."
    if not cpf_raw:
        return nome, None, data, "CPF é obrigatório."
    cpf, ok = _valida_cpf(cpf_raw)
    if not ok:
        return nome, None, data, "CPF inválido."
    if not data:
        return nome, cpf, None, "Data de nascimento é obrigatória."
    return nome, cpf, data, None


@pacientes_bp.route("/")
@login_required
@equipe_required
def listar():
    busca = request.args.get("q", "").strip()
    convenio = request.args.get("convenio", "").strip()
    q = select(Paciente).where(Paciente.ativo.is_(True))
    # Médico só enxerga os pacientes que ele atende (req. do sócio).
    if current_user.is_profissional:
        q = q.where(Paciente.id.in_(_ids_pacientes_do_profissional()))
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
        nome, cpf, data_nasc, erro = _valida_obrigatorios(request.form)
        if erro:
            flash(erro, "error")
            return render_template("pacientes/form.html", paciente=None,
                                   form=request.form)

        paciente = Paciente(
            nome_completo=nome,
            cpf=cpf,
            data_nascimento=data_nasc,
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
@equipe_required
def detalhe(paciente_id):
    paciente = db.session.get(Paciente, paciente_id)
    if not paciente:
        flash("Paciente não encontrado.", "error")
        return redirect(url_for("pacientes.listar"))
    # Médico só abre o paciente se for um dos seus (atende/agenda com ele).
    if current_user.is_profissional and \
            paciente_id not in _ids_pacientes_do_profissional():
        flash("Você só tem acesso aos seus próprios pacientes.", "error")
        return redirect(url_for("pacientes.listar"))
    # Prontuario so aparece pra clinico (profissional/admin).
    pode_ver_prontuario = current_user.is_profissional or current_user.is_admin
    return render_template("pacientes/detalhe.html", paciente=paciente,
                           pode_ver_prontuario=pode_ver_prontuario)


@pacientes_bp.route("/cep/<cep>")
@login_required
@recepcao_ou_admin
def buscar_cep(cep):
    """Proxy ViaCEP (server-side) p/ autopreenchimento de endereço.

    Feito no backend (não no browser) pra manter a CSP estrita — o JS chama
    nosso próprio endpoint ('self'). Sem SSRF: host fixo, só dígitos do CEP."""
    import json
    import urllib.request
    from flask import jsonify

    d = "".join(c for c in (cep or "") if c.isdigit())
    if len(d) != 8:
        return jsonify({"erro": "cep_invalido"}), 400
    try:
        # Host fixo https + só 8 dígitos interpolados (sem esquema/host do
        # usuário) -> sem SSRF. nosec: B310 é falso-positivo aqui.
        url = f"https://viacep.com.br/ws/{d}/json/"
        if not url.startswith("https://viacep.com.br/"):   # guarda redundante
            return jsonify({"erro": "cep_invalido"}), 400
        with urllib.request.urlopen(url, timeout=4) as resp:  # nosec B310
            dados = json.loads(resp.read().decode("utf-8"))
    except Exception:
        return jsonify({"erro": "falha_consulta"}), 502
    if dados.get("erro"):
        return jsonify({"erro": "nao_encontrado"}), 404
    return jsonify({
        "endereco": dados.get("logradouro", ""),
        "bairro": dados.get("bairro", ""),
        "cidade": dados.get("localidade", ""),
        "uf": dados.get("uf", ""),
    })


@pacientes_bp.route("/<int:paciente_id>/editar", methods=["GET", "POST"])
@login_required
@recepcao_ou_admin
def editar(paciente_id):
    paciente = db.session.get(Paciente, paciente_id)
    if not paciente:
        flash("Paciente não encontrado.", "error")
        return redirect(url_for("pacientes.listar"))

    if request.method == "POST":
        nome, cpf, data_nasc, erro = _valida_obrigatorios(request.form)
        if erro:
            flash(erro, "error")
            return render_template("pacientes/form.html", paciente=paciente,
                                   form=request.form)
        paciente.nome_completo = nome
        paciente.cpf = cpf
        paciente.data_nascimento = data_nasc
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