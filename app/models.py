"""Modelos do dominio: gestao de clinica / agenda.

Convencoes herdadas da plataforma:
- Dinheiro SEMPRE Numeric(12, 2) — nunca Float.
- Datas SEMPRE DateTime(timezone=True), armazenadas em UTC. Display converte
  pro fuso de Brasilia nos filtros Jinja (data_br / datetime_br / hora_br).
- Acesso por papel via Usuario.tipo: admin | profissional | recepcao.

Dados de saude sao "dados sensiveis" pela LGPD (art. 5, II). Prontuario
(Atendimento) so e acessivel por profissional/admin — nunca pela recepcao.
"""
from datetime import datetime, time, timezone

from flask_login import UserMixin
from sqlalchemy import Numeric

from app import db, login_manager


def _agora():
    return datetime.now(timezone.utc)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))


class Clinica(db.Model):
    """Tenant: uma clínica/consultório. Multi-tenant Fase 0 — todas as
    entidades do domínio ganham clinica_id (nullable nesta fase; o escopo
    automático e o NOT NULL entram na Fase 1). Ver docs/arquitetura/0001."""
    __tablename__ = "clinicas"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    # Identificador curto (futuro subdomínio/slug de URL). Único quando definido.
    slug = db.Column(db.String(60), unique=True)
    # White-label: tema de marca da clínica (classe CSS body.tema-<tema>).
    # Valores: teal (padrão) | indigo | violeta | verde | ambar | petroleo.
    tema = db.Column(db.String(20), nullable=False, default="teal")
    # Cor de marca livre (v2b) — sobrescreve o tema quando definida (#rrggbb).
    cor_primaria = db.Column(db.String(7))
    # Logo da clínica (v2a): chave opaca no storage + content-type confiável.
    logo_key = db.Column(db.String(255))
    logo_mime = db.Column(db.String(60))
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)

    def __repr__(self):
        return f"<Clinica {self.id} {self.nome}>"


class Convenio(db.Model):
    """Cadastro centralizado de convênios (master data).

    Evita duplicidade e erros de grafia do texto livre que hoje vive em
    Paciente.convenio / Agendamento.convenio / LancamentoFinanceiro.convenio /
    PrecoConvenio.convenio. Os campos de texto livre continuam existindo (não
    quebra dado legado); os forms passam a oferecer esta lista como sugestão.
    """
    __tablename__ = "convenios"
    __table_args__ = (
        db.UniqueConstraint("clinica_id", "nome", name="uq_convenio_clinica_nome"),
    )

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"),
                           index=True, nullable=False)
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)

    def __repr__(self):
        return f"<Convenio {self.id} {self.nome}>"


class Sala(db.Model):
    """Cadastro de salas/consultórios da clínica (master data, RF-03).

    Lista controlada (sem digitação livre, igual a Convenio). O agendamento
    passa a escolher a sala desta lista, e a agenda bloqueia duas consultas
    na MESMA sala no mesmo horário. Agendamento.sala segue como texto (snapshot
    histórico), populado a partir desta lista.
    """
    __tablename__ = "salas"
    __table_args__ = (
        db.UniqueConstraint("clinica_id", "nome", name="uq_sala_clinica_nome"),
    )

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(60), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"),
                           index=True, nullable=False)
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)

    def __repr__(self):
        return f"<Sala {self.id} {self.nome}>"


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    nome_responsavel = db.Column(db.String(150), nullable=False)
    telefone = db.Column(db.String(30))
    # admin | profissional | recepcao
    # superadmin (plataforma, cross-tenant) | admin | profissional | recepcao
    tipo = db.Column(db.String(20), nullable=False, default="recepcao")
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    # Nullable: o superadmin não pertence a nenhuma clínica (gerencia todas).
    # Usuários de clínica (admin/recepcao/profissional) sempre têm clinica_id.
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"), index=True)

    # Canal opcional de notificacao/reset de senha.
    telegram_chat_id = db.Column(db.String(40))

    aceite_termos_em = db.Column(db.DateTime(timezone=True))
    senha_atualizada_em = db.Column(db.DateTime(timezone=True))
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)

    # Proteção anti-brute-force POR CONTA (o rate-limit por IP não cobre ataque
    # distribuído a UMA conta). Persistido no DB porque prod é multi-worker.
    tentativas_falhas = db.Column(db.Integer, nullable=False, default=0)
    bloqueado_ate = db.Column(db.DateTime(timezone=True))
    # Último IP de login OK — dispara alerta por e-mail quando muda (acesso novo).
    ultimo_login_ip = db.Column(db.String(45))

    # 2FA/TOTP (opcional, recomendado p/ admin/superadmin). O segredo fica
    # CIFRADO em repouso (Fernet, services/cripto.py) — mesmo padrão do token
    # WhatsApp. `totp_ativado` só vira True após o usuário confirmar 1 código.
    totp_secret = db.Column(db.String(255))
    totp_ativado = db.Column(db.Boolean, nullable=False, default=False)
    # Códigos de recuperação do 2FA (uso único) guardados como HASH — JSON de
    # lista de sha256. Permite entrar se o usuário perder o autenticador.
    totp_recovery = db.Column(db.Text)

    profissional = db.relationship(
        "Profissional", back_populates="usuario", uselist=False
    )

    @property
    def is_superadmin(self):
        return self.tipo == "superadmin"

    @property
    def is_admin(self):
        return self.tipo == "admin"

    @property
    def is_profissional(self):
        return self.tipo == "profissional"

    @property
    def is_recepcao(self):
        return self.tipo == "recepcao"

    def __repr__(self):
        return f"<Usuario {self.id} {self.email} {self.tipo}>"


