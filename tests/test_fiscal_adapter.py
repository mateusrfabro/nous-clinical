"""Adaptador fiscal (NFS-e via Nuvem Fiscal): fábrica, disponibilidade, auth/token
e cache. NÃO faz rede real — requests.post é monkeypatchado."""
import pytest

from app.services.fiscal import GatewayError, get_gateway, nf_disponivel
from app.services.fiscal.nuvemfiscal import NuvemFiscalGateway


class _Resp:
    def __init__(self, status, data=None):
        self.status_code = status
        self._data = data or {}

    def json(self):
        return self._data


def _conf(monkeypatch, app, *, ativo=True, cid="cid-teste",
          secret="seg-teste", amb="sandbox"):
    monkeypatch.setitem(app.config, "NF_ATIVO", ativo)
    monkeypatch.setitem(app.config, "NUVEMFISCAL_CLIENT_ID", cid)
    monkeypatch.setitem(app.config, "NUVEMFISCAL_CLIENT_SECRET", secret)
    monkeypatch.setitem(app.config, "NUVEMFISCAL_AMBIENTE", amb)


def test_nf_indisponivel_por_padrao(app, monkeypatch):
    with app.app_context():
        monkeypatch.setitem(app.config, "NF_ATIVO", False)
        assert nf_disponivel() is False


def test_nf_disponivel_quando_configurado(app, monkeypatch):
    with app.app_context():
        _conf(monkeypatch, app)
        assert nf_disponivel() is True


def test_get_gateway_conhecido_e_default_e_desconhecido(app):
    with app.app_context():
        assert isinstance(get_gateway("nuvemfiscal"), NuvemFiscalGateway)
        assert isinstance(get_gateway(), NuvemFiscalGateway)      # default
        with pytest.raises(GatewayError):
            get_gateway("inexistente")


def test_token_sem_credencial_levanta(app, monkeypatch):
    with app.app_context():
        _conf(monkeypatch, app, cid="", secret="")
        with pytest.raises(GatewayError):
            get_gateway().ping()


def test_ping_autentica_e_cacheia_o_token(app, monkeypatch):
    import requests
    chamadas = {"n": 0}

    def fake_post(url, **kw):
        chamadas["n"] += 1
        return _Resp(200, {"access_token": "tok-123", "expires_in": 3600})

    monkeypatch.setattr(requests, "post", fake_post)
    with app.app_context():
        _conf(monkeypatch, app, cid="cache-cid")
        NuvemFiscalGateway._token_cache.pop("cache-cid", None)
        g = get_gateway()
        assert g.ping() is True
        assert g._token() == "tok-123"
        assert chamadas["n"] == 1          # 2ª chamada veio do cache, não da rede


def test_token_credencial_invalida_levanta(app, monkeypatch):
    import requests
    monkeypatch.setattr(requests, "post", lambda url, **kw: _Resp(401, {}))
    with app.app_context():
        _conf(monkeypatch, app, cid="cid-ruim")
        NuvemFiscalGateway._token_cache.pop("cid-ruim", None)
        with pytest.raises(GatewayError):
            get_gateway().ping()
