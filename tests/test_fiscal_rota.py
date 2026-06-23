"""Tela de configuração fiscal (/configuracoes/fiscal): gating por NF_ATIVO,
admin-only e salvamento da config do emitente."""
from sqlalchemy import select

from app import db
from app.models import ConfigFiscalClinica


def _liga_nf(monkeypatch, app):
    monkeypatch.setitem(app.config, "NF_ATIVO", True)
    monkeypatch.setitem(app.config, "NUVEMFISCAL_CLIENT_ID", "cid")
    monkeypatch.setitem(app.config, "NUVEMFISCAL_CLIENT_SECRET", "seg")


def test_fiscal_404_quando_modulo_desligado(app, client_admin, monkeypatch):
    monkeypatch.setitem(app.config, "NF_ATIVO", False)
    r = client_admin.get("/configuracoes/fiscal")
    assert r.status_code == 404


def test_fiscal_so_admin(app, client_recepcao, monkeypatch):
    _liga_nf(monkeypatch, app)
    r = client_recepcao.get("/configuracoes/fiscal")
    assert r.status_code in (403, 302)


def test_fiscal_get_admin_ok(app, client_admin, monkeypatch):
    _liga_nf(monkeypatch, app)
    r = client_admin.get("/configuracoes/fiscal")
    assert r.status_code == 200
    assert b"Nota Fiscal" in r.data


def test_fiscal_salva_config_do_emitente(app, client_admin, monkeypatch):
    _liga_nf(monkeypatch, app)
    r = client_admin.post("/configuracoes/fiscal", data={
        "ativo": "on",
        "cnpj": "12.345.678/0001-99",
        "razao_social": "Clínica Teste LTDA",
        "inscricao_municipal": "987654",
        "codigo_municipio_ibge": "4106902",
        "regime_tributario": "simples",
        "aliquota_iss": "5,00",
        "codigo_servico": "4.01",
    })
    assert r.status_code == 302
    with app.app_context():
        cfg = db.session.execute(
            select(ConfigFiscalClinica)).scalars().first()
        assert cfg is not None
        assert cfg.cnpj == "12345678000199"      # só dígitos
        assert cfg.ativo is True
        assert cfg.codigo_servico == "4.01"
        assert str(cfg.aliquota_iss) == "5.00"
        assert cfg.regime_tributario == "simples"
        # Ainda NÃO está pronta pra emitir: falta cadastrar o emitente no gateway
        # (gateway_empresa_id), que é o próximo passo.
        assert cfg.configurada is False