class Profissional(db.Model):
    __tablename__ = "profissionais"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id"), unique=True, nullable=False
    )
    nome = db.Column(db.String(150), nullable=False)
    especialidade = db.Column(db.String(100))
    # Numero do conselho (CRM, CRO, CRP, etc) — texto livre pra cobrir conselhos.
    registro_conselho = db.Column(db.String(40))
    # Cor hex pra diferenciar profissionais na agenda (ex: #43B8A5).
    cor_agenda = db.Column(db.String(7), default="#43B8A5")
    duracao_padrao_min = db.Column(db.Integer, default=30)
    # Sala/consultório padrão do profissional (texto livre). A agenda puxa
    # automaticamente este valor pro agendamento ao marcar a consulta.
    sala = db.Column(db.String(40))
    # % de repasse/comissão sobre a receita recebida das consultas (0..100).
    comissao_percent = db.Column(Numeric(5, 2), nullable=False, default=0)
    # --- Disponibilidade / horário de atendimento (RF-02) ---
    # Dias de atendimento: CSV de weekday() (0=Seg .. 6=Dom). NULL (legado) =
    # seg-sex via dias_atendimento_set(). Horários e pausa em hora LOCAL (BR).
    dias_atendimento = db.Column(db.String(20), default="0,1,2,3,4")
    hora_inicio = db.Column(db.Time, default=time(8, 0))
    hora_fim = db.Column(db.Time, default=time(18, 0))
    # Intervalo = pausa/almoço (janela em que NÃO há slots). Opcional.
    intervalo_inicio = db.Column(db.Time)
    intervalo_fim = db.Column(db.Time)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"), index=True, nullable=False)
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)

    usuario = db.relationship("Usuario", back_populates="profissional")
    agendamentos = db.relationship("Agendamento", back_populates="profissional")

    # Defaults usados quando o profissional não configurou disponibilidade
    # (cadastro legado). Mantém o comportamento antigo (seg-sex 08–18).
    DISP_DIAS_PADRAO = "0,1,2,3,4"
    DISP_HORA_INI_PADRAO = time(8, 0)
    DISP_HORA_FIM_PADRAO = time(18, 0)

    def dias_atendimento_set(self):
        """Set de weekday() (0=Seg) em que o profissional atende.
        NULL = fallback seg-sex (legado). String vazia = nenhum dia."""
        raw = self.dias_atendimento
        if raw is None:
            raw = self.DISP_DIAS_PADRAO
        out = set()
        for parte in raw.split(","):
            parte = parte.strip()
            if parte.isdigit() and 0 <= int(parte) <= 6:
                out.add(int(parte))
        return out

    def disp_hora_inicio(self):
        return self.hora_inicio or self.DISP_HORA_INI_PADRAO

    def disp_hora_fim(self):
        return self.hora_fim or self.DISP_HORA_FIM_PADRAO

    def __repr__(self):
        return f"<Profissional {self.id} {self.nome}>"


class Paciente(db.Model):
    __tablename__ = "pacientes"
    # Índice pros relatórios que filtram "novos pacientes" por período.
    __table_args__ = (
        db.Index("ix_pac_clinica_criado", "clinica_id", "criado_em"),
    )

    id = db.Column(db.Integer, primary_key=True)
    nome_completo = db.Column(db.String(150), nullable=False, index=True)
    cpf = db.Column(db.String(14), unique=True)  # formato 000.000.000-00
    data_nascimento = db.Column(db.Date)
    sexo = db.Column(db.String(1))  # M | F | O
    telefone = db.Column(db.String(30))
    email = db.Column(db.String(255))

    cep = db.Column(db.String(9))  # formato 00000-000
    endereco = db.Column(db.String(200))
    bairro = db.Column(db.String(80))
    cidade = db.Column(db.String(80))

    convenio = db.Column(db.String(80))
    observacoes = db.Column(db.Text)
    # "Como conheceu a clínica?" — inteligência comercial (origem do lead).
    # Obrigatório no cadastro novo (form); legado/online pode ficar nulo/Site.
    origem = db.Column(db.String(20))

    ativo = db.Column(db.Boolean, nullable=False, default=True)
    # LGPD art. 18 (direito ao esquecimento): marca quando os dados pessoais
    # foram anonimizados. NULL = paciente normal. Ver services/anonimizacao.py.
    anonimizado_em = db.Column(db.DateTime(timezone=True))
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"), index=True, nullable=False)
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)

    # Origens de lead aceitas (pergunta "Como conheceu a clínica?").
    ORIGENS = ("Google", "Instagram", "Facebook", "Indicação", "Site",
               "Convênio", "Outdoor", "Rádio", "Outros")
    criado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    agendamentos = db.relationship(
        "Agendamento", back_populates="paciente",
        order_by="Agendamento.inicio.desc()",
    )
    atendimentos = db.relationship(
        "Atendimento", back_populates="paciente",
        order_by="Atendimento.criado_em.desc()",
    )
    lancamentos = db.relationship(
        "LancamentoFinanceiro", back_populates="paciente",
        order_by="LancamentoFinanceiro.criado_em.desc()",
    )

    def __repr__(self):
        return f"<Paciente {self.id} {self.nome_completo}>"


