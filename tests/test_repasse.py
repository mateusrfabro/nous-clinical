"""Repasse/comissão médica: edição do profissional + cálculo no relatório."""
from datetime import datetime, timezone
from decimal import Decimal

from app import db
from app.models import Profissional, Agendamento, LancamentoFinanceiro


def test_editar_profissional_seta_comissao(client_admin):
    prof = Profissional.query.first()
    r = client_admin.post(f"/profissionais/{prof.id}/editar", data={
        "nome": prof.nome, "comissao_percent": "15",
        "duracao_padrao_min": "30", "ativo": "on",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert db.session.get(Profissional, prof.id).comissao_percent == Decimal("15")


def test_editar_profissional_gating(client_recepcao):
    prof = Profissional.query.first()
    assert client_recepcao.get(f"/profissionais/{prof.id}/editar").status_code in (301, 302)


def test_repasse_calculado_no_relatorio(client_admin):
    ag = Agendamento.query.first()
    ag.profissional.comissao_percent = Decimal("20.00")
    db.session.add(LancamentoFinanceiro(
        tipo="receita", categoria="consulta", valor=Decimal("1000.00"),
        status="pago", pago_em=datetime.now(timezone.utc),
        agendamento_id=ag.id, paciente_id=ag.paciente_id))
    db.session.commit()
    r = client_admin.get("/relatorios/?gerar=1")
    assert r.status_code == 200
    assert "Repasse".encode() in r.data
    assert b"R$ 200,00" in r.data          # 20% de R$ 1.000,00


def test_parse_comissao_robusto():
    from app.routes.profissionais import _parse_comissao
    for ruim in ["nan", "Infinity", "-Infinity", "1e999", "abc", "-5"]:
        v = _parse_comissao(ruim)
        assert v.is_finite() and Decimal("0") <= v <= Decimal("100")
    assert _parse_comissao("120") == Decimal("100")
    assert _parse_comissao("15,5") == Decimal("15.5")


def test_repasse_zero_sem_comissao(client_admin):
    # Sem comissão configurada, profissional não aparece na seção de repasse.
    ag = Agendamento.query.first()
    db.session.add(LancamentoFinanceiro(
        tipo="receita", categoria="consulta", valor=Decimal("500.00"),
        status="pago", pago_em=datetime.now(timezone.utc),
        agendamento_id=ag.id, paciente_id=ag.paciente_id))
    db.session.commit()
    r = client_admin.get("/relatorios/?gerar=1")
    assert "Nenhum repasse no período".encode() in r.data
