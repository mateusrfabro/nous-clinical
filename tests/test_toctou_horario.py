"""Trava anti-double-book no banco (índice único parcial): mesmo profissional +
início exato não pode ter 2 agendamentos NÃO-cancelados. Fecha a corrida TOCTOU
entre a checagem de conflito e o commit."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import Profissional, Paciente, Agendamento


def _ag(prof, pac, inicio, status=Agendamento.STATUS_AGENDADO):
    return Agendamento(paciente_id=pac.id, profissional_id=prof.id,
                       inicio=inicio, fim=inicio + timedelta(minutes=30),
                       status=status, clinica_id=prof.clinica_id)


def test_double_book_mesmo_inicio_barrado(app):
    prof = Profissional.query.first()
    pac = Paciente.query.first()
    ini = datetime(2030, 1, 10, 13, 0, tzinfo=timezone.utc)
    db.session.add(_ag(prof, pac, ini))
    db.session.commit()
    db.session.add(_ag(prof, pac, ini))        # mesmo slot, não-cancelado
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_cancelado_libera_o_slot(app):
    prof = Profissional.query.first()
    pac = Paciente.query.first()
    ini = datetime(2030, 1, 11, 13, 0, tzinfo=timezone.utc)
    db.session.add(_ag(prof, pac, ini, status=Agendamento.STATUS_CANCELADO))
    db.session.commit()
    db.session.add(_ag(prof, pac, ini))        # ativo sobre um cancelado -> ok
    db.session.commit()                        # não deve levantar
    assert Agendamento.query.filter_by(
        profissional_id=prof.id, inicio=ini,
        status=Agendamento.STATUS_AGENDADO).count() == 1