class Agendamento(db.Model):
    __tablename__ = "agendamentos"
    # Índices compostos pros filtros quentes: janela de dia por clínica e por
    # profissional (agenda, kanban, dashboard, checagem de conflito).
    __table_args__ = (
        db.Index("ix_ag_clinica_inicio", "clinica_id", "inicio"),
        db.Index("ix_ag_prof_inicio", "profissional_id", "inicio"),
    )

    STATUS_AGENDADO = "agendado"
    STATUS_CONFIRMADO = "confirmado"
    STATUS_ATENDIDO = "atendido"
    STATUS_CANCELADO = "cancelado"
    STATUS_FALTOU = "faltou"

    id = db.Column(db.Integer, primary_key=True)
    paciente_id = db.Column(
        db.Integer, db.ForeignKey("pacientes.id"), nullable=False, index=True
    )
    profissional_id = db.Column(
        db.Integer, db.ForeignKey("profissionais.id"), nullable=False, index=True
    )

    inicio = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    fim = db.Column(db.DateTime(timezone=True), nullable=False)

    status = db.Column(db.String(20), nullable=False, default=STATUS_AGENDADO)
    convenio = db.Column(db.String(80))
    valor = db.Column(Numeric(12, 2))
    # Sala/consultório da consulta. Preenchida automaticamente com a sala do
    # profissional ao agendar; editável.
    sala = db.Column(db.String(40))
    observacoes = db.Column(db.Text)

    # Check-in: momento em que o paciente chegou à recepção (NULL = não chegou).
    checkin_em = db.Column(db.DateTime(timezone=True))
    # Lembrete automático já enviado (idempotência do job de lembretes).
    lembrete_enviado_em = db.Column(db.DateTime(timezone=True))
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"), index=True, nullable=False)

    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)
    criado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    paciente = db.relationship("Paciente", back_populates="agendamentos")
    profissional = db.relationship("Profissional", back_populates="agendamentos")
    atendimento = db.relationship(
        "Atendimento", back_populates="agendamento", uselist=False
    )
    # Recebimento integrado: 0..1 lancamento financeiro ligado a consulta.
    lancamento = db.relationship(
        "LancamentoFinanceiro", back_populates="agendamento", uselist=False
    )

    def __repr__(self):
        return f"<Agendamento {self.id} pac={self.paciente_id} {self.status}>"


class Bloqueio(db.Model):
    """Bloqueio de agenda de um profissional (RF-05): férias, congresso,
    reunião, ausência. Impede agendamentos no intervalo [inicio, fim).
    Datas em UTC (display BR). Escopado por clínica. Criação/remoção auditadas.
    """
    __tablename__ = "bloqueios"

    MOTIVOS = ("Férias", "Congresso", "Reunião", "Ausência", "Outros")

    id = db.Column(db.Integer, primary_key=True)
    profissional_id = db.Column(
        db.Integer, db.ForeignKey("profissionais.id"), nullable=False, index=True
    )
    inicio = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    fim = db.Column(db.DateTime(timezone=True), nullable=False)
    motivo = db.Column(db.String(120))
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"), index=True, nullable=False)
    criado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)

    profissional = db.relationship("Profissional")

    def __repr__(self):
        return f"<Bloqueio {self.id} prof={self.profissional_id}>"


