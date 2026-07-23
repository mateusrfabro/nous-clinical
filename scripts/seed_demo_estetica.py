"""Seed de DEMONSTRACAO COMERCIAL — clinica de estetica/harmonizacao.

Persona: profissional autonoma (farmaceutica esteta, conselho CRF) que e DONA da
propria clinica e tambem quem atende. Como o papel `profissional` nao ve
Financeiro/Relatorios e o `admin` nao tem agenda/prontuario proprios, o seed cria
DOIS logins pra ela: gestora (admin) e profissional.

Todos os dados sao FICTICIOS (LGPD) e a clinica se chama "...Demonstracao".
Valores de procedimento sao ILUSTRATIVOS de mercado, nao tabela oficial.

Idempotente por slug/e-mail — rodar 2x nao duplica.

Uso:
    # senha forte gerada automaticamente:
    python scripts/seed_demo_estetica.py

    # personalizando (recomendado pra demo: use o nome real dela):
    DEMO_CLINICA="Studio da Ana" DEMO_PROFISSIONAL="Ana Paula Ribeiro" \
    DEMO_SENHA="umaSenhaForte123" python scripts/seed_demo_estetica.py

Apagar depois da demo: superadmin -> /clinicas -> remover a clinica do slug abaixo.
"""
import os
import secrets
import sys
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db  # noqa: E402
from app.models import (  # noqa: E402
    Clinica, Usuario, Profissional, Paciente, Agendamento, Atendimento,
    LancamentoFinanceiro, Convenio, Procedimento,
)
from app.services.passwords import hash_senha  # noqa: E402

BR = ZoneInfo("America/Sao_Paulo")
SLUG = "demo-estetica"

NOME_CLINICA = os.getenv("DEMO_CLINICA", "Studio Harmonizar — Demonstração")
NOME_PROF = os.getenv("DEMO_PROFISSIONAL", "Camila Ferraz")
EMAIL_GESTORA = os.getenv("DEMO_EMAIL_GESTORA", "gestora.demo@nousclinical.com")
EMAIL_PROF = os.getenv("DEMO_EMAIL_PROF", "profissional.demo@nousclinical.com")
SENHA = os.getenv("DEMO_SENHA") or secrets.token_urlsafe(9)

CONVENIO = "Particular"   # harmonizacao e particular; convenio nao cobre.

# Catalogo faturavel. Valores ILUSTRATIVOS de mercado (R$), nao tabela oficial.
PROCEDIMENTOS = [
    ("Avaliação / Consulta inicial", "150.00"),
    ("Toxina botulínica — terço superior", "1200.00"),
    ("Preenchimento labial (1ml)", "1400.00"),
    ("Preenchimento de malar (1ml)", "1500.00"),
    ("Bioestimulador de colágeno (frasco)", "1800.00"),
    ("Skinbooster (sessão)", "1100.00"),
    ("Microagulhamento (sessão)", "450.00"),
    ("Peeling químico (sessão)", "350.00"),
    ("Limpeza de pele profunda", "250.00"),
    ("Enzimas corporais (sessão)", "350.00"),
    ("Criolipólise (por área)", "900.00"),
]

# (nome, idade, origem, ddd_sufixo)
PACIENTES = [
    ("Aline Souza Martins", 34, "Instagram"),
    ("Bruna Carvalho Lima", 41, "Indicação"),
    ("Camila Ribeiro Alves", 29, "Instagram"),
    ("Daniela Ferreira Rocha", 37, "Google"),
    ("Eduarda Nunes Pinto", 45, "Indicação"),
    ("Fernanda Almeida Costa", 31, "Instagram"),
    ("Gabriela Moraes Dias", 38, "Site"),
    ("Helena Barbosa Reis", 52, "Indicação"),
]

# Agenda de HOJE: (hora, minutos_dur, idx_paciente, procedimento, valor, status)
HOJE = [
    (9, 60, 0, "Toxina botulínica — terço superior", "1200.00", Agendamento.STATUS_ATENDIDO),
    (10, 60, 1, "Preenchimento labial (1ml)", "1400.00", Agendamento.STATUS_ATENDIDO),
    (13, 90, 2, "Bioestimulador de colágeno (frasco)", "1800.00", Agendamento.STATUS_CONFIRMADO),
    (15, 60, 3, "Skinbooster (sessão)", "1100.00", Agendamento.STATUS_AGENDADO),
    (16, 30, 4, "Avaliação / Consulta inicial", "150.00", Agendamento.STATUS_AGENDADO),
    (17, 60, 5, "Limpeza de pele profunda", "250.00", Agendamento.STATUS_FALTOU),
]

