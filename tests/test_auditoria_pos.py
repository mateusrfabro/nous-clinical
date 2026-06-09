"""Testes negativos/regressão dos achados da auditoria multi-agente.

Cobre: IDOR cross-tenant em busca por PK (agendamento/lançamento), bloqueio da
recepção sobre despesas restritas em pagar/cancelar, médico não grava
atendimento de agenda alheia, profissional órfão (sem cadastro) barrado no
prontuário, criação de profissional + herança de clinica_id, cancelar
lançamento, duração inválida, formato de logo e reset de lembrete ao reagendar.
"""
import hashlib
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from io import BytesIO

from sqlalchemy import select

from app import db
from app.models import (
    Clinica, Usuario, Profissional, Paciente, Agendamento, Atendimento,
    LancamentoFinanceiro,
)
from app.services.passwords import hash_senha


def _sem_escopo(modelo, pk):
    """Busca por PK ignorando o escopo de tenant (verificação de teste — o
    g.clinica_id do request anterior fica pendurado no app_context do conftest)."""
    return db.session.execute(
        select(modelo).where(modelo.id == pk).execution_options(ignore_tenant=True)
    ).scalar_one_or_none()

_PNG_1x1 = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00'
            b'\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82')


def _login(app, email):
    u = Usuario.query.filter_by(email=email).first()
    c = app.test_client()
    sid = hashlib.sha512(f"test-{u.id}".encode()).hexdigest()
    with c.session_transaction() as s:
        s["_user_id"] = str(u.id)
        s["_fresh"] = True
        s["_id"] = sid
        s["_permanent"] = True
    return c