class Atendimento(db.Model):
    """Prontuario clinico de uma consulta. DADO SENSIVEL (LGPD).

    Acesso restrito a profissional/admin. Append-only na pratica: edicoes
    deveriam virar adendos, mas pro MVP permitimos editar enquanto o
    atendimento e do dia (regra aplicada na rota, nao no modelo).
    """
    __tablename__ = "atendimentos"
    # Índices compostos pros relatórios/CRM que filtram/ordenam por data e por
    # retorno recomendado (painel de retornos + badge de contagem).
    __table_args__ = (
        db.Index("ix_atend_clinica_criado", "clinica_id", "criado_em"),
        db.Index("ix_atend_clinica_retorno", "clinica_id", "retorno_em"),
    )

    id = db.Column(db.Integer, primary_key=True)
    agendamento_id = db.Column(
        db.Integer, db.ForeignKey("agendamentos.id"), unique=True
    )
    paciente_id = db.Column(
        db.Integer, db.ForeignKey("pacientes.id"), nullable=False, index=True
    )
    profissional_id = db.Column(
        db.Integer, db.ForeignKey("profissionais.id"), nullable=False
    )

    queixa = db.Column(db.Text)       # queixa principal / anamnese
    evolucao = db.Column(db.Text)     # evolucao / conduta
    prescricao = db.Column(db.Text)   # prescricao / receituario

    # CRM Retorno (Fase 2): data de retorno recomendada pelo profissional.
    # Alimenta o painel de retornos pendentes. Nullable = sem retorno previsto.
    retorno_em = db.Column(db.Date)
    # Atestado médico (opcional): dias de afastamento + CID. Alimenta o PDF de
    # atestado. Nullable = sem atestado nesta consulta.
    atestado_dias = db.Column(db.Integer)
    atestado_cid = db.Column(db.String(20))
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"), index=True, nullable=False)

    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)

    agendamento = db.relationship("Agendamento", back_populates="atendimento")
    paciente = db.relationship("Paciente", back_populates="atendimentos")
    profissional = db.relationship("Profissional")
    itens = db.relationship(
        "ItemAtendimento", back_populates="atendimento",
        cascade="all, delete-orphan",
    )
    exames = db.relationship(
        "Exame", back_populates="atendimento",
        order_by="Exame.criado_em.desc()",
    )

    @property
    def total_itens(self):
        """Soma dos itens/procedimentos consumidos (Decimal)."""
        from decimal import Decimal
        return sum((i.valor * i.quantidade for i in self.itens), Decimal("0.00"))

    def __repr__(self):
        return f"<Atendimento {self.id} pac={self.paciente_id}>"


class Procedimento(db.Model):
    """Catalogo de procedimentos/produtos faturaveis (consulta, exames...).

    O preco vive aqui; ao marcar no atendimento, copia-se o valor pro
    ItemAtendimento (snapshot) pra nao mudar historico se o preco subir.
    """
    __tablename__ = "procedimentos"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    valor_padrao = db.Column(Numeric(12, 2), nullable=False, default=0)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"), index=True, nullable=False)
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)

    precos = db.relationship(
        "PrecoConvenio", back_populates="procedimento",
        cascade="all, delete-orphan", order_by="PrecoConvenio.convenio",
    )

    def preco_para(self, convenio):
        """Preço do procedimento p/ um convênio (ou valor_padrao se não houver)."""
        if convenio:
            for p in self.precos:
                if p.convenio == convenio:
                    return p.valor
        return self.valor_padrao

    def __repr__(self):
        return f"<Procedimento {self.id} {self.nome}>"


class PrecoConvenio(db.Model):
    """Preço de um procedimento para um convênio específico (tabela de preços)."""
    __tablename__ = "precos_convenio"
    __table_args__ = (
        db.UniqueConstraint("procedimento_id", "convenio",
                            name="uq_preco_proc_conv"),
    )

    id = db.Column(db.Integer, primary_key=True)
    procedimento_id = db.Column(
        db.Integer, db.ForeignKey("procedimentos.id"), nullable=False, index=True
    )
    convenio = db.Column(db.String(80), nullable=False)
    valor = db.Column(Numeric(12, 2), nullable=False, default=0)

    procedimento = db.relationship("Procedimento", back_populates="precos")

    def __repr__(self):
        return f"<PrecoConvenio proc={self.procedimento_id} {self.convenio} {self.valor}>"


class ItemAtendimento(db.Model):
    """Item consumido em um atendimento (flag do medico). Snapshot de valor."""
    __tablename__ = "itens_atendimento"

    id = db.Column(db.Integer, primary_key=True)
    atendimento_id = db.Column(
        db.Integer, db.ForeignKey("atendimentos.id"), nullable=False, index=True
    )
    procedimento_id = db.Column(db.Integer, db.ForeignKey("procedimentos.id"))
    descricao = db.Column(db.String(120))     # snapshot do nome
    valor = db.Column(Numeric(12, 2), nullable=False, default=0)
    quantidade = db.Column(db.Integer, nullable=False, default=1)

    atendimento = db.relationship("Atendimento", back_populates="itens")
    procedimento = db.relationship("Procedimento")

    def __repr__(self):
        return f"<ItemAtendimento {self.id} {self.descricao} {self.valor}>"


