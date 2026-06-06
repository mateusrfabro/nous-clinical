"""Relatórios/BI — acesso, faturamento, faltas, convênio, procedimentos,
receita por médico, produtividade, novos pacientes, evasão e export CSV."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app import db
from app.models import (
    LancamentoFinanceiro, Agendamento, Atendimento, ItemAtendimento,
    Paciente, Profissional,
)


def test_relatorios_gating(client_prof, client_recepcao):
    assert client_prof.get("/relatorios/").status_code in (301, 302)
    assert client_recepcao.get("/relatorios/").status_code == 200


def test_faturamento_e_convenio(client_admin):
    db.session.add_all([
        LancamentoFinanceiro(tipo="receita", categoria="consulta",
                             valor=Decimal("250.00"), status="pago",
                             pago_em=datetime.now(timezone.utc), convenio="Unimed"),
        LancamentoFinanceiro(tipo="despesa", categoria="aluguel",
                             valor=Decimal("100.00"), status="pago",
                             pago_em=datetime.now(timezone.utc)),
    ])
    db.session.commit()
    h = client_admin.get("/relatorios/").data
    assert b"Faturamento" in h
    assert b"Unimed" in h
    assert b"R$ 250,00" in h          # faturamento
    assert b"R$ 150,00" in h          # saldo (250 - 100)


def test_taxa_de_faltas(client_admin):
    ag = Agendamento.query.first()
    ag.status = Agendamento.STATUS_FALTOU
    db.session.commit()
    h = client_admin.get("/relatorios/").data
    assert b"Taxa de faltas" in h
    # 1 de 1 consulta = 100%
    assert b"100.0%" in h


def test_volume_procedimentos(client_admin):
    ag = Agendamento.query.first()
    at = Atendimento(agendamento_id=ag.id, paciente_id=ag.paciente_id,
                     profissional_id=ag.profissional_id)
    db.session.add(at)
    db.session.flush()
    at.itens.append(ItemAtendimento(descricao="Ultrassom",
                                    valor=Decimal("180.00"), quantidade=1))
    db.session.commit()
    h = client_admin.get("/relatorios/").data
    assert b"Ultrassom" in h
    assert b"R$ 180,00" in h


def test_receita_por_medico(client_admin):
    ag = Agendamento.query.first()
    nome_med = ag.profissional.nome
    db.session.add(LancamentoFinanceiro(
        tipo="receita", categoria="consulta", valor=Decimal("400.00"),
        status="pago", pago_em=datetime.now(timezone.utc),
        agendamento_id=ag.id, paciente_id=ag.paciente_id))
    db.session.commit()
    h = client_admin.get("/relatorios/").data
    assert "Receita por médico".encode() in h
    assert nome_med.encode() in h
    assert b"R$ 400,00" in h


def test_produtividade_e_novos_pacientes(client_admin):
    h = client_admin.get("/relatorios/").data
    assert "Produtividade por profissional".encode() in h
    assert "Novos pacientes".encode() in h


def test_risco_evasao_lista_paciente_sumido(client_admin):
    prof = db.session.execute(db.select(Profissional)).scalars().first()
    pac = Paciente(nome_completo="Sumido Silva", telefone="(43) 90000-7777")
    db.session.add(pac)
    db.session.flush()
    at = Atendimento(paciente_id=pac.id, profissional_id=prof.id, queixa="x")
    at.criado_em = datetime.now(timezone.utc) - timedelta(days=400)
    db.session.add(at)
    db.session.commit()
    h = client_admin.get("/relatorios/").data
    assert "Pacientes em risco de evasão".encode() in h
    assert b"Sumido Silva" in h


def test_export_csv(client_admin):
    db.session.add(LancamentoFinanceiro(
        tipo="receita", categoria="consulta", valor=Decimal("123.45"),
        status="pago", pago_em=datetime.now(timezone.utc),
        descricao="Consulta CSV"))
    db.session.commit()
    r = client_admin.get("/relatorios/export.csv")
    assert r.status_code == 200
    assert "text/csv" in r.content_type
    assert b"Consulta CSV" in r.data
    assert b"123,45" in r.data
    assert "attachment" in r.headers.get("Content-Disposition", "")


def test_export_csv_gating(client_prof):
    assert client_prof.get("/relatorios/export.csv").status_code in (301, 302)


def test_export_csv_neutraliza_formula(client_admin):
    # Descrição é texto livre -> não pode virar fórmula no Excel/Calc.
    db.session.add(LancamentoFinanceiro(
        tipo="receita", categoria="consulta", valor=Decimal("10.00"),
        status="pago", pago_em=datetime.now(timezone.utc),
        descricao="=HYPERLINK(\"http://evil\")"))
    db.session.commit()
    r = client_admin.get("/relatorios/export.csv")
    assert r.status_code == 200
    # célula perigosa prefixada com aspa simples (sem '=' iniciando a célula).
    assert b"'=HYPERLINK" in r.data
    assert b";=HYPERLINK" not in r.data
