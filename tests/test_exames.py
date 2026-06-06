"""Anexos de exame: upload/download/excluir + gating clínico (LGPD)."""
import io

from app.models import Agendamento, Exame


def _pdf(nome="exame.pdf", conteudo=b"%PDF-1.4 conteudo de teste"):
    return {"arquivo": (io.BytesIO(conteudo), nome)}


def test_upload_e_download(client_prof):
    ag = Agendamento.query.first()
    r = client_prof.post(f"/exames/atendimento/{ag.id}", data=_pdf(),
                         content_type="multipart/form-data",
                         follow_redirects=True)
    assert r.status_code == 200
    ex = Exame.query.first()
    assert ex is not None
    assert ex.nome_original == "exame.pdf"
    assert ex.atendimento_id is not None  # criou/vinculou o atendimento

    d = client_prof.get(f"/exames/{ex.id}/download")
    assert d.status_code == 200
    assert b"%PDF" in d.data


def test_recepcao_nao_anexa(client_recepcao):
    ag = Agendamento.query.first()
    r = client_recepcao.post(f"/exames/atendimento/{ag.id}", data=_pdf(),
                             content_type="multipart/form-data")
    assert r.status_code in (301, 302)  # clinico_required
    assert Exame.query.count() == 0


def test_extensao_invalida_rejeitada(client_prof):
    ag = Agendamento.query.first()
    r = client_prof.post(f"/exames/atendimento/{ag.id}",
                         data=_pdf("virus.exe", b"MZ"),
                         content_type="multipart/form-data",
                         follow_redirects=True)
    assert r.status_code == 200
    assert "permitido".encode() in r.data.lower()
    assert Exame.query.count() == 0


def test_excluir_exame(client_prof):
    ag = Agendamento.query.first()
    client_prof.post(f"/exames/atendimento/{ag.id}", data=_pdf(),
                     content_type="multipart/form-data")
    ex = Exame.query.first()
    r = client_prof.post(f"/exames/{ex.id}/excluir", follow_redirects=True)
    assert r.status_code == 200
    assert Exame.query.count() == 0


def test_content_type_derivado_da_extensao(client_prof):
    ag = Agendamento.query.first()
    # mimetype mentiroso (text/html) com extensão .png -> deve virar image/png
    data = {"arquivo": (io.BytesIO(b"\x89PNG"), "foto.png", "text/html")}
    client_prof.post(f"/exames/atendimento/{ag.id}", data=data,
                     content_type="multipart/form-data")
    ex = Exame.query.first()
    assert ex.content_type == "image/png"


def test_download_exige_clinico(client_recepcao, client_prof):
    ag = Agendamento.query.first()
    client_prof.post(f"/exames/atendimento/{ag.id}", data=_pdf(),
                     content_type="multipart/form-data")
    ex = Exame.query.first()
    # recepção não é clínico -> bloqueada
    assert client_recepcao.get(f"/exames/{ex.id}/download").status_code in (301, 302)
