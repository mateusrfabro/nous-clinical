"""Fixtures pytest do Nous Clinical.

SQLite em arquivo temporario por sessao de teste (isolado do DB de dev),
schema via db.create_all(), seed minimo com 1 usuario de cada papel.
"""
import os
import tempfile
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app import create_app, db, limiter
from app.models import (
    Clinica, Usuario, Profissional, Paciente, Agendamento,
)
from app.services.passwords import hash_senha


@pytest.fixture
def app():
    fd, db_path = tempfile.mkstemp(suffix=".db", prefix="nous-test-")
    os.close(fd)
    os.environ["TEST_DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["SECRET_KEY"] = "test-secret"

    app = create_app("testing")
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    assert "nous.db" not in uri, f"SEGURANCA: teste nao toca DB real. URI={uri}"

    # Uploads isolados num temp (nao polui instance/uploads do dev).
    import shutil
    from app.services.storage import init_storage
    updir = tempfile.mkdtemp(prefix="nous-uploads-")
    app.config["UPLOAD_FOLDER"] = updir
    init_storage(app)

    limiter.enabled = False
    with app.app_context():
        db.create_all()
        _seed_minimo()
        yield app
        db.session.remove()
        db.drop_all()
    limiter.enabled = True
    os.environ.pop("TEST_DATABASE_URL", None)
    shutil.rmtree(updir, ignore_errors=True)
    try:
        os.unlink(db_path)
    except OSError:
        pass


def _novo_usuario(email, tipo, nome="Teste"):
    u = Usuario(email=email, senha_hash=hash_senha("testpass"),
                nome_responsavel=nome, telefone="(43) 99999-0000", tipo=tipo)
    db.session.add(u)
    db.session.flush()
    return u


def _seed_minimo():
    clinica = Clinica(nome="Clínica Teste", slug="teste")
    db.session.add(clinica)
    db.session.flush()

    _novo_usuario("admin@test.com", "admin")
    _novo_usuario("recepcao@test.com", "recepcao")

    up = _novo_usuario("prof@test.com", "profissional", "Dr. Teste")
    prof = Profissional(usuario_id=up.id, nome="Dr. Teste",
                        especialidade="Clínica Geral")
    db.session.add(prof)
    db.session.flush()

    pac = Paciente(nome_completo="Paciente Teste", cpf="111.111.111-11",
                   telefone="(43) 98888-0000")
    db.session.add(pac)
    db.session.flush()

    # Ancorado ao "hoje" de Brasília (não ao de UTC): à noite (após 21h BR) a
    # data UTC já virou, e um seed em UTC cairia "amanhã" no fuso BR, saindo do
    # período de relatórios/lembretes e quebrando testes por horário do dia.
    _br = ZoneInfo("America/Sao_Paulo")
    inicio = datetime.combine(datetime.now(_br).date(), time(12, 0),
                              tzinfo=_br).astimezone(timezone.utc)
    db.session.add(Agendamento(
        paciente_id=pac.id, profissional_id=prof.id,
        inicio=inicio, fim=inicio + timedelta(minutes=30),
        status=Agendamento.STATUS_AGENDADO,
    ))
    db.session.flush()

    # Multi-tenant Fase 0: vincula o seed à clínica de teste.
    for M in (Usuario, Profissional, Paciente, Agendamento):
        M.query.filter(M.clinica_id.is_(None)).update(
            {"clinica_id": clinica.id}, synchronize_session=False)
    db.session.commit()


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, email):
    import hashlib
    user = Usuario.query.filter_by(email=email).first()
    assert user is not None, f"Usuario {email} nao existe no seed."
    sid = hashlib.sha512(f"test-{user.id}".encode()).hexdigest()
    with client.session_transaction() as s:
        s["_user_id"] = str(user.id)
        s["_fresh"] = True
        s["_id"] = sid
        s["_permanent"] = True


@pytest.fixture
def client_admin(app):
    c = app.test_client()
    _login(c, "admin@test.com")
    return c


@pytest.fixture
def client_recepcao(app):
    c = app.test_client()
    _login(c, "recepcao@test.com")
    return c


@pytest.fixture
def client_prof(app):
    c = app.test_client()
    _login(c, "prof@test.com")
    return c