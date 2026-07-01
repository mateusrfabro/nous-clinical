"""Conciliação bancária (OFX): parser, importação/dedup, sugestão e fluxo."""
import io
from datetime import datetime, time, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app import db
from app.models import LancamentoFinanceiro, MovimentoBancario
from app.services.ofx import parse_ofx, OFXError
from app.services.extrato import parse_extrato, parse_csv
from app.services.conciliacao import (
    sugestao_para, candidatos_para, lancamentos_nao_conciliados,
)

_BR = ZoneInfo("America/Sao_Paulo")

_OFX = """OFXHEADER:100
DATA:OFXSGML
VERSION:102
<OFX>
<BANKMSGSRSV1><STMTTRNRS><STMTRS>
<BANKACCTFROM><BANKID>001<ACCTID>12345-6</BANKACCTFROM>
<BANKTRANLIST>
<STMTTRN><TRNTYPE>CREDIT<DTPOSTED>20260605120000[-3:GMT]<TRNAMT>150.00<FITID>TX001<MEMO>PIX CONSULTA</STMTTRN>
<STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20260606<TRNAMT>-80.00<FITID>TX002<MEMO>TARIFA BANCO</STMTTRN>
</BANKTRANLIST>
</STMTRS></STMTTRNRS></BANKMSGSRSV1>
</OFX>
"""


_CSV = (
    "Data;Valor;Histórico\n"
    "05/06/2026;150,00;PIX CONSULTA\n"
    "06/06/2026;-80,00;TARIFA BANCO\n"
)


def _upload(client):
    return client.post(
        "/financeiro/conciliacao/importar",
        data={"extrato": (io.BytesIO(_OFX.encode("utf-8")), "extrato.ofx")},
        content_type="multipart/form-data", follow_redirects=True)


def _upload_csv(client):
    return client.post(
        "/financeiro/conciliacao/importar",
        data={"extrato": (io.BytesIO(_CSV.encode("utf-8")), "extrato.csv")},
        content_type="multipart/form-data", follow_redirects=True)


# ---------------- parser (unit) ----------------

def test_ofx_parser_le_transacoes():
    ext = parse_ofx(_OFX)
    assert ext.conta == "12345-6"
    assert len(ext.transacoes) == 2
    cred = ext.transacoes[0]
    assert cred.tipo == "credito"
    assert cred.valor == Decimal("150.00")
    assert cred.fitid == "TX001"
    assert cred.data.isoformat() == "2026-06-05"
    deb = ext.transacoes[1]
    assert deb.tipo == "debito"
    assert deb.valor == Decimal("80.00")   # sempre positivo


def test_csv_parser_le_transacoes():
    ext = parse_csv(_CSV)
    assert len(ext.transacoes) == 2
    cred = ext.transacoes[0]
    assert cred.tipo == "credito" and cred.valor == Decimal("150.00")
    assert cred.data.isoformat() == "2026-06-05"
    assert cred.fitid.startswith("csv")   # fitid sintetizado p/ dedup
    deb = ext.transacoes[1]
    assert deb.tipo == "debito" and deb.valor == Decimal("80.00")


def test_csv_debito_entre_parenteses():
    """Formato contábil: (50,00) é DÉBITO (saída), não crédito."""
    csv_paren = ("Data;Valor;Histórico\n"
                 "10/06/2026;(50,00);TARIFA\n"
                 "11/06/2026;200,00;PIX\n")
    ext = parse_csv(csv_paren)
    tarifa = next(t for t in ext.transacoes if "TARIFA" in t.descricao)
    assert tarifa.tipo == "debito" and tarifa.valor == Decimal("50.00")
    pix = next(t for t in ext.transacoes if "PIX" in t.descricao)
    assert pix.tipo == "credito"


def test_parse_extrato_dispatch_por_nome():
    assert len(parse_extrato("x.csv", _CSV.encode("utf-8")).transacoes) == 2
    assert len(parse_extrato("x.ofx", _OFX.encode("utf-8")).transacoes) == 2


def test_importar_csv_e_dedup(client_admin, app):
    _upload_csv(client_admin)
    with app.app_context():
        from app.models import MovimentoBancario as M
        assert M.query.count() == 2
    _upload_csv(client_admin)   # reimport: dedup por fitid sintetizado
    with app.app_context():
        from app.models import MovimentoBancario as M
        assert M.query.count() == 2


