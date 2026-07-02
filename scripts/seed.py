"""Seed inicial / de demonstracao do Nous Clinical.

Cria: 1 admin, 1 recepcao, 2 profissionais (com login), pacientes e alguns
agendamentos pro dia de hoje. Idempotente por e-mail — rodar 2x nao duplica.

Uso:  python scripts/seed.py
"""
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

# Permite rodar de qualquer cwd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db  # noqa: E402
from app.models import (  # noqa: E402
    Clinica, Usuario, Profissional, Paciente, Agendamento,
    LancamentoFinanceiro, Atendimento, Procedimento, Convenio,
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
        # Clínica (tenant) PRIMEIRO — assim tudo já nasce com clinica_id
        # (before_flush usa a única clínica como fallback).
        clinica = Clinica.query.first()
        if not clinica:
            clinica = Clinica(nome="Clínica Nous", slug="nous",
                               agendamento_online_ativo=True)
            db.session.add(clinica)
            db.session.flush()

        # Admin + recepcao
        _get_or_create_usuario("admin@nous.com", "Administrador", "admin")
        _get_or_create_usuario("recepcao@nous.com", "Recepção", "recepcao")

        # Convênios (master data) — alimentam os selects de convênio nos cadastros.
        for nome_conv in ("Unimed", "Bradesco Saúde", "SulAmérica", "Amil",
                          "Particular"):
            if not Convenio.query.filter_by(clinica_id=clinica.id,
                                            nome=nome_conv).first():
                db.session.add(Convenio(nome=nome_conv, clinica_id=clinica.id))
        db.session.flush()

        # Profissionais (com login proprio)
        profs = []
        for email, nome, esp, cor in [
            ("dra.ana@nous.com", "Dra. Ana Souza", "Clínica Geral", "#43B8A5"),
            ("dr.bruno@nous.com", "Dr. Bruno Lima", "Pediatria", "#6FB59C"),
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
                                    telefone="(43) 98888-0001", convenio="Unimed",
                                    origem="Google"),
            _get_or_create_paciente("João Pereira", cpf="222.222.222-22",
                                    telefone="(43) 98888-0002", origem="Indicação"),
            _get_or_create_paciente("Carla Mendes", cpf="333.333.333-33",
                                    telefone="(43) 98888-0003", convenio="Bradesco Saúde",
                                    origem="Instagram"),
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

        # Lancamentos financeiros de demonstracao (fluxo de caixa nao nasce vazio).
        agora = datetime.now(timezone.utc)
        if LancamentoFinanceiro.query.count() == 0:
            db.session.add_all([
                LancamentoFinanceiro(
                    tipo="receita", categoria="consulta",
                    descricao="Consulta - Maria Oliveira", valor=Decimal("250.00"),
                    status="pago", pago_em=agora, forma_pagamento="pix",
                    paciente_id=pacientes[0].id, convenio="Unimed",
                ),
                LancamentoFinanceiro(
                    tipo="receita", categoria="consulta",
                    descricao="Consulta - João Pereira", valor=Decimal("200.00"),
                    status="pendente", vencimento=date.today() + timedelta(days=7),
                    paciente_id=pacientes[1].id,
                ),
                LancamentoFinanceiro(
                    tipo="receita", categoria="convenio",
                    descricao="Repasse convênio Bradesco Saúde",
                    valor=Decimal("180.00"), status="pendente",
                    vencimento=date.today() + timedelta(days=20),
                    paciente_id=pacientes[2].id, convenio="Bradesco Saúde",
                ),
                LancamentoFinanceiro(
                    tipo="despesa", categoria="aluguel",
                    descricao="Aluguel da clínica", valor=Decimal("3500.00"),
                    status="pago", pago_em=agora, forma_pagamento="transferencia",
                ),
                LancamentoFinanceiro(
                    tipo="despesa", categoria="insumo",
                    descricao="Material de consumo", valor=Decimal("420.00"),
                    status="pendente", vencimento=date.today() + timedelta(days=10),
                ),
            ])

        # Atendimento com retorno recomendado vencido -> alimenta o painel CRM.
        if Atendimento.query.count() == 0:
            helena = _get_or_create_paciente(
                "Helena Costa", cpf="444.444.444-44",
                telefone="(43) 98888-0004", convenio="Unimed")
            db.session.add(Atendimento(
                paciente_id=helena.id, profissional_id=profs[0].id,
                queixa="Acompanhamento — retorno anual recomendado.",
                evolucao="Quadro estável. Orientado retorno.",
                retorno_em=date.today() - timedelta(days=12)))

        # Catálogo de procedimentos (preços) pro flagbox do atendimento.
        if Procedimento.query.count() == 0:
            db.session.add_all([
                Procedimento(nome="Consulta", valor_padrao=Decimal("250.00")),
                Procedimento(nome="Exame Papanicolau", valor_padrao=Decimal("120.00")),
                Procedimento(nome="Ultrassonografia", valor_padrao=Decimal("180.00")),
                Procedimento(nome="Retorno", valor_padrao=Decimal("0.00")),
            ])

        # Multi-tenant Fase 0: garante a clínica default e vincula tudo a ela.
        clinica = Clinica.query.first()
        if not clinica:
            clinica = Clinica(nome="Clínica Nous", slug="nous",
                               agendamento_online_ativo=True)
            db.session.add(clinica)
            db.session.flush()
        for M in (Usuario, Profissional, Paciente, Agendamento, Atendimento,
                  LancamentoFinanceiro, Procedimento):
            M.query.filter(M.clinica_id.is_(None)).update(
                {"clinica_id": clinica.id}, synchronize_session=False)

        db.session.commit()
        print("Seed concluído.")
        print("Logins (senha: %s):" % SENHA_DEMO)
        print("  admin@nous.com      (admin)")
        print("  recepcao@nous.com   (recepção)")
        print("  dra.ana@nous.com    (profissional)")
        print("  dr.bruno@nous.com   (profissional)")


if __name__ == "__main__":
    seed()