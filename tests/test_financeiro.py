"""Testes do módulo financeiro do Nous Clinical.

Cobre acesso por papel, criação/baixa de lançamentos, recebimento integrado
da consulta (idempotente) e round-trip de valor em Numeric (sem Float).
"""
from decimal import Decimal

from app import db
from app.models import LancamentoFinanceiro, Agendamento


def test_financeiro_acesso_recepcao(client_recepcao):
    r = client_recepcao.get("/financeiro/")
    assert r.status_code == 200


def test_financeiro_bloqueia_profissional(client_prof):
    # Profissional nao acessa o financeiro -> redirect pro dashboard.
    r = client_prof.get("/financeiro/")
    assert r.status_code in (301, 302)


def test_contas_acesso_recepcao(client_recepcao):
    r = client_recepcao.get("/financeiro/contas")
    assert r.status_code == 200


def test_criar_lancamento_pago_aparece_no_fluxo(client_admin):
    r = client_admin.post("/financeiro/novo", data={
        "tipo": "receita", "valor": "250.00", "descricao": "Consulta teste",
        "categoria": "consulta", "status": "pago", "forma_pagamento": "pix",
    }, follow_redirects=True)
    assert r.status_code == 200

    lanc = LancamentoFinanceiro.query.filter_by(descricao="Consulta teste").first()
    assert lanc is not None
    assert lanc.status == "pago"
    assert lanc.pago_em is not None
    assert lanc.valor == Decimal("250.00")
    # Realizado no mes corrente -> aparece no fluxo de caixa.
    assert b"Consulta teste" in r.data


def test_pagar_lancamento_pendente(client_admin):
    client_admin.post("/financeiro/novo", data={
        "tipo": "despesa", "valor": "100.00", "descricao": "Conta pendente",
        "categoria": "insumo", "status": "pendente",
    })
    lanc = LancamentoFinanceiro.query.filter_by(descricao="Conta pendente").first()
    assert lanc.status == "pendente"
    assert lanc.pago_em is None
    lanc_id = lanc.id

    r = client_admin.post(f"/financeiro/{lanc_id}/pagar",
                          data={"forma_pagamento": "dinheiro"},
                          follow_redirects=True)
    assert r.status_code == 200

    pago = db.session.get(LancamentoFinanceiro, lanc_id)
    assert pago.status == "pago"
    assert pago.pago_em is not None
    assert pago.forma_pagamento == "dinheiro"


def test_receber_consulta_idempotente(client_admin):
    ag = Agendamento.query.first()
    ag.valor = Decimal("300.00")
    ag.status = Agendamento.STATUS_ATENDIDO
    db.session.commit()
    ag_id = ag.id

    # Dois POSTs: o segundo nao deve duplicar (unique em agendamento_id).
    client_admin.post(f"/financeiro/consulta/{ag_id}/receber",
                      data={"forma_pagamento": "pix"}, follow_redirects=True)
    client_admin.post(f"/financeiro/consulta/{ag_id}/receber",
                      data={"forma_pagamento": "pix"}, follow_redirects=True)

    lancs = LancamentoFinanceiro.query.filter_by(agendamento_id=ag_id).all()
    assert len(lancs) == 1
    assert lancs[0].status == "pago"
    assert lancs[0].valor == Decimal("300.00")
    assert lancs[0].paciente_id == ag.paciente_id


def test_valor_aceita_formato_br(client_admin):
    # Sem JS, o usuario pode digitar "1.234,56" (formato BR).
    client_admin.post("/financeiro/novo", data={
        "tipo": "receita", "valor": "1.234,56", "descricao": "Valor BR",
        "status": "pago",
    })
    lanc = LancamentoFinanceiro.query.filter_by(descricao="Valor BR").first()
    assert lanc is not None
    assert lanc.valor == Decimal("1234.56")


def test_valor_invalido_rejeitado(client_admin):
    r = client_admin.post("/financeiro/novo", data={
        "tipo": "receita", "valor": "0", "descricao": "Valor zero",
        "status": "pago",
    })
    assert r.status_code == 200  # re-renderiza o form com erro
    assert LancamentoFinanceiro.query.filter_by(descricao="Valor zero").first() is None


# --- Render das telas que integram o financeiro (pega erro de Jinja) ---

def test_form_novo_renderiza(client_admin):
    r = client_admin.get("/financeiro/novo")
    assert r.status_code == 200
    assert "lançamento".encode() in r.data.lower() or b"lan" in r.data.lower()


def test_dashboard_mostra_kpi_financeiro(client_admin):
    r = client_admin.get("/painel")
    assert r.status_code == 200
    assert "Entrada semanal".encode() in r.data


def test_paciente_detalhe_tem_historico_financeiro(client_admin):
    from app.models import Paciente
    pac = Paciente.query.first()
    r = client_admin.get(f"/pacientes/{pac.id}")
    assert r.status_code == 200
    assert "financeiro".encode() in r.data.lower()


def test_agenda_renderiza_com_pagamento(client_recepcao):
    # Consulta confirmada mostra a ação "Pagamento" (vai pro financeiro).
    from zoneinfo import ZoneInfo
    from datetime import timezone
    ag = Agendamento.query.first()
    ag.status = Agendamento.STATUS_CONFIRMADO
    db.session.commit()
    ini = ag.inicio if ag.inicio.tzinfo else ag.inicio.replace(tzinfo=timezone.utc)
    dia = ini.astimezone(ZoneInfo("America/Sao_Paulo")).date().isoformat()
    r = client_recepcao.get(f"/agenda/?dia={dia}")
    assert r.status_code == 200
    assert b"Pagamento" in r.data
