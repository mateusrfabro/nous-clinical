"""Evolução da agenda (RF-01..07): disponibilidade do profissional, slots
respeitando disponibilidade/pausa/bloqueios, CRUD de bloqueios + permissões +
auditoria, e a grade diária visual.
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app import db
from app.models import Profissional, Bloqueio, Agendamento, Paciente, AuditLog

_BR = ZoneInfo("America/Sao_Paulo")


def _prof():
    return db.session.execute(db.select(Profissional)).scalars().first()


def _prox_segunda():
    d = datetime.now(_BR).date() + timedelta(days=1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


def _futuro(dias):
    return datetime.now(_BR).date() + timedelta(days=dias)


# ---------- RF-02: disponibilidade no cadastro do profissional ----------

def test_form_profissional_salva_disponibilidade(client_admin):
    prof = _prof()
    client_admin.post(f"/profissionais/{prof.id}/editar", data={
        "nome": "Dr. Teste", "duracao_padrao_min": "30", "comissao_percent": "0",
        "ativo": "on", "dias": ["0", "2", "4"],
        "hora_inicio": "09:00", "hora_fim": "17:00",
        "intervalo_inicio": "12:00", "intervalo_fim": "13:00",
    }, follow_redirects=True)
    p = db.session.get(Profissional, prof.id)
    assert p.dias_atendimento == "0,2,4"
    assert p.hora_inicio == time(9, 0) and p.hora_fim == time(17, 0)
    assert p.intervalo_inicio == time(12, 0) and p.intervalo_fim == time(13, 0)


def test_disponibilidade_rejeita_fim_antes_do_inicio(client_admin):
    prof = _prof()
    r = client_admin.post(f"/profissionais/{prof.id}/editar", data={
        "nome": "Dr. Teste", "duracao_padrao_min": "30", "comissao_percent": "0",
        "ativo": "on", "dias": ["0"], "hora_inicio": "18:00", "hora_fim": "08:00",
    }, follow_redirects=True)
    assert "maior que o inicial".encode() in r.data
    p = db.session.get(Profissional, prof.id)
    assert p.hora_inicio != time(18, 0)          # não persistiu


# ---------- RF-03/04: slots respeitam disponibilidade ----------

def test_slots_respeitam_dias_de_atendimento(app):
    from app.routes.agenda import _slots_livres
    prof = _prof()
    prof.dias_atendimento = "0"                   # só segunda
    prof.hora_inicio, prof.hora_fim = time(8, 0), time(12, 0)
    prof.duracao_padrao_min = 60
    db.session.commit()
    seg = _prox_segunda()
    assert _slots_livres(prof, seg)               # segunda tem slots
    assert _slots_livres(prof, seg + timedelta(days=1)) == []   # terça não


def test_slots_excluem_pausa_almoco(app):
    from app.routes.agenda import _slots_livres
    prof = _prof()
    prof.dias_atendimento = "0,1,2,3,4,5,6"
    prof.hora_inicio, prof.hora_fim = time(8, 0), time(14, 0)
    prof.duracao_padrao_min = 60
    prof.intervalo_inicio, prof.intervalo_fim = time(12, 0), time(13, 0)
    db.session.commit()
    slots = _slots_livres(prof, _futuro(2))
    assert "08:00" in slots and "12:00" not in slots   # almoço fora


def test_slots_excluem_bloqueio(app):
    from app.routes.agenda import _slots_livres
    prof = _prof()
    prof.dias_atendimento = "0,1,2,3,4,5,6"
    prof.hora_inicio, prof.hora_fim = time(8, 0), time(12, 0)
    prof.duracao_padrao_min = 60
    db.session.commit()
    dia = _futuro(3)
    ini = datetime.combine(dia, time(9, 0), tzinfo=_BR).astimezone(timezone.utc)
    fim = datetime.combine(dia, time(10, 0), tzinfo=_BR).astimezone(timezone.utc)
    db.session.add(Bloqueio(profissional_id=prof.id, inicio=ini, fim=fim,
                            motivo="Reunião"))
    db.session.commit()
    slots = _slots_livres(prof, dia)
    assert "08:00" in slots and "09:00" not in slots


# ---------- RF-05/06/07: bloqueios ----------

def test_admin_cria_bloqueio_dia_inteiro(client_admin):
    prof = _prof()
    dia = _futuro(5).isoformat()
    antes = Bloqueio.query.count()
    r = client_admin.post("/agenda/bloqueios", data={
        "profissional_id": prof.id, "data_inicio": dia, "data_fim": dia,
        "motivo": "Férias",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert Bloqueio.query.count() == antes + 1
    assert AuditLog.query.filter_by(acao="bloqueio_criado").count() >= 1


def test_admin_cria_bloqueio_faixa_horario(client_admin):
    prof = _prof()
    dia = _futuro(5).isoformat()
    r = client_admin.post("/agenda/bloqueios", data={
        "profissional_id": prof.id, "data_inicio": dia,
        "hora_inicio": "14:00", "hora_fim": "16:00", "motivo": "Reunião",
    }, follow_redirects=True)
    assert r.status_code == 200
    b = Bloqueio.query.order_by(Bloqueio.id.desc()).first()
    dur_h = (b.fim - b.inicio).total_seconds() / 3600
    assert abs(dur_h - 2) < 0.01                  # faixa de 2h


def test_bloqueio_faixa_invalida_rejeitada(client_admin):
    prof = _prof()
    dia = _futuro(5).isoformat()
    antes = Bloqueio.query.count()
    client_admin.post("/agenda/bloqueios", data={
        "profissional_id": prof.id, "data_inicio": dia,
        "hora_inicio": "16:00", "hora_fim": "14:00", "motivo": "Reunião",
    }, follow_redirects=True)
    assert Bloqueio.query.count() == antes         # não criou


def test_bloqueio_impede_agendamento(client_admin):
    prof = _prof()
    pac = Paciente.query.first()
    dia = _futuro(6)
    ini = datetime.combine(dia, time.min, tzinfo=_BR).astimezone(timezone.utc)
    fim = datetime.combine(dia + timedelta(days=1), time.min,
                           tzinfo=_BR).astimezone(timezone.utc)
    db.session.add(Bloqueio(profissional_id=prof.id, inicio=ini, fim=fim,
                            motivo="Congresso"))
    db.session.commit()
    antes = Agendamento.query.count()
    r = client_admin.post("/agenda/novo", data={
        "paciente_id": pac.id, "profissional_id": prof.id,
        "dia": dia.isoformat(), "hora": "10:00", "duracao_min": "30",
    }, follow_redirects=True)
    assert b"bloqueada" in r.data
    assert Agendamento.query.count() == antes       # bloqueou o agendamento


def test_profissional_cria_bloqueio_proprio(client_prof):
    prof = _prof()
    dia = _futuro(4).isoformat()
    r = client_prof.post("/agenda/bloqueios", data={
        "profissional_id": "99999",               # tenta outro -> forçado a si
        "data_inicio": dia, "motivo": "Ausência",
    }, follow_redirects=True)
    assert r.status_code == 200
    b = Bloqueio.query.order_by(Bloqueio.id.desc()).first()
    assert b is not None and b.profissional_id == prof.id


def test_bloqueios_acessivel_pela_equipe(client_recepcao, client_prof):
    assert client_recepcao.get("/agenda/bloqueios").status_code == 200
    assert client_prof.get("/agenda/bloqueios").status_code == 200


def test_remover_bloqueio_audita(client_admin):
    prof = _prof()
    ini = datetime.now(timezone.utc) + timedelta(days=2)
    b = Bloqueio(profissional_id=prof.id, inicio=ini, fim=ini + timedelta(hours=1),
                 motivo="x")
    db.session.add(b)
    db.session.commit()
    bid = b.id
    client_admin.post(f"/agenda/bloqueios/{bid}/remover", follow_redirects=True)
    assert db.session.get(Bloqueio, bid) is None
    assert AuditLog.query.filter_by(acao="bloqueio_removido").count() >= 1


# ---------- RF-01: grade diária visual ----------

def test_grade_diaria_renderiza(client_admin):
    r = client_admin.get("/agenda/grade")
    assert r.status_code == 200
    assert b"week--single" in r.data and b"week-col" in r.data


def test_grade_mostra_bloqueio(client_admin):
    prof = _prof()
    dia = datetime.now(_BR).date()
    ini = datetime.combine(dia, time(9, 0), tzinfo=_BR).astimezone(timezone.utc)
    fim = datetime.combine(dia, time(10, 0), tzinfo=_BR).astimezone(timezone.utc)
    db.session.add(Bloqueio(profissional_id=prof.id, inicio=ini, fim=fim,
                            motivo="ReuniaoGradeX"))
    db.session.commit()
    r = client_admin.get(f"/agenda/grade?dia={dia.isoformat()}")
    assert b"ag-block" in r.data and b"ReuniaoGradeX" in r.data