class LancamentoFinanceiro(db.Model):
    """Lancamento do modulo financeiro: uma entrada (receita) ou saida (despesa).

    Um unico modelo cobre receitas/despesas, contas a receber/pagar (status
    pendente) e fluxo de caixa (somas por pago_em). Pode ligar a um paciente
    (historico financeiro) e a um agendamento (recebimento integrado da
    consulta, relacao 1:1 via unique). Dinheiro SEMPRE Numeric(12, 2).
    """
    __tablename__ = "lancamentos_financeiros"
    # Índices compostos pros filtros quentes: fluxo/faturamento (status+tipo+
    # pago_em) e contas a receber/atraso (status+tipo+vencimento), por clínica.
    __table_args__ = (
        db.Index("ix_lanc_clinica_status_tipo_pago",
                 "clinica_id", "status", "tipo", "pago_em"),
        db.Index("ix_lanc_clinica_status_tipo_venc",
                 "clinica_id", "status", "tipo", "vencimento"),
    )

    TIPO_RECEITA = "receita"
    TIPO_DESPESA = "despesa"

    STATUS_PENDENTE = "pendente"
    STATUS_PAGO = "pago"
    STATUS_CANCELADO = "cancelado"

    # Categorias livres-controladas (label PT-BR nos filtros Jinja).
    CATEGORIAS_RECEITA = ("consulta", "procedimento", "convenio", "outro")
    CATEGORIAS_DESPESA = ("aluguel", "salario", "insumo", "imposto", "outro")

    FORMAS_PAGAMENTO = (
        "dinheiro", "pix", "cartao_credito", "cartao_debito",
        "convenio", "boleto", "transferencia",
    )

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(10), nullable=False, default=TIPO_RECEITA, index=True)
    categoria = db.Column(db.String(30))
    descricao = db.Column(db.String(200))
    valor = db.Column(Numeric(12, 2), nullable=False)

    status = db.Column(db.String(12), nullable=False, default=STATUS_PENDENTE, index=True)
    forma_pagamento = db.Column(db.String(20))

    # Conta a receber/pagar: data de vencimento (sem hora). pago_em = realizado.
    vencimento = db.Column(db.Date)
    pago_em = db.Column(db.DateTime(timezone=True), index=True)

    # Ligacoes opcionais.
    paciente_id = db.Column(
        db.Integer, db.ForeignKey("pacientes.id"), index=True
    )
    agendamento_id = db.Column(
        db.Integer, db.ForeignKey("agendamentos.id"), unique=True, index=True
    )
    convenio = db.Column(db.String(80))

    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"), index=True, nullable=False)
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)
    criado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    paciente = db.relationship("Paciente", back_populates="lancamentos")
    agendamento = db.relationship("Agendamento", back_populates="lancamento")
    # Conciliação bancária: 0..1 movimento de extrato casado a este lançamento.
    # `movimento is None` => lançamento ainda não conciliado.
    movimento = db.relationship(
        "MovimentoBancario", back_populates="lancamento", uselist=False)

    @property
    def conciliado(self):
        """True se há um movimento bancário casado a este lançamento."""
        return self.movimento is not None

    @property
    def vencido(self):
        """True se pendente e o vencimento ja passou (compara em data BR)."""
        if self.status != self.STATUS_PENDENTE or not self.vencimento:
            return False
        from zoneinfo import ZoneInfo
        hoje_br = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
        return self.vencimento < hoje_br

    def __repr__(self):
        return f"<LancamentoFinanceiro {self.id} {self.tipo} {self.status} {self.valor}>"


class MovimentoBancario(db.Model):
    """Transação de um extrato bancário (OFX) importada para conciliação.

    Cada linha do extrato vira um movimento. O usuário concilia cada movimento
    com um LancamentoFinanceiro (relação 1:1) — casando um existente ou criando
    um novo a partir do movimento — ou marca como ignorado (tarifa, transferência
    interna, etc.). Dedup de reimportação por (clinica_id, conta, fitid). Valor
    SEMPRE positivo; o sentido vive em `tipo` (credito=entrada / debito=saida).
    Dinheiro Numeric(12,2). Datas do extrato são DATE (sem hora/fuso).
    """
    __tablename__ = "movimentos_bancarios"
    __table_args__ = (
        db.UniqueConstraint("clinica_id", "conta", "fitid", name="uq_mov_fitid"),
        db.Index("ix_mov_clinica_status_data", "clinica_id", "status", "data"),
    )

    STATUS_PENDENTE = "pendente"
    STATUS_CONCILIADO = "conciliado"
    STATUS_IGNORADO = "ignorado"

    TIPO_CREDITO = "credito"   # entrada (TRNAMT > 0)
    TIPO_DEBITO = "debito"     # saída   (TRNAMT < 0)

    id = db.Column(db.Integer, primary_key=True)
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"),
                           index=True, nullable=False)
    data = db.Column(db.Date, nullable=False, index=True)   # DTPOSTED do OFX
    valor = db.Column(Numeric(12, 2), nullable=False)       # sempre positivo
    tipo = db.Column(db.String(8), nullable=False)          # credito | debito
    descricao = db.Column(db.String(200))                   # MEMO/NAME do OFX
    fitid = db.Column(db.String(80))                        # id único da transação
    conta = db.Column(db.String(40))                        # ACCTID do OFX
    banco = db.Column(db.String(60))                        # ORG/BANKID (exibição)
    status = db.Column(db.String(12), nullable=False,
                       default=STATUS_PENDENTE, index=True)
    lancamento_id = db.Column(
        db.Integer, db.ForeignKey("lancamentos_financeiros.id"),
        unique=True, index=True)
    importado_em = db.Column(db.DateTime(timezone=True), default=_agora)
    importado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    conciliado_em = db.Column(db.DateTime(timezone=True))
    conciliado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    lancamento = db.relationship(
        "LancamentoFinanceiro", back_populates="movimento")

    def __repr__(self):
        return f"<MovimentoBancario {self.id} {self.tipo} {self.valor} {self.status}>"


