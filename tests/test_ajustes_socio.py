"""Ajustes pedidos pelo sócio: painel, agenda (atender/pagamento), CEP, filtro."""
from app import db
from app.models import Paciente, Agendamento, LancamentoFinanceiro


# ---- Painel: só os 4 KPIs combinados ----

def test_painel_kpis(client_admin):
    h = client_admin.get("/painel").data
    for txt in ["Consultas hoje", "Entrada semanal",
                "Profissionais ativos", "Pacientes ativos"]:
        assert txt.encode() in h
    assert "A receber".encode() not in h         # removido
    assert "Retornos pendentes".encode() not in h  # removido


# ---- Agenda: Atender só médico; Pagamento p/ recepção/admin ----

def _hoje_br_iso(ag):
    from zoneinfo import ZoneInfo
    from datetime import timezone
    ini = ag.inicio
    if ini.tzinfo is None:
        ini = ini.replace(tzinfo=timezone.utc)
    return ini.astimezone(ZoneInfo("America/Sao_Paulo")).date().isoformat()


def test_atender_so_medico(client_prof, client_admin):
    ag = Agendamento.query.first()
    dia = _hoje_br_iso(ag)
    assert b"Atender" in client_prof.get(f"/agenda/?dia={dia}").data
    # Admin não vê "Atender" (apenas o médico atende).
    assert b"Atender" not in client_admin.get(f"/agenda/?dia={dia}").data


def test_pagamento_link_na_agenda(client_recepcao):
    ag = Agendamento.query.first()
    ag.status = Agendamento.STATUS_CONFIRMADO
    db.session.commit()
    dia = _hoje_br_iso(ag)
    h = client_recepcao.get(f"/agenda/?dia={dia}").data
    assert b"Receber" in h
    assert b"/financeiro/novo" in h


# ---- Pagamento via financeiro pré-preenchido + vínculo com a consulta ----

def test_financeiro_novo_prefill_da_consulta(client_recepcao):
    ag = Agendamento.query.first()
    r = client_recepcao.get(f"/financeiro/novo?agendamento_id={ag.id}"
                            f"&paciente_id={ag.paciente_id}&categoria=consulta")
    assert r.status_code == 200
    assert b'name="agendamento_id"' in r.data
    # paciente vem pré-selecionado
    assert f'value="{ag.paciente_id}" selected'.encode() in r.data


def test_financeiro_novo_vincula_consulta(client_recepcao):
    ag = Agendamento.query.first()
    ag.status = Agendamento.STATUS_ATENDIDO
    db.session.commit()
    r = client_recepcao.post("/financeiro/novo", data={
        "tipo": "receita", "categoria": "consulta", "valor": "200,00",
        "status": "pago", "paciente_id": ag.paciente_id,
        "agendamento_id": ag.id, "descricao": "Consulta - teste",
    }, follow_redirects=True)
    assert r.status_code == 200
    lanc = LancamentoFinanceiro.query.filter_by(agendamento_id=ag.id).first()
    assert lanc is not None
    assert lanc.paciente_id == ag.paciente_id


# ---- Pacientes: CEP + filtro por convênio ----

def test_cep_salva(client_recepcao):
    client_recepcao.post("/pacientes/novo", data={
        "nome_completo": "Paciente CEP", "cep": "86010-000",
        "convenio": "Unimed",
    }, follow_redirects=True)
    p = Paciente.query.filter_by(nome_completo="Paciente CEP").first()
    assert p is not None
    assert p.cep == "86010-000"


def test_filtro_convenio(client_recepcao):
    db.session.add_all([
        Paciente(nome_completo="Com Unimed", convenio="Unimed"),
        Paciente(nome_completo="Com Bradesco", convenio="Bradesco"),
    ])
    db.session.commit()
    h = client_recepcao.get("/pacientes/?convenio=Unimed").data
    assert b"Com Unimed" in h
    assert b"Com Bradesco" not in h
