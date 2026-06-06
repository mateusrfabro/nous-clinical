"""CRM Retorno — registro do retorno no atendimento + painel de pendentes."""
from datetime import date, timedelta

from app import db
from app.models import Atendimento, Agendamento, Paciente, Profissional


def _agendamento_existente():
    return db.session.execute(db.select(Agendamento)).scalars().first()


def test_atendimento_grava_retorno_em(client_prof):
    ag = _agendamento_existente()
    r = client_prof.post(f"/agenda/{ag.id}/atendimento", data={
        "queixa": "x", "evolucao": "y", "prescricao": "z",
        "retorno_opcao": "30",
    }, follow_redirects=True)
    assert r.status_code == 200
    at = db.session.execute(
        db.select(Atendimento).where(Atendimento.agendamento_id == ag.id)
    ).scalar_one()
    assert at.retorno_em == date.today() + timedelta(days=30)


def test_retornos_acesso_por_papel(client_prof, client_recepcao):
    # Profissional não acessa o CRM; recepção sim.
    assert client_prof.get("/crm/retornos").status_code in (301, 302)
    assert client_recepcao.get("/crm/retornos").status_code == 200


def test_painel_lista_retorno_vencido_sem_reagendamento(client_admin, app):
    # Cria um atendimento com retorno vencido p/ um paciente novo (sem consulta futura).
    pac = Paciente(nome_completo="Retorno Teste", telefone="(43) 90000-1234")
    db.session.add(pac)
    prof = db.session.execute(db.select(Profissional)).scalars().first()
    db.session.flush()
    db.session.add(Atendimento(
        paciente_id=pac.id, profissional_id=prof.id,
        retorno_em=date.today() - timedelta(days=5),
    ))
    db.session.commit()

    r = client_admin.get("/crm/retornos?dias=0")
    assert r.status_code == 200
    assert b"Retorno Teste" in r.data
    assert b"Vencido" in r.data
    # Link de WhatsApp gerado a partir do telefone.
    assert b"wa.me/" in r.data


def test_paciente_com_consulta_futura_sai_do_painel(client_admin, app):
    from datetime import datetime, timezone
    pac = Paciente(nome_completo="Ja Reagendou", telefone="(43) 90000-5678")
    db.session.add(pac)
    prof = db.session.execute(db.select(Profissional)).scalars().first()
    db.session.flush()
    db.session.add(Atendimento(
        paciente_id=pac.id, profissional_id=prof.id,
        retorno_em=date.today() - timedelta(days=2),
    ))
    # Consulta futura -> nao deve aparecer como pendente.
    futuro = datetime.now(timezone.utc) + timedelta(days=3)
    db.session.add(Agendamento(
        paciente_id=pac.id, profissional_id=prof.id,
        inicio=futuro, fim=futuro + timedelta(minutes=30),
        status=Agendamento.STATUS_AGENDADO,
    ))
    db.session.commit()

    r = client_admin.get("/crm/retornos?dias=0")
    assert b"Ja Reagendou" not in r.data


def test_perde_flag_ao_se_consultar(client_admin, app):
    from datetime import datetime, timezone
    pac = Paciente(nome_completo="Voltou Sem Flag", telefone="(43) 90000-9999")
    db.session.add(pac)
    prof = db.session.execute(db.select(Profissional)).scalars().first()
    db.session.flush()
    # Atendimento antigo com retorno vencido...
    a1 = Atendimento(paciente_id=pac.id, profissional_id=prof.id,
                     retorno_em=date.today() - timedelta(days=10))
    a1.criado_em = datetime.now(timezone.utc) - timedelta(days=1)
    # ...e um mais recente SEM retorno (consultou de novo, médico não marcou).
    a2 = Atendimento(paciente_id=pac.id, profissional_id=prof.id, retorno_em=None)
    a2.criado_em = datetime.now(timezone.utc)
    db.session.add_all([a1, a2])
    db.session.commit()

    r = client_admin.get("/crm/retornos?dias=0")
    assert b"Voltou Sem Flag" not in r.data  # último atendimento não tem flag


def test_crm_no_menu_lateral(client_admin):
    # KPI de retornos saiu do painel; CRM permanece no menu lateral.
    r = client_admin.get("/painel")
    assert r.status_code == 200
    assert b'href="/crm/retornos"' in r.data
    assert b">CRM<" in r.data