class FechamentoCaixa(db.Model):
    """Fechamento de caixa diário: confere o ESPERADO (receitas pagas no dia,
    por forma de pagamento) contra o CONTADO pela recepção, registrando a
    divergência. Um por (clínica, dia) — reabrir apaga o registro. Os totais
    são snapshot do momento do fechamento; `detalhes` guarda o por-forma (JSON).
    Dinheiro Numeric(12,2). `dia` é DATE (fuso BR resolvido na rota).
    """
    __tablename__ = "fechamentos_caixa"
    __table_args__ = (
        db.UniqueConstraint("clinica_id", "dia", name="uq_fechamento_dia"),
    )

    id = db.Column(db.Integer, primary_key=True)
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"),
                           index=True, nullable=False)
    dia = db.Column(db.Date, nullable=False, index=True)
    esperado_total = db.Column(Numeric(12, 2), nullable=False, default=0)
    contado_total = db.Column(Numeric(12, 2), nullable=False, default=0)
    divergencia = db.Column(Numeric(12, 2), nullable=False, default=0)  # contado-esperado
    detalhes = db.Column(db.Text)        # JSON: {forma: {esperado, contado}}
    observacoes = db.Column(db.Text)
    fechado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    fechado_em = db.Column(db.DateTime(timezone=True), default=_agora)
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)

    def __repr__(self):
        return f"<FechamentoCaixa {self.id} dia={self.dia} div={self.divergencia}>"


class Exame(db.Model):
    """Anexo (exame/documento) de um atendimento. DADO SENSÍVEL (LGPD).

    O arquivo vive no storage (fora de static/); só a `arquivo_key` opaca fica
    no DB. Download por rota autenticada com checagem de papel (clínico).
    """
    __tablename__ = "exames"

    id = db.Column(db.Integer, primary_key=True)
    atendimento_id = db.Column(
        db.Integer, db.ForeignKey("atendimentos.id"), nullable=False, index=True
    )
    paciente_id = db.Column(
        db.Integer, db.ForeignKey("pacientes.id"), nullable=False, index=True
    )
    nome_original = db.Column(db.String(200))
    arquivo_key = db.Column(db.String(255), nullable=False)
    content_type = db.Column(db.String(100))
    tamanho = db.Column(db.Integer)
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"), index=True, nullable=False)
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)
    criado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    atendimento = db.relationship("Atendimento", back_populates="exames")
    paciente = db.relationship("Paciente")

    def __repr__(self):
        return f"<Exame {self.id} {self.nome_original}>"


