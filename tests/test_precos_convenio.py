"""Tabela de preços por convênio: CRUD + uso no atendimento/pagamento."""
from decimal import Decimal

from app import db
from app.models import Procedimento, PrecoConvenio, Agendamento, Atendimento


def test_precos_acesso_recepcao(client_recepcao):
    # Preços por convênio fazem parte do Cadastro de Itens (recepção acessa).
    p = Procedimento(nome="Consulta", valor_padrao=Decimal("200.00"))
    db.session.add(p)
    db.session.commit()
    assert client_recepcao.get(f"/procedimentos/{p.id}/precos").status_code == 200


def test_upsert_e_excluir_preco(client_admin):
    p = Procedimento(nome="Ultrassom", valor_padrao=Decimal("180.00"))
    db.session.add(p)
    db.session.commit()
    # cria
    client_admin.post(f"/procedimentos/{p.id}/precos",
                      data={"convenio": "Unimed", "valor": "150,00"},
                      follow_redirects=True)
    p = db.session.get(Procedimento, p.id)
    assert len(p.precos) == 1
    assert p.preco_para("Unimed") == Decimal("150.00")
    # upsert (mesmo convênio atualiza, não duplica)
    client_admin.post(f"/procedimentos/{p.id}/precos",
                      data={"convenio": "Unimed", "valor": "160,00"},
                      follow_redirects=True)
    p = db.session.get(Procedimento, p.id)
    assert len(p.precos) == 1
    assert p.preco_para("Unimed") == Decimal("160.00")
    # convênio sem preço -> valor padrão
    assert p.preco_para("Bradesco") == Decimal("180.00")
    # excluir
    pc_id = p.precos[0].id
    client_admin.post(f"/procedimentos/precos/{pc_id}/excluir", follow_redirects=True)
    assert PrecoConvenio.query.count() == 0


def test_atendimento_usa_preco_do_convenio(client_prof):
    proc = Procedimento(nome="Consulta", valor_padrao=Decimal("250.00"))
    db.session.add(proc)
    db.session.flush()
    db.session.add(PrecoConvenio(procedimento_id=proc.id, convenio="Unimed",
                                 valor=Decimal("150.00")))
    ag = Agendamento.query.first()
    ag.convenio = "Unimed"
    db.session.commit()

    client_prof.post(f"/agenda/{ag.id}/atendimento",
                     data={"procedimentos": [str(proc.id)]})
    at = Atendimento.query.filter_by(agendamento_id=ag.id).one()
    # snapshot usou o preço Unimed, não o padrão
    assert at.total_itens == Decimal("150.00")
