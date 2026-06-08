"""Seed de VALIDAÇÃO multi-clínica (pedido do sócio).

Cria 3 clínicas, cada uma com: 1 admin, 1 recepção e 2 médicos (com login),
+ pacientes, agendamentos atendidos, receitas e despesas DISTINTAS por clínica.
Objetivo: validar a visão do super admin (consolidado), o isolamento entre
clínicas e se os relatórios batem por clínica.

Senha de todos: 123demo. Idempotente por e-mail/slug — rodar 2x não duplica.

Uso:  python scripts/seed_demo_clinicas.py
"""
import os
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db  # noqa: E402
from app.models import (  # noqa: E402
    Clinica, Usuario, Profissional, Paciente, Agendamento, Atendimento,
    LancamentoFinanceiro, Convenio,
)
from app.services.passwords import hash_senha  # noqa: E402

SENHA = "123demo"

# Config por clínica. Valores distintos -> relatórios diferentes por clínica.
CLINICAS = [
    {
        "slug": "clinica-1", "nome": "Clínica 1 — Centro",
        "admin": ("clinica1@nous.com", "Admin Clínica 1"),
        "recepcao": ("recepcao1@nous.com", "Recepção Clínica 1"),
        "convenio": "Unimed",
        "medicos": [
            ("medico1.c1@nous.com", "Dr. Aldo Reis", "Cardiologia", "#43B8A5", "Sala 1", 10, Decimal("300.00")),
            ("medico2.c1@nous.com", "Dra. Bia Nunes", "Dermatologia", "#6FB59C", "Sala 2", 15, Decimal("250.00")),
        ],
        "aluguel": Decimal("1200.00"),
    },
    {
        "slug": "clinica-2", "nome": "Clínica 2 — Zona Sul",
        "admin": ("clinica2@nous.com", "Admin Clínica 2"),
        "recepcao": ("recepcao2@nous.com", "Recepção Clínica 2"),
        "convenio": "Bradesco Saúde",
        "medicos": [
            ("medico1.c2@nous.com", "Dr. Caio Melo", "Ortopedia", "#43B8A5", "Consultório A", 20, Decimal("500.00")),
            ("medico2.c2@nous.com", "Dra. Dora Pinto", "Ginecologia", "#B7A7F5", "Consultório B", 12, Decimal("400.00")),
        ],
        "aluguel": Decimal("2000.00"),
    },
    {
        "slug": "clinica-3", "nome": "Clínica 3 — Norte",
        "admin": ("clinica3@nous.com", "Admin Clínica 3"),
        "recepcao": ("recepcao3@nous.com", "Recepção Clínica 3"),
        "convenio": "SulAmérica",
        "medicos": [
            ("medico1.c3@nous.com", "Dr. Edu Faria", "Clínica Geral", "#6FB59C", "Sala 10", 8, Decimal("200.00")),
            ("medico2.c3@nous.com", "Dra. Fabi Rocha", "Pediatria", "#43B8A5", "Sala 11", 18, Decimal("150.00")),
        ],
        "aluguel": Decimal("800.00"),
    },
]


def _usuario(email, nome, tipo, clinica_id, tel="(11) 90000-0000"):
    u = Usuario.query.filter_by(email=email).first()
    if u:
        return u, False
    u = Usuario(email=email, senha_hash=hash_senha(SENHA), nome_responsavel=nome,
                telefone=tel, tipo=tipo, clinica_id=clinica_id,
                aceite_termos_em=datetime.now(timezone.utc))
    db.session.add(u)
    db.session.flush()
    return u, True