def _amanha():
    return (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()


def _clinica_b_com_agendamento():
    """Cria clínica B isolada com paciente/profissional/agendamento."""
    cb = Clinica(nome="Clínica B IDOR", slug="b-idor")
    db.session.add(cb)
    db.session.flush()
    ub = Usuario(email="profb@idor.com", senha_hash=hash_senha("x"),
                 nome_responsavel="Prof B", tipo="profissional", clinica_id=cb.id)
    db.session.add(ub)
    db.session.flush()
    pb = Profissional(usuario_id=ub.id, nome="Prof B", clinica_id=cb.id)
    pac = Paciente(nome_completo="Paciente B", clinica_id=cb.id)
    db.session.add_all([pb, pac])
    db.session.flush()
    ini = datetime.combine(datetime.now(timezone.utc).date() + timedelta(days=1),
                           time(15, 0), tzinfo=timezone.utc)
    ag = Agendamento(paciente_id=pac.id, profissional_id=pb.id, inicio=ini,
                     fim=ini + timedelta(minutes=30),
                     status=Agendamento.STATUS_AGENDADO, clinica_id=cb.id)
    db.session.add(ag)
    db.session.commit()
    return cb, ag


# ---- IDOR cross-tenant em busca por PK (expunge_all -> get a frio = produção) ----

def test_idor_agendamento_status_cross_tenant(client_admin, app):
    cb, ag = _clinica_b_com_agendamento()
    ag_id = ag.id
    db.session.expunge_all()                 # força SELECT a frio (sem identity map)
    client_admin.post(f"/agenda/{ag_id}/status",
                      data={"status": "confirmado"}, follow_redirects=True)
    # agendamento da clínica B segue intacto (escopo bloqueou)
    assert _sem_escopo(Agendamento, ag_id).status == Agendamento.STATUS_AGENDADO


def test_idor_financeiro_pagar_cross_tenant(client_admin, app):
    cb = Clinica(nome="Clínica B Fin", slug="b-fin")
    db.session.add(cb)
    db.session.flush()
    lanc = LancamentoFinanceiro(
        tipo="receita", categoria="consulta", valor=Decimal("100.00"),
        status="pendente", clinica_id=cb.id)
    db.session.add(lanc)
    db.session.commit()
    lid = lanc.id
    db.session.expunge_all()
    client_admin.post(f"/financeiro/{lid}/pagar", follow_redirects=True)
    assert _sem_escopo(LancamentoFinanceiro, lid).status == "pendente"


# ---- Recepção não paga/cancela despesa restrita ----

def _despesa_restrita():
    lanc = LancamentoFinanceiro(tipo="despesa", categoria="salario",
                                valor=Decimal("5000.00"), status="pendente")
    db.session.add(lanc)
    db.session.commit()
    return lanc


def test_recepcao_nao_paga_despesa_restrita(client_recepcao):
    lanc = _despesa_restrita()
    r = client_recepcao.post(f"/financeiro/{lanc.id}/pagar")
    assert r.status_code == 403
    assert db.session.get(LancamentoFinanceiro, lanc.id).status == "pendente"


def test_recepcao_nao_cancela_despesa_restrita(client_recepcao):
    lanc = _despesa_restrita()
    r = client_recepcao.post(f"/financeiro/{lanc.id}/cancelar")
    assert r.status_code == 403
    assert db.session.get(LancamentoFinanceiro, lanc.id).status == "pendente"


# ---- Médico não grava atendimento de agenda de outro médico ----

def test_medico_nao_registra_atendimento_alheio(client_prof, app):
    u2 = Usuario(email="dr2@test.com", senha_hash=hash_senha("x"),
                 nome_responsavel="Dr. Dois", tipo="profissional")
    db.session.add(u2)
    db.session.flush()
    clinica = Clinica.query.first()
    u2.clinica_id = clinica.id
    p2 = Profissional(usuario_id=u2.id, nome="Dr. Dois", clinica_id=clinica.id)
    db.session.add(p2)
    db.session.flush()
    pac = Paciente.query.first()
    ini = datetime.combine(datetime.now(timezone.utc).date(), time(16, 0),
                           tzinfo=timezone.utc)
    ag = Agendamento(paciente_id=pac.id, profissional_id=p2.id, inicio=ini,
                     fim=ini + timedelta(minutes=30),
                     status=Agendamento.STATUS_AGENDADO, clinica_id=clinica.id)
    db.session.add(ag)
    db.session.commit()
    # client_prof é o Dr. Teste; o agendamento é do Dr. Dois
    client_prof.post(f"/agenda/{ag.id}/atendimento",
                     data={"queixa": "invasao"}, follow_redirects=True)
    assert Atendimento.query.filter_by(agendamento_id=ag.id).first() is None


def test_profissional_sem_cadastro_barrado_no_prontuario(client_prof, app):
    # Usuario tipo=profissional SEM registro Profissional -> check_cadastro barra.
    u = Usuario(email="orfao@test.com", senha_hash=hash_senha("x"),
                nome_responsavel="Órfão", tipo="profissional",
                clinica_id=Clinica.query.first().id)
    db.session.add(u)
    db.session.commit()
    c = _login(app, "orfao@test.com")
    ag = Agendamento.query.first()
    r = c.get(f"/agenda/{ag.id}/atendimento")
    assert r.status_code in (301, 302)         # redirecionado (sem cadastro)


# ---- Criação de profissional + herança de clinica_id ----

def test_admin_cria_profissional(client_admin):
    r = client_admin.post("/profissionais/novo", data={
        "nome": "Dra. Nova", "email": "dra.nova@test.com",
        "senha": "senha1234", "especialidade": "Clínica Geral",
    }, follow_redirects=True)
    assert r.status_code == 200
    u = Usuario.query.filter_by(email="dra.nova@test.com").first()
    assert u is not None and u.tipo == "profissional"
    prof = Profissional.query.filter_by(usuario_id=u.id).first()
    clinica = Clinica.query.filter_by(slug="teste").first()
    assert prof is not None and prof.clinica_id == clinica.id
    assert u.clinica_id == clinica.id


# ---- Cancelar lançamento (caminho feliz) ----

def test_cancelar_lancamento(client_admin):
    lanc = LancamentoFinanceiro(tipo="receita", categoria="consulta",
                                valor=Decimal("80.00"), status="pendente")
    db.session.add(lanc)
    db.session.commit()
    client_admin.post(f"/financeiro/{lanc.id}/cancelar", follow_redirects=True)
    assert db.session.get(LancamentoFinanceiro, lanc.id).status == \
        LancamentoFinanceiro.STATUS_CANCELADO


# ---- Duração inválida cai no padrão ----

def test_duracao_invalida_usa_padrao(client_admin):
    prof = Profissional.query.first()
    pac = Paciente.query.first()
    client_admin.post("/agenda/novo", data={
        "paciente_id": pac.id, "profissional_id": prof.id,
        "dia": _amanha(), "hora": "08:00", "duracao_min": "45",  # fora do set
    }, follow_redirects=True)
    ag = db.session.execute(
        db.select(Agendamento).where(Agendamento.inicio > datetime.now(timezone.utc))
        .order_by(Agendamento.inicio.desc())
    ).scalars().first()
    padrao = prof.duracao_padrao_min or 30
    assert (ag.fim - ag.inicio) == timedelta(minutes=padrao)


# ---- Logo rejeita formato não suportado (além do SVG) ----

def test_logo_rejeita_formato_nao_suportado(client_admin):
    client_admin.post("/configuracoes/logo",
                      data={"logo": (BytesIO(_PNG_1x1), "x.gif")},
                      content_type="multipart/form-data", follow_redirects=True)
    assert Clinica.query.filter_by(slug="teste").first().logo_key is None


# ---- Reagendar reseta lembrete_enviado_em (regressão do P1) ----

def test_reagendar_reseta_lembrete(client_admin):
    ag = Agendamento.query.first()
    ag.lembrete_enviado_em = datetime.now(timezone.utc)
    db.session.commit()
    client_admin.post(f"/agenda/{ag.id}/editar", data={
        "profissional_id": ag.profissional_id, "dia": _amanha(), "hora": "10:00",
    }, follow_redirects=True)
    assert db.session.get(Agendamento, ag.id).lembrete_enviado_em is None
