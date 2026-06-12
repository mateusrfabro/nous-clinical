"""Testes negativos das correções da auditoria multi-agente.

Cobre: vazamento de prontuário entre profissionais (P0), CPF duplicado/inválido,
agendar/reagendar no passado, e recepção marcando/reverteendo 'atendido'.
"""
from app import db
from app.models import Usuario, Profissional, Paciente, Agendamento, Atendimento
from app.services.passwords import hash_senha

# CPF válido canônico para testes (dígitos verificadores corretos).
CPF_VALIDO = "529.982.247-25"


def _cria_prof(nome="Dra. Dois", email="prof2x@test.com"):
    u = Usuario(email=email, senha_hash=hash_senha("x"),
                nome_responsavel=nome, tipo="profissional")
    db.session.add(u)
    db.session.flush()
    p = Profissional(usuario_id=u.id, nome=nome, especialidade="Geral")
    db.session.add(p)
    db.session.flush()
    return p


# ---- P0: prontuário não vaza entre profissionais ----

def test_prontuario_nao_vaza_entre_profissionais(client_prof):
    ag = Agendamento.query.first()            # consulta do Dr. Teste (client_prof)
    p2 = _cria_prof()
    db.session.add(Atendimento(paciente_id=ag.paciente_id, profissional_id=p2.id,
                               queixa="SEGREDOB123", evolucao="conduta de B"))
    db.session.commit()
    r = client_prof.get(f"/agenda/{ag.id}/atendimento")
    assert r.status_code == 200
    assert b"SEGREDOB123" not in r.data       # não vê o atendimento de outro médico


def test_admin_ve_historico_completo(client_admin):
    ag = Agendamento.query.first()
    p2 = _cria_prof(email="prof3x@test.com")
    db.session.add(Atendimento(paciente_id=ag.paciente_id, profissional_id=p2.id,
                               queixa="VISIVEL_ADM", evolucao="x"))
    db.session.commit()
    r = client_admin.get(f"/agenda/{ag.id}/atendimento")
    assert r.status_code == 200
    assert b"VISIVEL_ADM" in r.data           # admin vê o histórico completo


# ---- CPF: duplicado não quebra, inválido é rejeitado ----

def test_cpf_duplicado_nao_quebra(client_admin):
    client_admin.post("/pacientes/novo",
                      data={"nome_completo": "Primeiro", "cpf": CPF_VALIDO,
                            "data_nascimento": "1990-05-10",
                            "telefone": "(43) 90000-0000", "origem": "Google"},
                      follow_redirects=True)
    antes = Paciente.query.count()
    r = client_admin.post("/pacientes/novo",
                          data={"nome_completo": "Segundo", "cpf": CPF_VALIDO,
                                "data_nascimento": "1990-05-10",
                                "telefone": "(43) 90000-1111", "origem": "Google"},
                          follow_redirects=True)
    assert r.status_code == 200               # não vira 500
    assert "Já existe".encode() in r.data
    assert Paciente.query.count() == antes    # não criou o duplicado


def test_cpf_invalido_rejeitado(client_admin):
    antes = Paciente.query.count()
    r = client_admin.post("/pacientes/novo",
                          data={"nome_completo": "CPF Ruim", "cpf": "123.456.789-00"},
                          follow_redirects=True)
    assert r.status_code == 200
    assert "inválido".encode() in r.data
    assert Paciente.query.count() == antes


def test_cpf_obrigatorio(client_admin):
    # CPF agora é OBRIGATÓRIO no cadastro (req. do sócio).
    antes = Paciente.query.count()
    r = client_admin.post("/pacientes/novo",
                          data={"nome_completo": "Sem CPF",
                                "data_nascimento": "1990-05-10"},
                          follow_redirects=True)
    assert r.status_code == 200
    assert Paciente.query.count() == antes      # não criou sem CPF
    assert b"CPF" in r.data


# ---- Agenda: não aceita data passada ----

def test_agenda_nao_aceita_dia_passado(client_recepcao):
    pac = Paciente.query.first()
    ag = Agendamento.query.first()
    antes = Agendamento.query.count()
    r = client_recepcao.post("/agenda/novo", data={
        "paciente_id": pac.id, "profissional_id": ag.profissional_id,
        "dia": "2020-01-01", "hora": "10:00",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "passada".encode() in r.data
    assert Agendamento.query.count() == antes


def test_reagendar_nao_aceita_dia_passado(client_recepcao):
    ag = Agendamento.query.first()
    r = client_recepcao.post(f"/agenda/{ag.id}/editar", data={
        "profissional_id": ag.profissional_id, "dia": "2020-01-01", "hora": "10:00",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "passada".encode() in r.data


# ---- Status: recepção não marca/reverte 'atendido' ----

def test_recepcao_nao_marca_atendido(client_recepcao):
    ag = Agendamento.query.first()
    r = client_recepcao.post(f"/agenda/{ag.id}/status",
                             data={"status": "atendido"}, follow_redirects=True)
    assert r.status_code == 200
    assert "inválido".encode() in r.data
    assert db.session.get(Agendamento, ag.id).status != Agendamento.STATUS_ATENDIDO


def test_status_nao_reverte_de_atendido(client_recepcao):
    ag = Agendamento.query.first()
    ag.status = Agendamento.STATUS_ATENDIDO
    db.session.commit()
    client_recepcao.post(f"/agenda/{ag.id}/status",
                         data={"status": "agendado"}, follow_redirects=True)
    assert db.session.get(Agendamento, ag.id).status == Agendamento.STATUS_ATENDIDO