# Historico (dias atras, idx_paciente, procedimento, valor, dias_ate_retorno)
HISTORICO = [
    (75, 0, "Toxina botulínica — terço superior", "1200.00", 120),   # retorno VENCIDO
    (60, 2, "Bioestimulador de colágeno (frasco)", "1800.00", 30),   # retorno VENCIDO
    (45, 4, "Preenchimento de malar (1ml)", "1500.00", 180),
    (30, 6, "Microagulhamento (sessão)", "450.00", 30),              # retorno de hoje-ish
    (20, 7, "Enzimas corporais (sessão)", "350.00", 15),             # retorno VENCIDO
    (10, 1, "Peeling químico (sessão)", "350.00", 30),
]

# Prontuario por procedimento (queixa, evolucao, orientacoes)
PRONTUARIO = {
    "Toxina botulínica — terço superior": (
        "Relata incômodo com linhas de expressão na região frontal e glabela.",
        "Aplicação de toxina botulínica em terço superior (frontal, glabela e "
        "periorbital), técnica intramuscular, pontos simétricos. Sem intercorrências.",
        "Não massagear a região e evitar exercício físico e exposição solar por 24h. "
        "Retorno em 15 dias para avaliação do resultado.",
    ),
    "Preenchimento labial (1ml)": (
        "Deseja hidratação e definição do contorno labial.",
        "Preenchimento labial com ácido hialurônico (1ml), técnica de retroinjeção "
        "em bordo e corpo. Boa acomodação do produto, sem isquemia.",
        "Compressa fria nas primeiras horas. Evitar calor intenso por 48h. "
        "Edema esperado nas primeiras 72h.",
    ),
    "Bioestimulador de colágeno (frasco)": (
        "Busca melhora da flacidez e qualidade de pele em terço médio/inferior.",
        "Aplicação de bioestimulador de colágeno, diluição conforme protocolo, "
        "técnica retroinjeção em leque. Massagem pós-aplicação realizada.",
        "Massagear a área conforme orientação (5x/dia por 5 dias). "
        "Retorno em 30 dias para 2ª sessão do protocolo.",
    ),
    "Preenchimento de malar (1ml)": (
        "Queixa de perda de projeção na região malar.",
        "Preenchimento de malar com ácido hialurônico de alta sustentação (1ml), "
        "técnica de bolus em plano supraperiosteal. Boa projeção obtida.",
        "Evitar pressão local por 7 dias. Retorno semestral para manutenção.",
    ),
    "Microagulhamento (sessão)": (
        "Textura irregular e poros dilatados em zona T.",
        "Microagulhamento com profundidade ajustada por região, associado a ativo "
        "pós-procedimento. Eritema esperado ao final.",
        "Fotoproteção rigorosa. Sessão seguinte em 30 dias (protocolo de 4 sessões).",
    ),
    "Enzimas corporais (sessão)": (
        "Objetivo de melhora de contorno corporal em flancos.",
        "Aplicação de protocolo enzimático corporal em flancos, pontos distribuídos. "
        "Boa tolerância, sem reação adversa.",
        "Ingerir bastante água e manter atividade física. Próxima sessão em 15 dias.",
    ),
    "Peeling químico (sessão)": (
        "Manchas e irregularidade de tom na face.",
        "Peeling químico superficial aplicado em face, tempo de permanência conforme "
        "fototipo. Neutralização realizada. Descamação esperada.",
        "Fotoproteção rigorosa e hidratação. Não remover a descamação. "
        "Próxima sessão em 30 dias.",
    ),
}


def _usuario(email, nome, tipo, clinica_id, tel):
    u = Usuario.query.filter_by(email=email).first()
    if u:
        return u
    u = Usuario(email=email, senha_hash=hash_senha(SENHA), nome_responsavel=nome,
                telefone=tel, tipo=tipo, clinica_id=clinica_id,
                aceite_termos_em=datetime.now(timezone.utc))
    db.session.add(u)
    db.session.flush()
    return u


def _hoje_br():
    return datetime.now(BR).date()


def _utc(d, hora, minuto=0):
    """Data BR + hora local -> datetime UTC aware (o app guarda tudo em UTC)."""
    return datetime.combine(d, time(hora, minuto), tzinfo=BR).astimezone(timezone.utc)