class AuditLog(db.Model):
    """Trilha de auditoria. NUNCA gravar PII em `detalhes`."""
    __tablename__ = "audit_logs"

    # Acoes (constantes — usadas pelos services/rotas pra evitar string solta)
    ACAO_LOGIN_OK = "login_ok"
    ACAO_LOGIN_FAIL = "login_fail"
    ACAO_LOGOUT = "logout"
    ACAO_SENHA_REDEFINIDA = "senha_redefinida"
    ACAO_PACIENTE_CRIADO = "paciente_criado"
    ACAO_PACIENTE_EDITADO = "paciente_editado"
    ACAO_PACIENTE_ANONIMIZADO = "paciente_anonimizado"  # LGPD art. 18
    ACAO_LOGIN_BLOQUEADO = "login_bloqueado"            # conta travada por brute-force
    ACAO_2FA_ATIVADO = "2fa_ativado"
    ACAO_2FA_DESATIVADO = "2fa_desativado"
    ACAO_AGENDAMENTO_CRIADO = "agendamento_criado"
    ACAO_AGENDAMENTO_STATUS = "agendamento_status"
    ACAO_AGENDAMENTO_EDITADO = "agendamento_editado"
    ACAO_AGENDAMENTO_CHECKIN = "agendamento_checkin"
    ACAO_AGENDAMENTO_CONFIRMADO_PUB = "agendamento_confirmado_publico"
    ACAO_ATENDIMENTO_REGISTRADO = "atendimento_registrado"
    ACAO_ATENDIMENTO_EDITADO = "atendimento_editado"
    ACAO_PROFISSIONAL_CRIADO = "profissional_criado"
    ACAO_PROFISSIONAL_EDITADO = "profissional_editado"
    ACAO_CLINICA_CRIADA = "clinica_criada"
    ACAO_CLINICA_STATUS = "clinica_status"
    ACAO_LANCAMENTO_CRIADO = "lancamento_criado"
    ACAO_LANCAMENTO_PAGO = "lancamento_pago"
    ACAO_LANCAMENTO_CANCELADO = "lancamento_cancelado"
    ACAO_PROCEDIMENTO_SALVO = "procedimento_salvo"
    ACAO_PROCEDIMENTO_EXCLUIDO = "procedimento_excluido"
    ACAO_CONVENIO_SALVO = "convenio_salvo"
    ACAO_SALA_SALVA = "sala_salva"  # cadastro de sala/consultório (RF-03)
    ACAO_EXAME_ANEXADO = "exame_anexado"
    ACAO_EXAME_REMOVIDO = "exame_removido"
    # Acesso a dado sensivel (LGPD art. 37 — registro de operacoes de
    # tratamento). Le/visualiza/exporta — nao so altera.
    ACAO_PRONTUARIO_VISUALIZADO = "prontuario_visualizado"
    ACAO_EXAME_BAIXADO = "exame_baixado"
    ACAO_RELATORIO_EXPORTADO = "relatorio_exportado"
    ACAO_DOCUMENTO_EMITIDO = "documento_emitido"  # receita/atestado PDF
    ACAO_CRM_INTERACAO = "crm_interacao"  # contato registrado (ex: aniversário)
    ACAO_BLOQUEIO_CRIADO = "bloqueio_criado"      # bloqueio de agenda (RF-05/07)
    ACAO_BLOQUEIO_REMOVIDO = "bloqueio_removido"  # desbloqueio de agenda
    ACAO_AJUDA_CONSULTA = "ajuda_consulta"        # pergunta ao chatbot de ajuda
    ACAO_WHATSAPP_CONFIG = "whatsapp_config"      # conexão/edição da conta WhatsApp
    ACAO_WHATSAPP_ENVIADA = "whatsapp_enviada"    # mensagem enviada pela equipe
    ACAO_FISCAL_CONFIG = "fiscal_config"          # config de emissão de NFS-e da clínica
    ACAO_CONCILIACAO_IMPORT = "conciliacao_import"      # importou extrato OFX
    ACAO_CONCILIACAO_CONCILIADO = "conciliacao_conciliado"  # casou movimento×lançamento
    ACAO_CONCILIACAO_IGNORADO = "conciliacao_ignorado"      # ignorou um movimento
    ACAO_CONCILIACAO_DESFEITO = "conciliacao_desfeito"      # desfez a conciliação
    ACAO_CAIXA_FECHADO = "caixa_fechado"          # fechamento de caixa do dia
    ACAO_CAIXA_REABERTO = "caixa_reaberto"        # reabertura do caixa
    ACAO_CONCIERGE_GERADO = "concierge_gerado"    # rascunho de mensagem IA (retorno/reativação)

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), index=True)
    acao = db.Column(db.String(50), nullable=False, index=True)
    recurso_tipo = db.Column(db.String(40))
    recurso_id = db.Column(db.Integer)
    detalhes = db.Column(db.String(500))
    ip = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora, index=True)

    def __repr__(self):
        return f"<AuditLog {self.id} {self.acao}>"


class WhatsAppConta(db.Model):
    """Conta WhatsApp Business (Cloud API) de UMA clínica. Multi-tenant: 1 por
    clínica (UniqueConstraint). O `phone_number_id` (id do número na Meta) roteia
    o webhook único de volta pra clínica dona. O token de acesso é SEGREDO —
    guardado CIFRADO (Fernet, ver services/cripto.py) em `token_cifrado` e nunca
    exibido ou logado. Feature INERTE por padrão: só há tráfego/custo quando
    `WHATSAPP_ATIVO` (global) está on E esta conta tem `ativo=True` + token.
    """
    __tablename__ = "whatsapp_contas"
    __table_args__ = (
        db.UniqueConstraint("clinica_id", name="uq_whatsapp_conta_clinica"),
    )

    id = db.Column(db.Integer, primary_key=True)
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"),
                           index=True, nullable=False)
    # IDs da Meta (Graph API). phone_number_id é único global (roteia o webhook).
    phone_number_id = db.Column(db.String(40), unique=True, index=True)
    waba_id = db.Column(db.String(40))            # WhatsApp Business Account id
    display_phone = db.Column(db.String(20))      # número humano (exibição)
    nome_exibicao = db.Column(db.String(120))
    token_cifrado = db.Column(db.Text)            # access token cifrado em repouso
    ativo = db.Column(db.Boolean, nullable=False, default=False)
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)
    atualizado_em = db.Column(db.DateTime(timezone=True), default=_agora,
                              onupdate=_agora)

    @property
    def configurada(self):
        """Pronta pra operar: tem número e token (não revela o token)."""
        return bool(self.phone_number_id and self.token_cifrado)

    def __repr__(self):
        return f"<WhatsAppConta {self.id} clinica={self.clinica_id}>"


