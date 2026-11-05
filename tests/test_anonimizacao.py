"""Anonimização de paciente — LGPD art. 18 (custo-zero)."""
from datetime import date, datetime, timezone
from decimal import Decimal

from app import db
from app.models import (Paciente, Atendimento, Exame, LancamentoFinanceiro,
                        Profissional)


def _paciente_rico():
    """Cria um paciente com PII + prontuário + exame + financeiro."""
    prof = Profissional.query.first()
    pac = Paciente(nome_completo="João Sensível", cpf="999.999.999-99",
                   telefone="(43) 90000-1111", email="joao@ex.com",
                   endereco="Rua X, 10", observacoes="nota privada")
    db.session.add(pac)
    db.session.flush()
    at = Atendimento(paciente_id=pac.id, profissional_id=prof.id,
                     queixa="dor de cabeça", evolucao="quadro estável",
                     prescricao="dipirona", retorno_em=date.today())
    db.session.add(at)
    db.session.flush()
    db.session.add(Exame(atendimento_id=at.id, paciente_id=pac.id,
                         nome_original="exame.pdf", arquivo_key="exames/fake.pdf",
                         content_type="application/pdf", tamanho=10))
    lanc = LancamentoFinanceiro(
        tipo="receita", categoria="consulta",
        descricao="Consulta - João Sensível", valor=Decimal("250.00"),
        status="pago", pago_em=datetime.now(timezone.utc), paciente_id=pac.id)
    db.session.add(lanc)
    db.session.commit()
    return pac.id, lanc.id


def test_anonimizar_remove_pii_e_clinico_preserva_financeiro(client_admin, app):
    with app.app_context():
        pid, lid = _paciente_rico()
    r = client_admin.post(f"/pacientes/{pid}/anonimizar",
                          data={"confirmacao": "ANONIMIZAR"}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        pac = db.session.get(Paciente, pid)
        assert pac.anonimizado_em is not None
        assert pac.cpf is None and pac.email is None and pac.telefone is None
        assert pac.endereco is None and pac.observacoes is None
        assert "removido" in pac.nome_completo.lower()
        # prontuário clínico apagado
        at = Atendimento.query.filter_by(paciente_id=pid).first()
        assert at.queixa is None and at.evolucao is None and at.prescricao is None
        # exame (arquivo sensível) removido
        assert Exame.query.filter_by(paciente_id=pid).count() == 0
        # financeiro PRESERVADO (valor/data), mas sem o nome na descrição
        lanc = db.session.get(LancamentoFinanceiro, lid)
        assert lanc is not None and lanc.valor == Decimal("250.00")
        assert "Sensível" not in (lanc.descricao or "")


def test_anonimizar_exige_palavra_confirmacao(client_admin, app):
    with app.app_context():
        pid, _ = _paciente_rico()
    client_admin.post(f"/pacientes/{pid}/anonimizar",
                      data={"confirmacao": "sim"}, follow_redirects=True)
    with app.app_context():
        assert db.session.get(Paciente, pid).anonimizado_em is None   # não anonimizou


def test_anonimizar_negado_para_recepcao(client_recepcao, app):
    with app.app_context():
        pid, _ = _paciente_rico()
    r = client_recepcao.post(f"/pacientes/{pid}/anonimizar",
                             data={"confirmacao": "ANONIMIZAR"})
    assert r.status_code in (302, 403)
    with app.app_context():
        assert db.session.get(Paciente, pid).anonimizado_em is None
