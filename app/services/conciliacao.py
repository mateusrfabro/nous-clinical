"""Conciliação bancária: importa transações do extrato (OFX) como
MovimentoBancario e sugere o LancamentoFinanceiro correspondente.

Regras de match (sugestão; o usuário confirma):
- crédito (entrada) casa com receita; débito (saída) casa com despesa.
- mesmo VALOR exato + tipo compatível + lançamento ainda NÃO conciliado +
  data próxima (janela de ±7 dias entre a data do extrato e a data do
  lançamento — pago_em, senão vencimento, senão criado_em).
- entre vários candidatos, o de data mais próxima vence.
"""
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app import db
from app.models import LancamentoFinanceiro, MovimentoBancario

_BR_TZ = ZoneInfo("America/Sao_Paulo")
_JANELA_DIAS = 7   # tolerância de data entre extrato e lançamento


def _data_lancamento(lanc):
    """Data de referência do lançamento p/ comparar com o extrato (em BR)."""
    if lanc.pago_em:
        return lanc.pago_em.astimezone(_BR_TZ).date()
    if lanc.vencimento:
        return lanc.vencimento
    if lanc.criado_em:
        return lanc.criado_em.astimezone(_BR_TZ).date()
    return None


def importar_extrato(extrato, clinica_id, usuario_id):
    """Cria os MovimentoBancario do extrato. Dedup por (conta, fitid) já
    existente na clínica. Retorna (novos, duplicados)."""
    conta = extrato.conta or None
    # FITIDs já importados desta conta (escopo de clínica é automático).
    ja = set(db.session.execute(
        select(MovimentoBancario.fitid).where(
            MovimentoBancario.conta.is_(conta) if conta is None
            else MovimentoBancario.conta == conta,
            MovimentoBancario.fitid.is_not(None),
        )
    ).scalars())

    novos = duplicados = 0
    for t in extrato.transacoes:
        if t.fitid and t.fitid in ja:
            duplicados += 1
            continue
        db.session.add(MovimentoBancario(
            clinica_id=clinica_id,
            data=t.data, valor=t.valor, tipo=t.tipo,
            descricao=t.descricao or None,
            fitid=t.fitid or None,
            conta=conta, banco=extrato.banco or None,
            status=MovimentoBancario.STATUS_PENDENTE,
            importado_por_id=usuario_id,
        ))
        if t.fitid:
            ja.add(t.fitid)
        novos += 1
    db.session.commit()
    return novos, duplicados


def sugestao_para(mov):
    """Melhor LancamentoFinanceiro candidato p/ conciliar com o movimento, ou
    None. Não altera nada — só sugere."""
    L = LancamentoFinanceiro
    alvo = (L.TIPO_RECEITA if mov.tipo == MovimentoBancario.TIPO_CREDITO
            else L.TIPO_DESPESA)
    # Lançamentos já conciliados (têm movimento) ficam de fora.
    usados = select(MovimentoBancario.lancamento_id).where(
        MovimentoBancario.lancamento_id.is_not(None))
    candidatos = db.session.execute(
        select(L).where(
            L.tipo == alvo,
            L.valor == mov.valor,
            L.status != L.STATUS_CANCELADO,
            L.id.notin_(usados),
        )
    ).scalars().all()
    if not candidatos:
        return None

    def distancia(lanc):
        d = _data_lancamento(lanc)
        return abs((d - mov.data).days) if d else 10**6

    melhor = min(candidatos, key=distancia)
    return melhor if distancia(melhor) <= _JANELA_DIAS else None


def candidatos_para(mov, limite=50):
    """Lançamentos não conciliados compatíveis com o movimento (mesmo tipo),
    ordenados por proximidade de data — para a CONCILIAÇÃO MANUAL (o usuário
    escolhe um quando o valor não bate com a sugestão automática). Sem corte de
    janela: lista tudo que faz sentido, mais próximo primeiro."""
    L = LancamentoFinanceiro
    alvo = (L.TIPO_RECEITA if mov.tipo == MovimentoBancario.TIPO_CREDITO
            else L.TIPO_DESPESA)
    usados = select(MovimentoBancario.lancamento_id).where(
        MovimentoBancario.lancamento_id.is_not(None))
    candidatos = db.session.execute(
        select(L).where(
            L.tipo == alvo,
            L.status != L.STATUS_CANCELADO,
            L.id.notin_(usados),
        )
    ).scalars().all()

    def chave(lanc):
        d = _data_lancamento(lanc)
        # mais próximo por data; desempata por |diferença de valor|.
        return (abs((d - mov.data).days) if d else 10**6,
                abs(lanc.valor - mov.valor))

    return sorted(candidatos, key=chave)[:limite]


def lancamentos_nao_conciliados(clinica_id, desde):
    """Lançamentos PAGOS (receita) ainda sem movimento conciliado desde uma
    data — o "outro lado" da divergência (esperado no banco, não apareceu)."""
    L = LancamentoFinanceiro
    usados = select(MovimentoBancario.lancamento_id).where(
        MovimentoBancario.lancamento_id.is_not(None))
    return db.session.execute(
        select(L).where(
            L.tipo == L.TIPO_RECEITA, L.status == L.STATUS_PAGO,
            L.pago_em >= desde, L.id.notin_(usados),
        ).order_by(L.pago_em.desc())
    ).scalars().all()
