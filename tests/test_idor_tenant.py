"""IDOR cross-tenant: rotas que usam db.session.get(Model, id) NÃO podem
expor/alterar registro de OUTRA clínica (achado #10 da auditoria de código).

Verifica empiricamente se o escopo automático do tenant (do_orm_execute +
with_loader_criteria) cobre o Session.get() por PK nas rotas de paciente,
agenda e exame.
"""
from datetime import datetime, timedelta, timezone

from app import db
from app.models import (
    Clinica, Paciente, Profissional, Usuario, Agendamento, Atendimento, Exame,
)
from app.services.passwords import hash_senha


def _clinica_b():
    """Cria uma 2ª clínica com paciente, profissional, agendamento e exame
    próprios (clinica_id explícito = B)."""
    cb = Clinica(nome="Clínica B IDOR", slug="b-idor")
    db.session.add(cb)
    db.session.flush()
    u = Usuario(email="medico.b@idor.com", senha_hash=hash_senha("x"),
                nome_responsavel="Med B", telefone="(11) 90000-0000",
                tipo="profissional", clinica_id=cb.id)
    db.session.add(u)
    db.session.flush()
    prof = Profissional(usuario_id=u.id, nome="Dr. B IDOR",
                        especialidade="Geral", clinica_id=cb.id)
    pac = Paciente(nome_completo="PACIENTE-B-SECRETO", clinica_id=cb.id,
                   telefone="(11) 98888-0000")
    db.session.add_all([prof, pac])
    db.session.flush()
    ini = datetime.now(timezone.utc) + timedelta(days=1)
    ag = Agendamento(clinica_id=cb.id, paciente_id=pac.id,
                     profissional_id=prof.id, inicio=ini,
                     fim=ini + timedelta(minutes=30),
                     status=Agendamento.STATUS_AGENDADO)
    db.session.add(ag)
    db.session.flush()
    at = Atendimento(clinica_id=cb.id, paciente_id=pac.id,
                     profissional_id=prof.id, queixa="QUEIXA-B-SECRETA")
    db.session.add(at)
    db.session.flush()
    ex = Exame(clinica_id=cb.id, atendimento_id=at.id, paciente_id=pac.id,
               nome_original="EXAME-B-SECRETO.pdf", arquivo_key="b/x.pdf",
               content_type="application/pdf", tamanho=10)
    db.session.add(ex)
    db.session.commit()
    return {"clinica": cb, "paciente": pac, "agendamento": ag,
            "atendimento": at, "exame": ex}


_NEGADO = (302, 403, 404)   # qualquer um nega; o que NÃO pode é 200 com o dado


def test_paciente_de_outra_clinica_nao_vaza(client_admin, app):
    b = _clinica_b()
    r = client_admin.get(f"/pacientes/{b['paciente'].id}", follow_redirects=True)
    assert b"PACIENTE-B-SECRETO" not in r.data   # o dado da clínica B não aparece


def test_agendamento_de_outra_clinica_nao_muda_status(client_admin, app):
    b = _clinica_b()
    r = client_admin.post(f"/agenda/{b['agendamento'].id}/status",
                          data={"status": "cancelado"}, follow_redirects=False)
    assert r.status_code in _NEGADO
    # E o status real NÃO mudou (a mutação cross-tenant foi barrada).
    db.session.expire_all()
    ag = db.session.execute(
        db.select(Agendamento).where(Agendamento.id == b["agendamento"].id)
        .execution_options(ignore_tenant=True)).scalar_one()
    assert ag.status == Agendamento.STATUS_AGENDADO


def test_atendimento_de_outra_clinica_nao_abre(client_admin, app):
    b = _clinica_b()
    r = client_admin.get(f"/agenda/{b['agendamento'].id}/atendimento",
                         follow_redirects=True)
    assert b"QUEIXA-B-SECRETA" not in r.data


def test_exame_de_outra_clinica_nao_baixa(client_admin, app):
    b = _clinica_b()
    r = client_admin.get(f"/exames/{b['exame'].id}/download", follow_redirects=True)
    assert b"EXAME-B-SECRETO" not in r.data
    assert b"%PDF" not in r.data[:200]   # não serviu o arquivo
