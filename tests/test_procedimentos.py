"""Catálogo de procedimentos + flagbox no atendimento -> total no pagamento."""
from decimal import Decimal

from app import db
from app.models import Procedimento, Agendamento, Atendimento


def _dois_procedimentos():
    p1 = Procedimento(nome="Consulta", valor_padrao=Decimal("200.00"))
    p2 = Procedimento(nome="Ultrassom", valor_padrao=Decimal("150.00"))
    db.session.add_all([p1, p2])
    db.session.commit()
    return p1, p2


# ---- Catálogo (admin) ----

def test_procedimentos_so_admin(client_recepcao, client_prof):
    assert client_recepcao.get("/procedimentos/").status_code in (301, 302)
    assert client_prof.get("/procedimentos/").status_code in (301, 302)


def test_admin_cria_e_edita_procedimento(client_admin):
    r = client_admin.post("/procedimentos/novo",
                          data={"nome": "Eletro", "valor": "90,00"},
                          follow_redirects=True)
    assert r.status_code == 200
    p = Procedimento.query.filter_by(nome="Eletro").first()
    assert p is not None and p.valor_padrao == Decimal("90.00")
    # edita preço + inativa
    client_admin.post(f"/procedimentos/{p.id}",
                      data={"nome": "Eletro", "valor": "110,00"},
                      follow_redirects=True)
    p = db.session.get(Procedimento, p.id)
    assert p.valor_padrao == Decimal("110.00")
    assert p.ativo is False  # checkbox 'ativo' ausente => desmarcado


# ---- Flagbox no atendimento ----

def test_atendimento_salva_itens(client_prof):
    p1, p2 = _dois_procedimentos()
    ag = Agendamento.query.first()
    r = client_prof.post(f"/agenda/{ag.id}/atendimento", data={
        "queixa": "x", "procedimentos": [str(p1.id), str(p2.id)],
    }, follow_redirects=True)
    assert r.status_code == 200
    at = Atendimento.query.filter_by(agendamento_id=ag.id).one()
    assert len(at.itens) == 2
    assert at.total_itens == Decimal("350.00")


def test_reeditar_atendimento_substitui_itens(client_prof):
    p1, p2 = _dois_procedimentos()
    ag = Agendamento.query.first()
    client_prof.post(f"/agenda/{ag.id}/atendimento",
                     data={"procedimentos": [str(p1.id), str(p2.id)]})
    # regrava só com 1 item
    client_prof.post(f"/agenda/{ag.id}/atendimento",
                     data={"procedimentos": [str(p1.id)]})
    at = Atendimento.query.filter_by(agendamento_id=ag.id).one()
    assert len(at.itens) == 1
    assert at.total_itens == Decimal("200.00")


# ---- Pagamento puxa itens automaticamente ----

def test_pagamento_puxa_total_e_descricao(client_prof, client_recepcao):
    p1, p2 = _dois_procedimentos()
    ag = Agendamento.query.first()
    client_prof.post(f"/agenda/{ag.id}/atendimento",
                     data={"procedimentos": [str(p1.id), str(p2.id)]})
    r = client_recepcao.get(f"/financeiro/novo?agendamento_id={ag.id}")
    assert r.status_code == 200
    assert b'value="350.00"' in r.data
    assert b"Consulta + Ultrassom" in r.data
