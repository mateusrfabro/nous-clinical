"""Multi-tenant Fase 0: existe a clínica (tenant) e o seed está vinculado.

Fase 0 é fundação não-quebra: clinica_id é nullable e ainda NÃO há escopo
automático. Estes testes travam a base para a Fase 1 (enforcement)."""
from app.models import Clinica, Usuario, Paciente, Profissional, Agendamento


def test_clinica_tenant_existe(app):
    assert Clinica.query.count() >= 1


def test_seed_vinculado_a_clinica(app):
    c = Clinica.query.first()
    assert Usuario.query.filter_by(email="admin@test.com").first().clinica_id == c.id
    assert Profissional.query.first().clinica_id == c.id
    assert Paciente.query.first().clinica_id == c.id
    assert Agendamento.query.first().clinica_id == c.id