def test_ofx_parser_rejeita_lixo():
    try:
        parse_ofx(b"isto nao e um ofx")
        assert False, "deveria lançar OFXError"
    except OFXError:
        pass


# ---------------- acesso ----------------

def test_conciliacao_profissional_negado(client_prof):
    r = client_prof.get("/financeiro/conciliacao")
    assert r.status_code in (301, 302, 403)


def test_conciliacao_admin_ok(client_admin):
    assert client_admin.get("/financeiro/conciliacao").status_code == 200


# ---------------- importação + dedup ----------------

def test_importar_cria_movimentos(client_admin, app):
    r = _upload(client_admin)
    assert r.status_code == 200
    with app.app_context():
        movs = MovimentoBancario.query.all()
        assert len(movs) == 2
        assert {m.fitid for m in movs} == {"TX001", "TX002"}


def test_importar_dedup(client_admin, app):
    _upload(client_admin)
    _upload(client_admin)   # 2ª vez: tudo duplicado
    with app.app_context():
        assert MovimentoBancario.query.count() == 2


# ---------------- sugestão de match ----------------

def test_sugestao_casa_lancamento(client_admin, app):
    with app.app_context():
        pago = datetime.combine(__import__("datetime").date(2026, 6, 5),
                                time(12, 0), tzinfo=_BR).astimezone(timezone.utc)
        db.session.add(LancamentoFinanceiro(
            tipo=LancamentoFinanceiro.TIPO_RECEITA,
            status=LancamentoFinanceiro.STATUS_PAGO,
            categoria="consulta", descricao="Consulta particular",
            valor=Decimal("150.00"), pago_em=pago))
        db.session.commit()
    _upload(client_admin)
    with app.app_context():
        cred = MovimentoBancario.query.filter_by(fitid="TX001").first()
        sug = sugestao_para(cred)
        assert sug is not None
        assert sug.valor == Decimal("150.00")
        # débito (tarifa) não tem despesa correspondente -> sem sugestão
        deb = MovimentoBancario.query.filter_by(fitid="TX002").first()
        assert sugestao_para(deb) is None


# ---------------- fluxo: conciliar / criar / ignorar / desfazer ----------------

