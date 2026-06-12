"""3º lote do sócio — Fase 2/3: novos relatórios gerenciais + CRM.

Cobre:
- 3.1 Clientes e ticket médio
- 3.2 Pacientes por convênio (filtro)
- 3.3 DRE simplificado
- 3.4 Faixa etária
- 3.5 Origem de leads
- 4   CRM Aniversariantes (lista do dia, registro de interação, gate)
e o isolamento multi-tenant dos relatórios por paciente.
"""
from datetime import datetime, timezone, date
from zoneinfo import ZoneInfo

from app import db
from app.models import (
    Paciente, LancamentoFinanceiro, AuditLog, Clinica,
)

_BR = ZoneInfo("America/Sao_Paulo")
CPF_A = "529.982.247-25"
CPF_B = "168.995.350-09"


def _agora_utc():
    return datetime.now(timezone.utc)


def _receita(valor, paciente_id=None, convenio=None, categoria="consulta",
             agendamento_id=None):
    db.session.add(LancamentoFinanceiro(
        tipo="receita", categoria=categoria, valor=valor, status="pago",
        pago_em=_agora_utc(), paciente_id=paciente_id, convenio=convenio,
        agendamento_id=agendamento_id, descricao="x"))


def _despesa(valor, categoria):
    db.session.add(LancamentoFinanceiro(
        tipo="despesa", categoria=categoria, valor=valor, status="pago",
        pago_em=_agora_utc(), descricao="x"))


def _paciente(nome, cpf=None, sexo=None, nascimento=None, convenio=None,
              origem=None):
    p = Paciente(nome_completo=nome, cpf=cpf, sexo=sexo,
                 data_nascimento=nascimento, convenio=convenio, origem=origem,
                 telefone="(43) 90000-0000")
    db.session.add(p)
    db.session.flush()
    return p


# ---- 3.1 Clientes e ticket médio ----

def test_clientes_ticket_em_tela(client_admin):
    p = _paciente("Cliente Top", cpf=CPF_A, sexo="M")
    _receita(300, paciente_id=p.id)
    _receita(100, paciente_id=p.id)
    db.session.commit()
    r = client_admin.get("/relatorios/?gerar=1&tipo=clientes_ticket")
    assert r.status_code == 200
    assert "Cliente Top".encode() in r.data
    assert b"400,00" in r.data          # total gasto
    assert b"200,00" in r.data          # ticket medio (400/2)


def test_clientes_ticket_csv(client_admin):
    p = _paciente("Cliente CSV", cpf=CPF_A)
    _receita(150, paciente_id=p.id)
    db.session.commit()
    r = client_admin.get("/relatorios/clientes.csv")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    assert "Ticket Médio".encode("utf-8") in r.data
    assert b"Cliente CSV" in r.data


# ---- 3.2 Pacientes por convênio ----

def test_pacientes_por_convenio_filtra(client_admin):
    _paciente("Fulano Unimed", cpf=CPF_A, convenio="Unimed",
              nascimento=date(1990, 1, 1))
    _paciente("Beltrano Bradesco", cpf=CPF_B, convenio="Bradesco")
    db.session.commit()
    r = client_admin.get(
        "/relatorios/?gerar=1&tipo=pacientes_convenio&convenio=Unimed")
    assert r.status_code == 200
    assert "Fulano Unimed".encode() in r.data
    assert "Beltrano Bradesco".encode() not in r.data   # filtrado


def test_pacientes_por_convenio_csv(client_admin):
    _paciente("Conv CSV", cpf=CPF_A, convenio="Unimed")
    db.session.commit()
    r = client_admin.get("/relatorios/pacientes_convenio.csv?convenio=Unimed")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    assert b"Conv CSV" in r.data and b"Unimed" in r.data


# ---- 3.4 Faixa etária ----

def test_faixa_etaria_classifica(client_admin):
    _paciente("Jovem Vinte", cpf=CPF_A, sexo="F", nascimento=date(2002, 6, 1))
    db.session.commit()
    r = client_admin.get("/relatorios/?gerar=1&tipo=faixa_etaria")
    assert r.status_code == 200
    assert "Jovem Vinte".encode() in r.data
    assert b"18" in r.data                     # faixa 18-29


def test_faixa_etaria_csv(client_admin):
    _paciente("Faixa CSV", cpf=CPF_A, nascimento=date(1980, 3, 3))
    db.session.commit()
    r = client_admin.get("/relatorios/faixa_etaria.csv")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    assert b"Faixa CSV" in r.data
    assert "Faixa".encode("utf-8") in r.data


