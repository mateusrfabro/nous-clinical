"""Multi-tenant Fase 0 + Fase 1: tenant existe, seed vinculado e ISOLAMENTO
entre clínicas (escopo automático nas leituras)."""
from decimal import Decimal

from app import db
from app.models import (Clinica, Usuario, Paciente, Profissional, Agendamento,
                        Procedimento, PrecoConvenio)


def test_clinica_tenant_existe(app):
    assert Clinica.query.count() >= 1


def test_seed_vinculado_a_clinica(app):
    c = Clinica.query.first()
    assert Usuario.query.filter_by(email="admin@test.com").first().clinica_id == c.id
    assert Profissional.query.first().clinica_id == c.id
    assert Paciente.query.first().clinica_id == c.id
    assert Agendamento.query.first().clinica_id == c.id


# ---- Fase 1: isolamento entre clínicas (escopo automático) ----

def test_isolamento_lista_e_busca(client_admin):
    """Admin da clínica T não vê paciente de outra clínica (B) na lista nem
    na busca rápida — o escopo automático filtra por clinica_id."""
    cb = Clinica(nome="Clínica B", slug="b")
    db.session.add(cb)
    db.session.flush()
    db.session.add(Paciente(nome_completo="Paciente Da Clinica B",
                            telefone="11900000000", clinica_id=cb.id))
    db.session.commit()

    r = client_admin.get("/pacientes/")
    assert r.status_code == 200
    assert b"Paciente Da Clinica B" not in r.data      # lista escopada
    assert b"Paciente Teste" in r.data                 # vê os da própria clínica

    busca = client_admin.get("/buscar?q=Clinica B").get_json()
    assert busca["pacientes"] == []                    # busca não vaza


def test_criacao_herda_clinica_do_usuario(client_admin):
    # Paciente criado por admin (clínica T) nasce com a clínica dele.
    client_admin.post("/pacientes/novo",
                      data={"nome_completo": "Novo Da T", "cpf": "529.982.247-25",
                            "data_nascimento": "1990-05-10",
                            "telefone": "(43) 90000-0000", "origem": "Google"},
                      follow_redirects=True)
    p = Paciente.query.filter_by(nome_completo="Novo Da T").first()
    c = Clinica.query.filter_by(slug="teste").first()
    assert p is not None and p.clinica_id == c.id


def test_excluir_preco_de_outra_clinica_bloqueado(client_admin):
    """IDOR cross-tenant: PrecoConvenio não tem clinica_id próprio. Admin da
    clínica T NÃO pode excluir o preço de um procedimento de outra clínica."""
    cb = Clinica(nome="Clínica B Preço", slug="b-preco")
    db.session.add(cb)
    db.session.flush()
    proc = Procedimento(nome="Proc da B", valor_padrao=Decimal("100.00"),
                        clinica_id=cb.id)
    db.session.add(proc)
    db.session.flush()
    pc = PrecoConvenio(procedimento_id=proc.id, convenio="Unimed",
                       valor=Decimal("80.00"))
    db.session.add(pc)
    db.session.commit()
    preco_id = pc.id

    r = client_admin.post(f"/procedimentos/precos/{preco_id}/excluir",
                          follow_redirects=True)
    assert r.status_code == 200
    # o preço da clínica B continua existindo (exclusão foi barrada)
    assert db.session.get(PrecoConvenio, preco_id) is not None


def test_excluir_item_de_outra_clinica_bloqueado(client_admin):
    """IDOR cross-tenant: admin da clínica T NÃO pode excluir um item
    (Procedimento) de outra clínica (guarda de posse explícita em excluir)."""
    cb = Clinica(nome="Clínica B Item", slug="b-item")
    db.session.add(cb)
    db.session.flush()
    proc = Procedimento(nome="Item da B", valor_padrao=Decimal("100.00"),
                        clinica_id=cb.id)
    db.session.add(proc)
    db.session.commit()
    proc_id = proc.id
    db.session.expunge_all()        # espelha produção (sem identity map)

    r = client_admin.post(f"/procedimentos/{proc_id}/excluir",
                          follow_redirects=True)
    assert r.status_code == 200
    sem_escopo = db.session.execute(
        db.select(Procedimento).where(Procedimento.id == proc_id)
        .execution_options(ignore_tenant=True)
    ).scalars().first()
    assert sem_escopo is not None   # item da clínica B segue existindo
