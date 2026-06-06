"""Busca rápida / paleta de comando: endpoint /buscar (JSON, escopo por papel)."""
from app import db
from app.models import Paciente


def test_buscar_query_curta_vazia(client_admin):
    r = client_admin.get("/buscar?q=a")
    assert r.status_code == 200
    assert r.get_json()["pacientes"] == []


def test_buscar_acha_paciente(client_admin):
    db.session.add(Paciente(nome_completo="Mariana Testebusca",
                            telefone="(43) 90000-0001", convenio="Unimed"))
    db.session.commit()
    r = client_admin.get("/buscar?q=Testebusca")
    data = r.get_json()
    achados = [p for p in data["pacientes"] if "Testebusca" in p["nome"]]
    assert achados
    assert achados[0]["url"].rstrip("/").split("/")[-1].isdigit()  # tem link


def test_buscar_profissional_so_seus_pacientes(client_prof):
    # Paciente sem vínculo com o profissional não pode aparecer (escopo LGPD).
    db.session.add(Paciente(nome_completo="Estranho Semvinculo"))
    db.session.commit()
    r = client_prof.get("/buscar?q=Semvinculo")
    assert r.status_code == 200
    assert r.get_json()["pacientes"] == []
