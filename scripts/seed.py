"""Seed inicial / de demonstracao do medsaas.

Cria: 1 admin, 1 recepcao, 2 profissionais (com login), pacientes e alguns
agendamentos pro dia de hoje. Idempotente por e-mail — rodar 2x nao duplica.

Uso:  python scripts/seed.py
"""
import os
import sys
from datetime import datetime, time, timedelta, timezone

# Permite rodar de qualquer cwd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db  # noqa: E402
from app.models import (  # noqa: E402
    Usuario, Profissional, Paciente, Agendamento,
)
from app.services.passwords import hash_senha  # noqa: E402

SENHA_DEMO = "demo123"


def _get_or_create_usuario(email, nome, tipo, telefone="(43) 99999-0000"):
    u = Usuario.query.filter_by(email=email).first()
    if u:
        return u, False
    u = Usuario(
        email=email, senha_hash=hash_senha(SENHA_DEMO),
        nome_responsavel=nome, telefone=telefone, tipo=tipo,
        aceite_termos_em=datetime.now(timezone.utc),
    )
    db.session.add(u)
    db.session.flush()
    return u, True


def _get_or_create_paciente(nome, **kw):
    p = Paciente.query.filter_by(nome_completo=nome).first()
    if p:
        return p
    p = Paciente(nome_completo=nome, **kw)
    db.session.add(p)
    db.session.flush()
    return p


def seed():
    app = create_app(os.getenv("FLASK_ENV", "development") == "production"
                     and "production" or "development")
    with app.app_context():
        # Admin + recepcao
        _get_or_create_usuario("admin@medsaas.com", "Administrador", "admin")
        _get_or_create_usuario("recepcao@medsaas.com", "Recepção", "recepcao")

        # Profissionais (com login proprio)
        profs = []
        for email, nome, esp, cor in [
            ("dra.ana@medsaas.com", "Dra. Ana Souza", "Clínica Geral", "#2563eb"),
            ("dr.bruno@medsaas.com", "Dr. Bruno Lima", "Pediatria", "#16a34a"),
        ]:
            u, _ = _get_or_create_usuario(email, nome, "profissional")
            prof = Profissional.query.filter_by(usuario_id=u.id).first()
            if not prof:
                prof = Profissional(usuario_id=u.id, nome=nome, especialidade=esp,
                                    cor_agenda=cor, duracao_padrao_min=30)
                db.session.add(prof)
                db.session.flush()
            profs.append(prof)

        # Pacientes
        pacientes = [
            _get_or_create_paciente("Maria Oliveira", cpf="111.111.111-11",
                                    telefone="(43) 98888-0001", convenio="Unimed"),
            _get_or_create_paciente("João Pereira", cpf="222.222.222-22",
                                    telefone="(43) 98888-0002"),
            _get_or_create_paciente("Carla Mendes", cpf="333.333.333-33",
                                    telefone="(43) 98888-0003", convenio="Bradesco Saúde"),
        ]

        # Agendamentos de hoje (09:00, 09:30, 10:00)
        hoje = datetime.now(timezone.utc).replace(microsecond=0)
        base = datetime.combine(hoje.date(), time(12, 0), tzinfo=timezone.utc)  # ~09:00 BR
        if Agendamento.query.count() == 0:
            for i, pac in enumerate(pacientes):
                inicio = base + timedelta(minutes=30 * i)
                db.session.add(Agendamento(
                    paciente_id=pac.id,
                    profissional_id=profs[i % len(profs)].id,
                    inicio=inicio, fim=inicio + timedelta(minutes=30),
                    status=Agendamento.STATUS_AGENDADO,
                ))

        db.session.commit()
        print("Seed concluído.")
        print("Logins (senha: %s):" % SENHA_DEMO)
        print("  admin@medsaas.com      (admin)")
        print("  recepcao@medsaas.com   (recepção)")
        print("  dra.ana@medsaas.com    (profissional)")
        print("  dr.bruno@medsaas.com   (profissional)")


if __name__ == "__main__":
    seed()