"""Operação da agenda: check-in (fila do dia) + cores/legenda por status."""
from app import db
from app.models import Agendamento


def test_checkin_marca_chegada_e_confirma(client_recepcao):
    ag = Agendamento.query.first()        # nasce 'agendado'
    r = client_recepcao.post(f"/agenda/{ag.id}/checkin", follow_redirects=True)
    assert r.status_code == 200
    ag2 = db.session.get(Agendamento, ag.id)
    assert ag2.checkin_em is not None
    assert ag2.status == Agendamento.STATUS_CONFIRMADO   # chegar confirma presença


def test_checkin_toggle_desfaz(client_recepcao):
    ag = Agendamento.query.first()
    client_recepcao.post(f"/agenda/{ag.id}/checkin")
    client_recepcao.post(f"/agenda/{ag.id}/checkin")      # 2ª vez desfaz
    assert db.session.get(Agendamento, ag.id).checkin_em is None


def test_checkin_gating_profissional(client_prof):
    ag = Agendamento.query.first()
    assert client_prof.post(f"/agenda/{ag.id}/checkin").status_code in (301, 302)


def test_semana_tem_legenda_e_dot(client_admin):
    r = client_admin.get("/agenda/semana")
    assert r.status_code == 200
    assert b"agenda-legenda" in r.data