def seed():
    clinica = Clinica.query.filter_by(slug=SLUG).first()
    if not clinica:
        clinica = Clinica(nome=NOME_CLINICA, slug=SLUG, tema="teal",
                          # Liga o portal publico /c/demo-estetica/agendar —
                          # otimo argumento de venda ("seu paciente agenda sozinho").
                          agendamento_online_ativo=True)
        db.session.add(clinica)
        db.session.flush()
    cid = clinica.id

    _usuario(EMAIL_GESTORA, NOME_PROF, "admin", cid, "(43) 99900-0001")
    u_prof = _usuario(EMAIL_PROF, NOME_PROF, "profissional", cid, "(43) 99900-0002")

    prof = Profissional.query.filter_by(usuario_id=u_prof.id).first()
    if not prof:
        prof = Profissional(
            usuario_id=u_prof.id, nome=NOME_PROF,
            especialidade="Harmonização Facial e Corporal",
            registro_conselho="CRF-PR 41234",   # farmaceutica esteta
            cor_agenda="#B7A7F5", sala="Sala de Procedimentos",
            duracao_padrao_min=60, comissao_percent=Decimal("0.00"),
            clinica_id=cid)
        db.session.add(prof)
        db.session.flush()

    if not Convenio.query.filter_by(clinica_id=cid, nome=CONVENIO).first():
        db.session.add(Convenio(nome=CONVENIO, clinica_id=cid))

    # Catalogo de procedimentos (itens faturaveis)
    for nome, valor in PROCEDIMENTOS:
        if not Procedimento.query.filter_by(clinica_id=cid, nome=nome).first():
            db.session.add(Procedimento(nome=nome, valor_padrao=Decimal(valor),
                                        clinica_id=cid))
    db.session.flush()

    # Pacientes
    hoje = _hoje_br()
    pacientes = []
    for i, (nome, idade, origem) in enumerate(PACIENTES, start=1):
        p = Paciente.query.filter_by(clinica_id=cid, nome_completo=nome).first()
        if not p:
            p = Paciente(
                nome_completo=nome,
                cpf=f"900.000.{i:03d}-{i:02d}",
                data_nascimento=date(hoje.year - idade, ((i * 3) % 12) + 1, (i % 27) + 1),
                sexo="F", telefone=f"(43) 98{i}00-1{i}{i}{i}",
                email=f"paciente{i}.demo@exemplo.com",
                cidade="Londrina", convenio=CONVENIO, origem=origem,
                observacoes="Paciente fictícia — dados de demonstração.",
                clinica_id=cid)
            db.session.add(p)
            db.session.flush()
        pacientes.append(p)

    # Idempotencia: so monta a agenda/financeiro na primeira execucao.
    if Agendamento.query.filter_by(clinica_id=cid).count() > 0:
        db.session.commit()
        return clinica, False

    def _atender(ag, pac, procedimento, dia):
        """Cria o prontuario + define o retorno recomendado (alimenta o CRM)."""
        q, e, o = PRONTUARIO.get(
            procedimento,
            ("Avaliação inicial.", "Plano de tratamento definido com a paciente.",
             "Retorno conforme protocolo."))
        db.session.add(Atendimento(
            agendamento_id=ag.id, paciente_id=pac.id, profissional_id=prof.id,
            queixa=q, evolucao=e, prescricao=o, clinica_id=cid))

    def _receita(pac, ag, procedimento, valor, pago, quando, forma):
        db.session.add(LancamentoFinanceiro(
            tipo=LancamentoFinanceiro.TIPO_RECEITA, categoria="procedimento",
            descricao=f"{procedimento} — {pac.nome_completo}",
            valor=Decimal(valor),
            status=(LancamentoFinanceiro.STATUS_PAGO if pago
                    else LancamentoFinanceiro.STATUS_PENDENTE),
            pago_em=(quando if pago else None),
            vencimento=(None if pago else hoje + timedelta(days=7)),
            forma_pagamento=(forma if pago else None),
            paciente_id=pac.id, agendamento_id=(ag.id if ag else None),
            convenio=CONVENIO, clinica_id=cid))

    # ---- Agenda de HOJE (a tela que ela vai ver primeiro) ----
    for hora, dur, idx, proc, valor, status in HOJE:
        pac = pacientes[idx]
        ini = _utc(hoje, hora)
        ag = Agendamento(paciente_id=pac.id, profissional_id=prof.id,
                         inicio=ini, fim=ini + timedelta(minutes=dur),
                         status=status, sala=prof.sala, convenio=CONVENIO,
                         valor=Decimal(valor), clinica_id=cid)
        db.session.add(ag)
        db.session.flush()
        if status == Agendamento.STATUS_ATENDIDO:
            _atender(ag, pac, proc, hoje)
            _receita(pac, ag, proc, valor, True, datetime.now(timezone.utc),
                     "cartao_credito")

    # ---- Historico (gera retornos pendentes no CRM + faturamento do periodo) ----
    for dias, idx, proc, valor, ret in HISTORICO:
        pac = pacientes[idx]
        d = hoje - timedelta(days=dias)
        ini = _utc(d, 14)
        ag = Agendamento(paciente_id=pac.id, profissional_id=prof.id,
                         inicio=ini, fim=ini + timedelta(minutes=60),
                         status=Agendamento.STATUS_ATENDIDO, sala=prof.sala,
                         convenio=CONVENIO, valor=Decimal(valor), clinica_id=cid)
        db.session.add(ag)
        db.session.flush()
        q, e, o = PRONTUARIO.get(proc, ("Avaliação.", "Conduta definida.", "Retorno."))
        db.session.add(Atendimento(
            agendamento_id=ag.id, paciente_id=pac.id, profissional_id=prof.id,
            queixa=q, evolucao=e, prescricao=o,
            retorno_em=d + timedelta(days=ret),   # <- alimenta /crm/retornos
            clinica_id=cid))
        _receita(pac, ag, proc, valor, True,
                 _utc(d, 18), "pix" if dias % 2 else "cartao_credito")

    # ---- Agenda futura (proximos dias) ----
    for k, (idx, proc, valor) in enumerate([
        (3, "Bioestimulador de colágeno (frasco)", "1800.00"),
        (5, "Toxina botulínica — terço superior", "1200.00"),
        (7, "Criolipólise (por área)", "900.00"),
    ], start=1):
        pac = pacientes[idx]
        ini = _utc(hoje + timedelta(days=k), 10 + k)
        db.session.add(Agendamento(
            paciente_id=pac.id, profissional_id=prof.id,
            inicio=ini, fim=ini + timedelta(minutes=60),
            status=Agendamento.STATUS_AGENDADO, sala=prof.sala,
            convenio=CONVENIO, valor=Decimal(valor), clinica_id=cid))

    # ---- Contas a receber (parcelado no cartao e' o normal da estetica) ----
    _receita(pacientes[2], None, "Bioestimulador — 2ª parcela", "900.00",
             False, None, None)
    _receita(pacientes[4], None, "Preenchimento de malar — 2ª parcela", "750.00",
             False, None, None)

    # ---- Despesas (fazem o DRE/relatorio ter sentido) ----
    agora = datetime.now(timezone.utc)
    for cat, desc, valor, pago in [
        ("aluguel", "Aluguel da sala", "2500.00", True),
        ("insumo", "Toxina botulínica e preenchedores (estoque)", "3800.00", True),
        ("insumo", "Descartáveis e anestésicos", "620.00", True),
        ("imposto", "Simples Nacional — competência do mês", "980.00", False),
    ]:
        db.session.add(LancamentoFinanceiro(
            tipo=LancamentoFinanceiro.TIPO_DESPESA, categoria=cat, descricao=desc,
            valor=Decimal(valor),
            status=(LancamentoFinanceiro.STATUS_PAGO if pago
                    else LancamentoFinanceiro.STATUS_PENDENTE),
            pago_em=(agora if pago else None),
            vencimento=(None if pago else hoje + timedelta(days=10)),
            forma_pagamento=("transferencia" if pago else None),
            clinica_id=cid))

    db.session.commit()
    return clinica, True


def main():
    ambiente = "production" if os.getenv("FLASK_ENV") == "production" else "development"
    app = create_app(ambiente)
    with app.app_context():
        clinica, novo = seed()
        print("\n" + "=" * 62)
        print(f"  DEMO {'criada' if novo else 'ja existia (nada duplicado)'}: {clinica.nome}")
        print("=" * 62)
        print(f"  Gestora (admin) ....: {EMAIL_GESTORA}")
        print(f"  Profissional .......: {EMAIL_PROF}")
        print(f"  Senha (ambos) ......: {SENHA}")
        print(f"  Portal publico .....: /c/{SLUG}/agendar")
        print("=" * 62)
        print("  Dados ficticios. Apagar depois: superadmin -> /clinicas.\n")


if __name__ == "__main__":
    main()