def test_conciliar_com_lancamento(client_admin, app):
    with app.app_context():
        pago = datetime.now(timezone.utc)
        lanc = LancamentoFinanceiro(
            tipo=LancamentoFinanceiro.TIPO_RECEITA,
            status=LancamentoFinanceiro.STATUS_PAGO, categoria="consulta",
            descricao="Consulta", valor=Decimal("150.00"), pago_em=pago)
        db.session.add(lanc)
        db.session.commit()
        lanc_id = lanc.id
    _upload(client_admin)
    with app.app_context():
        mov_id = MovimentoBancario.query.filter_by(fitid="TX001").first().id
    r = client_admin.post(
        f"/financeiro/conciliacao/{mov_id}/conciliar",
        data={"lancamento_id": lanc_id}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        mov = db.session.get(MovimentoBancario, mov_id)
        assert mov.status == "conciliado"
        assert mov.lancamento_id == lanc_id


def test_criar_lancamento_do_movimento(client_admin, app):
    _upload(client_admin)
    with app.app_context():
        mov_id = MovimentoBancario.query.filter_by(fitid="TX001").first().id
        antes = LancamentoFinanceiro.query.count()
    r = client_admin.post(
        f"/financeiro/conciliacao/{mov_id}/criar", follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        assert LancamentoFinanceiro.query.count() == antes + 1
        mov = db.session.get(MovimentoBancario, mov_id)
        assert mov.status == "conciliado"
        lanc = db.session.get(LancamentoFinanceiro, mov.lancamento_id)
        assert lanc.tipo == "receita" and lanc.valor == Decimal("150.00")
        assert lanc.status == "pago"


def test_conciliacao_manual_valor_diferente(client_admin, app):
    """Conciliação MANUAL: casa o movimento de 150 com um lançamento de valor
    diferente (ex.: 145 + 5 de tarifa) — o que a sugestão automática não faria."""
    with app.app_context():
        db.session.add(LancamentoFinanceiro(
            tipo=LancamentoFinanceiro.TIPO_RECEITA,
            status=LancamentoFinanceiro.STATUS_PAGO, categoria="consulta",
            descricao="Consulta 145", valor=Decimal("145.00"),
            pago_em=datetime.now(timezone.utc)))
        db.session.commit()
    _upload(client_admin)
    with app.app_context():
        cred = MovimentoBancario.query.filter_by(fitid="TX001").first()
        # sem sugestão automática (valor não bate)
        assert sugestao_para(cred) is None
        # mas aparece como CANDIDATO manual
        cands = candidatos_para(cred)
        assert any(c.valor == Decimal("145.00") for c in cands)
        cand_id = cands[0].id
        mov_id = cred.id
    # tela de detalhe abre
    assert client_admin.get(f"/financeiro/conciliacao/{mov_id}").status_code == 200
    # concilia manualmente
    r = client_admin.post(
        f"/financeiro/conciliacao/{mov_id}/conciliar",
        data={"lancamento_id": cand_id}, follow_redirects=True)
    assert r.status_code == 200
    with app.app_context():
        mov = db.session.get(MovimentoBancario, mov_id)
        assert mov.status == "conciliado" and mov.lancamento_id == cand_id


def test_lancamentos_sem_extrato(client_admin, app):
    """Receita paga não conciliada conta como 'recebido sem extrato'."""
    with app.app_context():
        db.session.add(LancamentoFinanceiro(
            tipo=LancamentoFinanceiro.TIPO_RECEITA,
            status=LancamentoFinanceiro.STATUS_PAGO, categoria="consulta",
            descricao="Recebido", valor=Decimal("300.00"),
            pago_em=datetime.now(timezone.utc)))
        db.session.commit()
        desde = datetime.now(timezone.utc).replace(year=2000)
        clinica_id = LancamentoFinanceiro.query.first().clinica_id
        sem = lancamentos_nao_conciliados(clinica_id, desde)
        assert any(x.valor == Decimal("300.00") for x in sem)


def test_divergencias_painel(client_admin, app):
    with app.app_context():
        db.session.add(LancamentoFinanceiro(
            tipo=LancamentoFinanceiro.TIPO_RECEITA,
            status=LancamentoFinanceiro.STATUS_PAGO, categoria="consulta",
            descricao="Recebido sem extrato", valor=Decimal("300.00"),
            pago_em=datetime.now(timezone.utc)))
        db.session.commit()
    _upload(client_admin)   # 2 movimentos pendentes
    r = client_admin.get("/financeiro/conciliacao/divergencias")
    assert r.status_code == 200
    assert "Extrato sem lançamento".encode() in r.data
    assert "Recebido sem extrato".encode() in r.data
    assert b"PIX CONSULTA" in r.data          # movimento pendente
    assert b"300,00" in r.data                # lançamento sem extrato


def test_ignorar_e_desfazer(client_admin, app):
    _upload(client_admin)
    with app.app_context():
        mov_id = MovimentoBancario.query.filter_by(fitid="TX002").first().id
    client_admin.post(f"/financeiro/conciliacao/{mov_id}/ignorar",
                      follow_redirects=True)
    with app.app_context():
        assert db.session.get(MovimentoBancario, mov_id).status == "ignorado"
    client_admin.post(f"/financeiro/conciliacao/{mov_id}/desfazer",
                      follow_redirects=True)
    with app.app_context():
        assert db.session.get(MovimentoBancario, mov_id).status == "pendente"


def test_criar_nao_duplica_receita(client_recepcao, app):
    """#2: 'criar a partir do movimento' é bloqueado quando já existe um
    lançamento que casa — senão duplicaria a receita no faturamento/DRE."""
    _upload(client_recepcao)
    mov = db.session.execute(
        db.select(MovimentoBancario).where(
            MovimentoBancario.tipo == MovimentoBancario.TIPO_CREDITO)
    ).scalars().first()
    pago = datetime.combine(mov.data, time(12, 0),
                            tzinfo=_BR).astimezone(timezone.utc)
    db.session.add(LancamentoFinanceiro(
        tipo=LancamentoFinanceiro.TIPO_RECEITA, valor=mov.valor,
        status=LancamentoFinanceiro.STATUS_PAGO, pago_em=pago,
        descricao="Consulta recebida"))
    db.session.commit()
    antes = len(db.session.execute(db.select(LancamentoFinanceiro)).scalars().all())
    r = client_recepcao.post(f"/financeiro/conciliacao/{mov.id}/criar",
                             follow_redirects=True)
    depois = len(db.session.execute(db.select(LancamentoFinanceiro)).scalars().all())
    assert depois == antes          # NÃO criou um segundo lançamento (duplicata)
    assert "Conciliar".encode() in r.data