# ---- 3.5 Origem de leads ----

def test_origem_leads_percentual(client_admin):
    _paciente("Lead Insta", cpf=CPF_A, origem="Instagram")
    _paciente("Lead Goog", cpf=CPF_B, origem="Google")
    db.session.commit()
    r = client_admin.get("/relatorios/?gerar=1&tipo=origem_leads")
    assert r.status_code == 200
    assert b"Instagram" in r.data and b"Google" in r.data


def test_origem_leads_csv(client_admin):
    _paciente("Lead CSV", cpf=CPF_A, origem="Indicação")
    db.session.commit()
    r = client_admin.get("/relatorios/leads.csv")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    assert "Origem do Lead".encode("utf-8") in r.data
    assert "Indicação".encode("utf-8") in r.data


# ---- 3.3 DRE simplificado ----

def test_dre_resultado(client_admin):
    _receita(1000)
    _despesa(100, "imposto")
    _despesa(50, "insumo")
    _despesa(200, "aluguel")
    db.session.commit()
    r = client_admin.get("/relatorios/?gerar=1&tipo=dre")
    assert r.status_code == 200
    assert "Resultado Operacional".encode("utf-8") in r.data
    assert b"650,00" in r.data            # 1000 - 100 - 50 - 200


def test_dre_csv(client_admin):
    _receita(500)
    _despesa(80, "imposto")
    db.session.commit()
    r = client_admin.get("/relatorios/dre.csv")
    assert r.status_code == 200 and r.mimetype == "text/csv"
    assert "Resultado Operacional".encode("utf-8") in r.data


# ---- Seletor lista os novos relatórios ----

def test_seletor_inclui_novos_relatorios(client_admin):
    r = client_admin.get("/relatorios/")
    for chave in (b"clientes_ticket", b"pacientes_convenio", b"faixa_etaria",
                  b"origem_leads", b"dre"):
        assert chave in r.data


# ---- 4. CRM Aniversariantes ----

def test_aniversariantes_do_dia(client_admin):
    hoje = datetime.now(_BR).date()
    aniv = date(1990, hoje.month, hoje.day)
    _paciente("Aniversariante Hoje", cpf=CPF_A, nascimento=aniv)
    _paciente("Outro Dia", cpf=CPF_B,
              nascimento=date(1990, 1 if hoje.month != 1 else 2, 1))
    db.session.commit()
    r = client_admin.get("/crm/aniversariantes")
    assert r.status_code == 200
    assert "Aniversariante Hoje".encode() in r.data
    assert "Outro Dia".encode() not in r.data


def test_registrar_interacao_audita(client_admin):
    hoje = datetime.now(_BR).date()
    p = _paciente("Niver Audit", cpf=CPF_A,
                  nascimento=date(1985, hoje.month, hoje.day))
    db.session.commit()
    antes = AuditLog.query.filter_by(acao="crm_interacao").count()
    r = client_admin.post(f"/crm/aniversariantes/{p.id}/interagir",
                          follow_redirects=True)
    assert r.status_code == 200
    depois = AuditLog.query.filter_by(acao="crm_interacao").count()
    assert depois == antes + 1


def test_aniversariantes_recepcao_ok_prof_bloqueado(client_recepcao,
                                                    client_prof):
    assert client_recepcao.get("/crm/aniversariantes").status_code == 200
    assert client_prof.get("/crm/aniversariantes").status_code in (301, 302)


# ---- Regressão multi-tenant: relatório por paciente não vaza outra clínica ----

def test_clientes_ticket_isolado_entre_clinicas(client_admin):
    cb = Clinica(nome="Clínica B F2", slug="b-f2")
    db.session.add(cb)
    db.session.flush()
    pb = Paciente(nome_completo="SegredoPacienteB", cpf=CPF_B,
                  telefone="x", clinica_id=cb.id)
    db.session.add(pb)
    db.session.flush()
    db.session.add(LancamentoFinanceiro(
        tipo="receita", categoria="consulta", valor=88888, status="pago",
        pago_em=_agora_utc(), paciente_id=pb.id, clinica_id=cb.id,
        descricao="x"))
    db.session.commit()
    db.session.expunge_all()

    tela = client_admin.get(
        "/relatorios/?gerar=1&tipo=clientes_ticket").data
    assert b"SegredoPacienteB" not in tela and b"88.888" not in tela
    conv = client_admin.get(
        "/relatorios/?gerar=1&tipo=pacientes_convenio").data
    assert b"SegredoPacienteB" not in conv
