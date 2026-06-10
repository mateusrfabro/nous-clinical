"""Melhorias/correções do 2º lote do sócio:

- convênio só por seleção (lista controlada);
- exclusão de item faturável (preserva histórico);
- telefone obrigatório + médico não cadastra paciente;
- forma de pagamento obrigatória;
- anexar exame NÃO apaga o prontuário (bug "none");
- atestado (dias + CID) + PDFs de receita/atestado;
- filtro por profissional nos relatórios.
"""
import io
from datetime import date

from app import db
from app.models import (
    Procedimento, ItemAtendimento, Atendimento, Agendamento, Paciente,
    LancamentoFinanceiro,
)

CPF_VALIDO = "529.982.247-25"


# ---- Cadastro de Itens: exclusão preserva histórico ----

def test_excluir_item_preserva_historico(client_recepcao, client_prof):
    p = Procedimento(nome="Ressonância", valor_padrao=1500)
    db.session.add(p)
    db.session.commit()
    pid = p.id
    # médico consome o item num atendimento (cria snapshot histórico)
    ag = Agendamento.query.first()
    at = Atendimento(agendamento_id=ag.id, paciente_id=ag.paciente_id,
                     profissional_id=ag.profissional_id)
    db.session.add(at)
    db.session.flush()
    db.session.add(ItemAtendimento(atendimento_id=at.id, procedimento_id=pid,
                                   descricao="Ressonância", valor=1500))
    db.session.commit()

    r = client_recepcao.post(f"/procedimentos/{pid}/excluir", follow_redirects=True)
    assert r.status_code == 200
    assert db.session.get(Procedimento, pid) is None          # item removido
    # snapshot histórico preservado (só desvinculado)
    item = ItemAtendimento.query.filter_by(descricao="Ressonância").one()
    assert item.procedimento_id is None
    assert item.valor == 1500


# ---- Pacientes: telefone obrigatório + médico bloqueado ----

def test_paciente_exige_telefone(client_recepcao):
    antes = Paciente.query.count()
    client_recepcao.post("/pacientes/novo", data={
        "nome_completo": "Sem Tel", "cpf": CPF_VALIDO,
        "data_nascimento": "1990-05-10",
    }, follow_redirects=True)
    assert Paciente.query.count() == antes              # sem telefone não cria


def test_medico_nao_cadastra_paciente(client_prof):
    # rota de cadastro é gate recepção/admin -> médico é redirecionado
    assert client_prof.get("/pacientes/novo").status_code in (301, 302)
    antes = Paciente.query.count()
    client_prof.post("/pacientes/novo", data={
        "nome_completo": "Pelo Medico", "cpf": CPF_VALIDO,
        "data_nascimento": "1990-05-10", "telefone": "11999990000",
    }, follow_redirects=True)
    assert Paciente.query.count() == antes


# ---- Financeiro: forma de pagamento obrigatória ----

def test_pago_exige_forma_pagamento(client_admin):
    antes = LancamentoFinanceiro.query.count()
    r = client_admin.post("/financeiro/novo", data={
        "tipo": "receita", "valor": "100,00", "descricao": "Sem forma",
        "status": "pago",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert LancamentoFinanceiro.query.count() == antes      # não criou sem forma


def test_baixa_exige_forma_pagamento(client_admin):
    lanc = LancamentoFinanceiro(tipo="receita", valor=100, status="pendente",
                                descricao="A receber")
    db.session.add(lanc)
    db.session.commit()
    lid = lanc.id
    client_admin.post(f"/financeiro/{lid}/pagar", data={}, follow_redirects=True)
    assert db.session.get(LancamentoFinanceiro, lid).status == "pendente"  # barrado


# ---- BUG: anexar exame não apaga queixa/evolução/prescrição ----

def _arquivo():
    return (io.BytesIO(b"%PDF-1.4 conteudo de teste"), "exame.pdf")


def test_anexar_preserva_prontuario(client_prof):
    ag = Agendamento.query.first()
    r = client_prof.post(
        f"/exames/atendimento/{ag.id}",
        data={"queixa": "dor de cabeca", "evolucao": "melhora",
              "prescricao": "dipirona", "arquivo": _arquivo()},
        content_type="multipart/form-data", follow_redirects=True)
    assert r.status_code == 200
    at = Atendimento.query.filter_by(agendamento_id=ag.id).one()
    assert at.queixa == "dor de cabeca"      # NÃO virou None/"none"
    assert at.evolucao == "melhora"
    assert at.prescricao == "dipirona"
    assert len(at.exames) == 1               # exame anexado


def test_atendimento_vazio_nao_renderiza_none(client_prof):
    ag = Agendamento.query.first()
    # cria registro vazio (upload sem texto e sem arquivo só salva o rascunho)
    client_prof.post(f"/exames/atendimento/{ag.id}", data={},
                     content_type="multipart/form-data", follow_redirects=True)
    h = client_prof.get(f"/agenda/{ag.id}/atendimento").data
    assert b"None</textarea>" not in h        # textarea vazio, não literal "None"


# ---- Atestado + PDFs ----

def _registra_atendimento(client_prof, ag, **extra):
    data = {"queixa": "q", "prescricao": "Dipirona 500mg 6/6h"}
    data.update(extra)
    return client_prof.post(f"/agenda/{ag.id}/atendimento", data=data,
                            follow_redirects=True)


def test_atestado_salva_dias_e_cid(client_prof):
    ag = Agendamento.query.first()
    _registra_atendimento(client_prof, ag, atestado_dias="3", atestado_cid="J11")
    at = Atendimento.query.filter_by(agendamento_id=ag.id).one()
    assert at.atestado_dias == 3
    assert at.atestado_cid == "J11"


def test_pdf_receita_gera(client_prof):
    ag = Agendamento.query.first()
    _registra_atendimento(client_prof, ag)
    r = client_prof.get(f"/documentos/receita/{ag.id}.pdf")
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"
    assert r.data[:5] == b"%PDF-"


def test_pdf_atestado_gera(client_prof):
    ag = Agendamento.query.first()
    _registra_atendimento(client_prof, ag, atestado_dias="5", atestado_cid="M54")
    r = client_prof.get(f"/documentos/atestado/{ag.id}.pdf")
    assert r.status_code == 200
    assert r.mimetype == "application/pdf"


def test_pdf_receita_sem_prescricao_nao_gera(client_prof):
    ag = Agendamento.query.first()
    # registra sem prescrição
    client_prof.post(f"/agenda/{ag.id}/atendimento", data={"queixa": "q"},
                     follow_redirects=True)
    r = client_prof.get(f"/documentos/receita/{ag.id}.pdf")
    # redireciona com aviso (não entrega PDF)
    assert r.status_code in (302, 200)
    assert r.mimetype != "application/pdf" or r.status_code != 200


# ---- Relatórios: filtro por profissional ----

def test_relatorio_filtro_por_profissional(client_admin):
    from app.models import Profissional
    prof = Profissional.query.first()
    hoje = date.today().isoformat()
    r = client_admin.get(
        f"/relatorios/?gerar=1&ini={hoje}&fim={hoje}&profissional_id={prof.id}")
    assert r.status_code == 200
    # sob filtro de profissional, a página avisa que despesas não se aplicam
    assert "Despesas não se aplicam".encode() in r.data
