"""Agenda em quadro Kanban (por status): render, colunas, ações rápidas e gating."""
from app import db
from app.models import Agendamento


def test_kanban_admin_renderiza_colunas(client_admin):
    r = client_admin.get("/agenda/quadro")
    assert r.status_code == 200
    assert b"kanban-board" in r.data
    # As 5 colunas de status aparecem.
    for titulo in (b"Agendado", b"Confirmado", b"Atendido", b"Faltou", b"Cancelado"):
        assert titulo in r.data


def test_kanban_card_na_coluna_do_status(client_admin):
    ag = Agendamento.query.first()
    nome = ag.paciente.nome_completo.encode()
    r = client_admin.get("/agenda/quadro")
    assert r.status_code == 200
    assert nome in r.data
    # Consulta 'agendado' oferece a ação rápida de confirmar (POST mudar_status).
    assert b'value="confirmado"' in r.data
    assert b"/status" in r.data


def test_kanban_acao_rapida_muda_status(client_admin):
    ag = Agendamento.query.first()
    assert ag.status == Agendamento.STATUS_AGENDADO
    r = client_admin.post(
        f"/agenda/{ag.id}/status",
        data={"status": "confirmado"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    db.session.refresh(ag)
    assert ag.status == Agendamento.STATUS_CONFIRMADO


def test_kanban_profissional_acessa(client_prof):
    assert client_prof.get("/agenda/quadro").status_code == 200
