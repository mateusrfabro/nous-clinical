"""Dashboard do gestor (/painel): KPIs de hoje + ocupação por profissional.

Cobre faturamento de hoje, taxa de faltas, a receber em atraso e a tabela de
ocupação — e o gating (profissional não vê os KPIs financeiros/de gestão).
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app import db
from app.models import Agendamento, LancamentoFinanceiro

_BR = ZoneInfo("America/Sao_Paulo")


def _hoje_utc(h=12, m=0):
    d = datetime.now(_BR).date()
    return datetime.combine(d, time(h, m), tzinfo=_BR).astimezone(timezone.utc)


def test_painel_admin_mostra_kpis_gestao(client_admin):
    r = client_admin.get("/painel")
    assert r.status_code == 200
    assert "Faturamento hoje".encode() in r.data
    assert "Faltas hoje".encode() in r.data


def test_painel_faturamento_hoje_soma_receita_paga(client_admin, app):
    with app.app_context():
        ag = Agendamento.query.first()
        db.session.add(LancamentoFinanceiro(
            tipo=LancamentoFinanceiro.TIPO_RECEITA,
            status=LancamentoFinanceiro.STATUS_PAGO,
            categoria="consulta", descricao="Consulta",
            valor=150, pago_em=_hoje_utc(10),
            paciente_id=ag.paciente_id, clinica_id=ag.clinica_id,
        ))
        db.session.commit()
    r = client_admin.get("/painel")
    assert r.status_code == 200
    # 150,00 formatado em BRL aparece no card de faturamento.
    assert b"150,00" in r.data


def test_painel_a_receber_atraso(client_admin, app):
    with app.app_context():
        ag = Agendamento.query.first()
        ontem = (datetime.now(_BR).date() - timedelta(days=3))
        db.session.add(LancamentoFinanceiro(
            tipo=LancamentoFinanceiro.TIPO_RECEITA,
            status=LancamentoFinanceiro.STATUS_PENDENTE,
            categoria="consulta", descricao="Consulta atrasada",
            valor=200, vencimento=ontem,
            paciente_id=ag.paciente_id, clinica_id=ag.clinica_id,
        ))
        db.session.commit()
    r = client_admin.get("/painel")
    assert r.status_code == 200
    assert "A receber em atraso".encode() in r.data
    assert b"200,00" in r.data


def test_painel_ocupacao_por_profissional(client_admin, app):
    # O seed já tem 1 consulta hoje -> a tabela de ocupação deve aparecer.
    r = client_admin.get("/painel")
    assert r.status_code == 200
    assert "Ocupação por profissional".encode() in r.data
    assert b"Dr. Teste" in r.data


def test_painel_profissional_nao_ve_kpis_gestao(client_prof):
    r = client_prof.get("/painel")
    assert r.status_code == 200
    # Profissional não vê faturamento nem ocupação cross-profissional.
    assert "Faturamento hoje".encode() not in r.data
    assert "Ocupação por profissional".encode() not in r.data
