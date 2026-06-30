"""Fechamento de caixa diário: esperado por forma, fechar, divergência, reabrir."""
import json
from datetime import datetime, time, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app import db
from app.models import LancamentoFinanceiro, FechamentoCaixa

_BR = ZoneInfo("America/Sao_Paulo")


def _hoje_br():
    return datetime.now(_BR).date()


def _receita_paga(valor, forma):
    d = _hoje_br()
    pago = datetime.combine(d, time(12, 0), tzinfo=_BR).astimezone(timezone.utc)
    return LancamentoFinanceiro(
        tipo=LancamentoFinanceiro.TIPO_RECEITA,
        status=LancamentoFinanceiro.STATUS_PAGO, categoria="consulta",
        descricao="Consulta", valor=Decimal(valor), forma_pagamento=forma,
        pago_em=pago)


def test_caixa_acesso(client_prof, client_admin):
    assert client_prof.get("/financeiro/caixa").status_code in (301, 302, 403)
    assert client_admin.get("/financeiro/caixa").status_code == 200


def test_caixa_esperado_por_forma(client_admin, app):
    with app.app_context():
        db.session.add(_receita_paga("100.00", "dinheiro"))
        db.session.add(_receita_paga("50.00", "pix"))
        db.session.commit()
    r = client_admin.get("/financeiro/caixa")
    assert r.status_code == 200
    assert b"150,00" in r.data   # esperado total


def test_caixa_fechar_com_divergencia(client_admin, app):
    with app.app_context():
        db.session.add(_receita_paga("100.00", "dinheiro"))
        db.session.add(_receita_paga("50.00", "pix"))
        db.session.commit()
    dia = _hoje_br().isoformat()
    r = client_admin.post("/financeiro/caixa/fechar", data={
        "dia": dia,
        "contado_dinheiro": "100.00",
        "contado_pix": "40.00",   # faltou 10
        "observacoes": "sangria 10",
    }, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        f = FechamentoCaixa.query.filter_by().first()
        assert f is not None
        assert f.esperado_total == Decimal("150.00")
        assert f.contado_total == Decimal("140.00")
        assert f.divergencia == Decimal("-10.00")
        det = json.loads(f.detalhes)
        assert det["pix"]["esperado"] == "50.00"
        assert det["pix"]["contado"] == "40.00"
        assert f.observacoes == "sangria 10"


def test_caixa_esperado_recalculado_no_servidor(client_admin, app):
    """O esperado vem do banco, não do cliente: contado não altera o esperado."""
    with app.app_context():
        db.session.add(_receita_paga("200.00", "dinheiro"))
        db.session.commit()
    dia = _hoje_br().isoformat()
    client_admin.post("/financeiro/caixa/fechar", data={
        "dia": dia, "contado_dinheiro": "999.00",
    }, follow_redirects=True)
    with app.app_context():
        f = FechamentoCaixa.query.first()
        assert f.esperado_total == Decimal("200.00")   # não 999
        assert f.divergencia == Decimal("799.00")


def test_caixa_reabrir(client_admin, app):
    dia = _hoje_br().isoformat()
    client_admin.post("/financeiro/caixa/fechar",
                      data={"dia": dia}, follow_redirects=True)
    with app.app_context():
        f = FechamentoCaixa.query.first()
        assert f is not None
        fid = f.id
    client_admin.post(f"/financeiro/caixa/{fid}/reabrir", follow_redirects=True)
    with app.app_context():
        assert db.session.get(FechamentoCaixa, fid) is None


def test_caixa_refechar_atualiza(client_admin, app):
    """Fechar de novo no mesmo dia atualiza (não duplica — unique por dia)."""
    dia = _hoje_br().isoformat()
    client_admin.post("/financeiro/caixa/fechar",
                      data={"dia": dia, "contado_dinheiro": "10"},
                      follow_redirects=True)
    client_admin.post("/financeiro/caixa/fechar",
                      data={"dia": dia, "contado_dinheiro": "20"},
                      follow_redirects=True)
    with app.app_context():
        assert FechamentoCaixa.query.count() == 1
