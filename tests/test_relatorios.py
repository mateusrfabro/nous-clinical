"""Relatórios/BI v1 — acesso, faturamento, faltas, convênio, procedimentos."""
from datetime import datetime, timezone
from decimal import Decimal

from app import db
from app.models import (
    LancamentoFinanceiro, Agendamento, Atendimento, ItemAtendimento,
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