def seed_clinica(cfg, ordem):
    clinica = Clinica.query.filter_by(slug=cfg["slug"]).first()
    if not clinica:
        clinica = Clinica(nome=cfg["nome"], slug=cfg["slug"])
        db.session.add(clinica)
        db.session.flush()
    cid = clinica.id

    _usuario(*cfg["admin"], "admin", cid)
    _usuario(*cfg["recepcao"], "recepcao", cid)

    # Convênio (master data da clínica)
    if not Convenio.query.filter_by(clinica_id=cid, nome=cfg["convenio"]).first():
        db.session.add(Convenio(nome=cfg["convenio"], clinica_id=cid))

    # Médicos (login + Profissional)
    profs = []
    for email, nome, esp, cor, sala, comissao, _val in cfg["medicos"]:
        u, _ = _usuario(email, nome, "profissional", cid)
        prof = Profissional.query.filter_by(usuario_id=u.id).first()
        if not prof:
            prof = Profissional(usuario_id=u.id, nome=nome, especialidade=esp,
                                cor_agenda=cor, sala=sala, duracao_padrao_min=30,
                                comissao_percent=Decimal(comissao), clinica_id=cid)
            db.session.add(prof)
            db.session.flush()
        profs.append(prof)

    # Pacientes da clínica
    pacientes = []
    for n in range(1, 4):
        nome = f"Paciente {ordem}.{n} ({cfg['slug']})"
        p = Paciente.query.filter_by(nome_completo=nome).first()
        if not p:
            p = Paciente(nome_completo=nome, telefone=f"(11) 9{ordem}{n}00-00{n}{n}",
                         convenio=cfg["convenio"] if n == 1 else None, clinica_id=cid)
            db.session.add(p)
            db.session.flush()
        pacientes.append(p)

    agora = datetime.now(timezone.utc)
    base = datetime.combine(agora.date(), time(12, 0), tzinfo=timezone.utc)

    # 1 consulta ATENDIDA por médico (este mês) + atendimento + receita paga.
    # Só cria se a clínica ainda não tem agendamentos (idempotência simples).
    if Agendamento.query.filter_by(clinica_id=cid).count() == 0:
        for i, (prof, cfg_med) in enumerate(zip(profs, cfg["medicos"])):
            valor = cfg_med[6]
            pac = pacientes[i % len(pacientes)]
            inicio = base + timedelta(minutes=40 * i)
            ag = Agendamento(
                paciente_id=pac.id, profissional_id=prof.id,
                inicio=inicio, fim=inicio + timedelta(minutes=30),
                status=Agendamento.STATUS_ATENDIDO, sala=prof.sala,
                convenio=pac.convenio, valor=valor, clinica_id=cid)
            db.session.add(ag)
            db.session.flush()
            db.session.add(Atendimento(
                agendamento_id=ag.id, paciente_id=pac.id, profissional_id=prof.id,
                queixa="Consulta de rotina.", evolucao="Quadro estável.",
                clinica_id=cid))
            db.session.add(LancamentoFinanceiro(
                tipo="receita", categoria="consulta",
                descricao=f"Consulta - {pac.nome_completo}", valor=valor,
                status="pago", pago_em=agora, forma_pagamento="pix",
                paciente_id=pac.id, agendamento_id=ag.id,
                convenio=pac.convenio, clinica_id=cid))

        # 1 a-receber pendente + 1 despesa aluguel (paga) — pro fluxo/contas.
        db.session.add(LancamentoFinanceiro(
            tipo="receita", categoria="consulta",
            descricao="Consulta a receber", valor=Decimal("180.00"),
            status="pendente", vencimento=date.today() + timedelta(days=7),
            paciente_id=pacientes[2].id, clinica_id=cid))
        db.session.add(LancamentoFinanceiro(
            tipo="despesa", categoria="aluguel", descricao="Aluguel da clínica",
            valor=cfg["aluguel"], status="pago", pago_em=agora,
            forma_pagamento="transferencia", clinica_id=cid))

    return clinica


def main():
    app = create_app("development")
    with app.app_context():
        for i, cfg in enumerate(CLINICAS, start=1):
            seed_clinica(cfg, i)
        db.session.commit()

        print("Seed de validação concluído. Senha de todos: %s\n" % SENHA)
        for cfg in CLINICAS:
            print(f"== {cfg['nome']} ==")
            print(f"  admin:    {cfg['admin'][0]}")
            print(f"  recepção: {cfg['recepcao'][0]}")
            for m in cfg["medicos"]:
                print(f"  médico:   {m[0]}  ({m[1]} — {m[2]})")
            print()


if __name__ == "__main__":
    main()