class WhatsAppContato(db.Model):
    """A outra ponta de uma conversa de WhatsApp = uma 'thread' da inbox.
    `wa_id` é o número internacional só dígitos (ex.: 5543999998888). Ligado
    opcionalmente a um Paciente (casado pelo telefone) pra dar contexto clínico."""
    __tablename__ = "whatsapp_contatos"
    __table_args__ = (
        db.UniqueConstraint("clinica_id", "wa_id", name="uq_whatsapp_contato"),
    )

    id = db.Column(db.Integer, primary_key=True)
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"),
                           index=True, nullable=False)
    wa_id = db.Column(db.String(20), nullable=False, index=True)
    nome = db.Column(db.String(120))              # push name informado pela Meta
    paciente_id = db.Column(db.Integer, db.ForeignKey("pacientes.id"), index=True)
    nao_lidas = db.Column(db.Integer, nullable=False, default=0)
    ultima_em = db.Column(db.DateTime(timezone=True), default=_agora, index=True)
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)

    paciente = db.relationship("Paciente", lazy="joined")
    mensagens = db.relationship(
        "WhatsAppMensagem", back_populates="contato",
        order_by="WhatsAppMensagem.criado_em", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<WhatsAppContato {self.id} {self.wa_id}>"


class WhatsAppMensagem(db.Model):
    """Uma mensagem da thread. `direcao` in=recebida / out=enviada pela equipe.
    `wa_message_id` é o id da Meta (dedupe de webhook e correlação de status)."""
    __tablename__ = "whatsapp_mensagens"

    DIRECAO_IN = "in"
    DIRECAO_OUT = "out"

    id = db.Column(db.Integer, primary_key=True)
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"),
                           index=True, nullable=False)
    contato_id = db.Column(db.Integer, db.ForeignKey("whatsapp_contatos.id"),
                           index=True, nullable=False)
    direcao = db.Column(db.String(3), nullable=False)
    wa_message_id = db.Column(db.String(80), index=True)
    texto = db.Column(db.Text)
    status = db.Column(db.String(12))             # out: enviada|entregue|lida|falhou
    enviado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora, index=True)

    contato = db.relationship("WhatsAppContato", back_populates="mensagens")

    def __repr__(self):
        return f"<WhatsAppMensagem {self.id} {self.direcao}>"


class ConfigFiscalClinica(db.Model):
    """Config de emissão de NFS-e de UMA clínica (multi-tenant: 1 por clínica).

    Módulo INERTE por padrão: `NF_ATIVO` (global) + `ativo` (por clínica). As
    credenciais do gateway são da PLATAFORMA (variáveis de ambiente, não por clínica);
    aqui ficam os dados do EMITENTE (a clínica) e o vínculo com o emitente cadastrado
    no gateway (`gateway_empresa_id`). O **certificado A1 vai pro gateway** — não é
    guardado aqui. Ver docs/11-emissao-nf.md.
    """
    __tablename__ = "config_fiscal_clinica"
    __table_args__ = (
        db.UniqueConstraint("clinica_id", name="uq_config_fiscal_clinica"),
    )

    REGIMES = ("simples", "presumido", "real")

    id = db.Column(db.Integer, primary_key=True)
    clinica_id = db.Column(db.Integer, db.ForeignKey("clinicas.id"),
                           index=True, nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=False)
    gateway = db.Column(db.String(20), nullable=False, default="nuvemfiscal")
    gateway_empresa_id = db.Column(db.String(40))     # emitente no gateway (CNPJ)
    # Dados do prestador (a clínica) — usados pra cadastrar o emitente e na nota.
    cnpj = db.Column(db.String(14))
    razao_social = db.Column(db.String(160))
    email = db.Column(db.String(160))
    inscricao_municipal = db.Column(db.String(30))
    # Endereço do prestador (exigido pelo gateway ao cadastrar o emitente).
    logradouro = db.Column(db.String(160))
    numero = db.Column(db.String(20))
    complemento = db.Column(db.String(80))
    bairro = db.Column(db.String(80))
    cidade = db.Column(db.String(80))
    uf = db.Column(db.String(2))
    cep = db.Column(db.String(8))
    codigo_municipio_ibge = db.Column(db.String(7))   # IBGE (7 dígitos)
    regime_tributario = db.Column(db.String(12))      # simples|presumido|real
    aliquota_iss = db.Column(Numeric(5, 2))           # % de ISS
    codigo_servico = db.Column(db.String(20))         # LC116 (4.01/4.03) ou municipal
    cnae = db.Column(db.String(10))
    iss_retido_padrao = db.Column(db.Boolean, nullable=False, default=False)
    certificado_validade = db.Column(db.Date)         # status do A1 (vive no gateway)
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)
    atualizado_em = db.Column(db.DateTime(timezone=True), default=_agora,
                              onupdate=_agora)

    clinica = db.relationship("Clinica")

    @property
    def configurada(self):
        """Pronta pra emitir: emitente no gateway + dados fiscais mínimos."""
        return bool(self.gateway_empresa_id and self.cnpj
                    and self.inscricao_municipal and self.codigo_servico)

    def __repr__(self):
        return f"<ConfigFiscalClinica {self.id} clinica={self.clinica_id}>"