"""Modelos do dominio: gestao de clinica / agenda.

Convencoes herdadas da plataforma:
- Dinheiro SEMPRE Numeric(12, 2) — nunca Float.
- Datas SEMPRE DateTime(timezone=True), armazenadas em UTC. Display converte
  pro fuso de Brasilia nos filtros Jinja (data_br / datetime_br / hora_br).
- Acesso por papel via Usuario.tipo: admin | profissional | recepcao.

Dados de saude sao "dados sensiveis" pela LGPD (art. 5, II). Prontuario
(Atendimento) so e acessivel por profissional/admin — nunca pela recepcao.
"""
from datetime import datetime, timezone

from flask_login import UserMixin
from sqlalchemy import Numeric

from app import db, login_manager


def _agora():
    return datetime.now(timezone.utc)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(Usuario, int(user_id))


class Usuario(UserMixin, db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    nome_responsavel = db.Column(db.String(150), nullable=False)
    telefone = db.Column(db.String(30))
    # admin | profissional | recepcao
    tipo = db.Column(db.String(20), nullable=False, default="recepcao")
    ativo = db.Column(db.Boolean, nullable=False, default=True)

    # Canal opcional de notificacao/reset de senha.
    telegram_chat_id = db.Column(db.String(40))

    aceite_termos_em = db.Column(db.DateTime(timezone=True))
    senha_atualizada_em = db.Column(db.DateTime(timezone=True))
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)

    profissional = db.relationship(
        "Profissional", back_populates="usuario", uselist=False
    )

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
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)

    usuario = db.relationship("Usuario", back_populates="profissional")
    agendamentos = db.relationship("Agendamento", back_populates="profissional")

    def __repr__(self):
        return f"<Profissional {self.id} {self.nome}>"


class Paciente(db.Model):
    __tablename__ = "pacientes"

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

    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)
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
    observacoes = db.Column(db.Text)

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


class Atendimento(db.Model):
    """Prontuario clinico de uma consulta. DADO SENSIVEL (LGPD).

    Acesso restrito a profissional/admin. Append-only na pratica: edicoes
    deveriam virar adendos, mas pro MVP permitimos editar enquanto o
    atendimento e do dia (regra aplicada na rota, nao no modelo).
    """
    __tablename__ = "atendimentos"

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

    criado_em = db.Column(db.DateTime(timezone=True), default=_agora)
    criado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"))

    paciente = db.relationship("Paciente", back_populates="lancamentos")
    agendamento = db.relationship("Agendamento", back_populates="lancamento")

    @property
    def vencido(self):
        """True se pendente e o vencimento ja passou (compara em data BR)."""
        if self.status != self.STATUS_PENDENTE or not self.vencimento:
            return False
        from datetime import date
        return self.vencimento < date.today()

    def __repr__(self):
        return f"<LancamentoFinanceiro {self.id} {self.tipo} {self.status} {self.valor}>"


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
    ACAO_AGENDAMENTO_CRIADO = "agendamento_criado"
    ACAO_AGENDAMENTO_STATUS = "agendamento_status"
    ACAO_AGENDAMENTO_EDITADO = "agendamento_editado"
    ACAO_ATENDIMENTO_REGISTRADO = "atendimento_registrado"
    ACAO_PROFISSIONAL_CRIADO = "profissional_criado"
    ACAO_LANCAMENTO_CRIADO = "lancamento_criado"
    ACAO_LANCAMENTO_PAGO = "lancamento_pago"
    ACAO_LANCAMENTO_CANCELADO = "lancamento_cancelado"
    ACAO_PROCEDIMENTO_SALVO = "procedimento_salvo"
    ACAO_EXAME_ANEXADO = "exame_anexado"
    ACAO_EXAME_REMOVIDO = "exame_removido"
    # Acesso a dado sensivel (LGPD art. 37 — registro de operacoes de
    # tratamento). Le/visualiza/exporta — nao so altera.
    ACAO_PRONTUARIO_VISUALIZADO = "prontuario_visualizado"
    ACAO_EXAME_BAIXADO = "exame_baixado"
    ACAO_RELATORIO_EXPORTADO = "relatorio_exportado"

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