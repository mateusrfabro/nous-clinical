"""Conciliação bancária (OFX): parser, importação/dedup, sugestão e fluxo."""
import io
from datetime import datetime, time, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app import db
from app.models import LancamentoFinanceiro, MovimentoBancario
from app.services.ofx import parse_ofx, OFXError
from app.services.conciliacao import sugestao_para

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


def _upload(client):
    return client.post(
        "/financeiro/conciliacao/importar",
        data={"extrato": (io.BytesIO(_OFX.encode("utf-8")), "extrato.ofx")},
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
