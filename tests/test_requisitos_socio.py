"""Cobre os requisitos consolidados pelo sócio: convênios/itens, sala,
duração configurável, restrição financeira da recepção e escopo do médico."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app import db
from app.models import (
    Convenio, Procedimento, Profissional, Paciente, Agendamento,
    LancamentoFinanceiro,
)


def _amanha_iso():
    return (datetime.now(timezone.utc).date() + timedelta(days=1)).isoformat()


# ---- Cadastro de Itens: convênios + itens (recepção) ----

def test_recepcao_cadastra_convenio(client_recepcao):
    r = client_recepcao.post("/procedimentos/adicionar",
                             data={"tipo": "convenio", "nome": "Unimed"},
                             follow_redirects=True)
    assert r.status_code == 200
    assert Convenio.query.filter_by(nome="Unimed").first() is not None


def test_convenio_duplicado_nao_cria(client_recepcao):
    client_recepcao.post("/procedimentos/adicionar",
                         data={"tipo": "convenio", "nome": "Bradesco"})
    client_recepcao.post("/procedimentos/adicionar",
                         data={"tipo": "convenio", "nome": "Bradesco"})
    assert Convenio.query.filter_by(nome="Bradesco").count() == 1


def test_recepcao_cadastra_item(client_recepcao):
    r = client_recepcao.post("/procedimentos/adicionar",
                             data={"tipo": "item", "nome": "Raio-X", "valor": "120,00"},
                             follow_redirects=True)
    assert r.status_code == 200
    p = Procedimento.query.filter_by(nome="Raio-X").first()
    assert p is not None and p.valor_padrao == Decimal("120.00")


def test_convenio_aparece_no_datalist(client_recepcao):
    client_recepcao.post("/procedimentos/adicionar",
                         data={"tipo": "convenio", "nome": "Amil"})
    # datalist global no app shell (qualquer página logada renderiza)
    r = client_recepcao.get("/pacientes/novo")
    assert b'list="convenios"' in r.data
    assert b"Amil" in r.data


# ---- Sala: puxa do profissional pro agendamento ----

def test_agendamento_puxa_sala_do_profissional(client_admin):
    prof = Profissional.query.first()
    prof.sala = "Sala 7"
    db.session.commit()
    pac = Paciente.query.first()
    client_admin.post("/agenda/novo", data={
        "paciente_id": pac.id, "profissional_id": prof.id,
        "dia": _amanha_iso(), "hora": "09:00",
    }, follow_redirects=True)
    ag = Agendamento.query.filter(Agendamento.inicio > datetime.now(timezone.utc)).first()
    assert ag is not None and ag.sala == "Sala 7"


# ---- Duração configurável (30/60/90/120) ----

def test_duracao_configuravel(client_admin):
    prof = Profissional.query.first()
    pac = Paciente.query.first()
    client_admin.post("/agenda/novo", data={
        "paciente_id": pac.id, "profissional_id": prof.id,
        "dia": _amanha_iso(), "hora": "14:00", "duracao_min": "90",
    }, follow_redirects=True)
    ag = db.session.execute(
        db.select(Agendamento).where(Agendamento.inicio > datetime.now(timezone.utc))
        .order_by(Agendamento.inicio.desc())
    ).scalars().first()
    assert ag is not None
    assert (ag.fim - ag.inicio) == timedelta(minutes=90)


# ---- Financeiro: recepção não vê/lança categorias sensíveis ----

def _despesa_aluguel():
    l = LancamentoFinanceiro(
        tipo="despesa", categoria="aluguel", valor=Decimal("3000.00"),
        status="pago", pago_em=datetime.now(timezone.utc), descricao="Aluguel")
    db.session.add(l)
    db.session.commit()
    return l


def test_recepcao_nao_ve_despesa_sensivel_no_fluxo(client_recepcao):
    _despesa_aluguel()
    r = client_recepcao.get("/financeiro/")
    assert r.status_code == 200
    assert b"Aluguel" not in r.data


def test_admin_ve_despesa_sensivel(client_admin):
    _despesa_aluguel()
    r = client_admin.get("/financeiro/")
    assert b"Aluguel" in r.data


def test_recepcao_nao_lanca_categoria_restrita(client_recepcao):
    antes = LancamentoFinanceiro.query.count()
    r = client_recepcao.post("/financeiro/novo", data={
        "tipo": "despesa", "categoria": "salario", "valor": "5000,00",
        "status": "pago",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert LancamentoFinanceiro.query.count() == antes  # não criou


# ---- Cadastro de paciente: obrigatórios + CEP ----

def test_paciente_exige_cpf_e_data(client_recepcao):
    antes = Paciente.query.count()
    client_recepcao.post("/pacientes/novo",
                         data={"nome_completo": "So Nome"}, follow_redirects=True)
    assert Paciente.query.count() == antes      # sem CPF/Data não cria


def test_cep_endpoint_valida_formato(client_recepcao):
    # CEP malformado responde 400 sem tocar a rede (não chama o ViaCEP).
    assert client_recepcao.get("/pacientes/cep/123").status_code == 400


# ---- Médico só vê os próprios pacientes ----

def test_medico_ve_so_seus_pacientes(client_prof):
    # paciente sem vínculo com o médico não aparece na lista dele
    outro = Paciente(nome_completo="Fulano Sem Vinculo", telefone="11911112222")
    db.session.add(outro)
    db.session.commit()
    r = client_prof.get("/pacientes/")
    assert r.status_code == 200
    assert b"Fulano Sem Vinculo" not in r.data
    # o paciente do agendamento do seed (que é do Dr. Teste) aparece
    assert b"Paciente Teste" in r.data
