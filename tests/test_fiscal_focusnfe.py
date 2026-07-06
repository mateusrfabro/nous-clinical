"""Adaptador Focus NFe: fábrica/seleção por FISCAL_GATEWAY, disponibilidade,
emissão, consulta, cancelamento e erro de autenticação. NÃO faz rede real —
requests.request é monkeypatchado (a Focus usa Basic Auth, sem token OAuth)."""
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.fiscal import GatewayError, get_gateway, nf_disponivel
from app.services.fiscal.focusnfe import FocusNFeGateway
from app.services.fiscal.nuvemfiscal import NuvemFiscalGateway


class _Resp:
    def __init__(self, status, data=None):
        self.status_code = status
        self._data = data or {}

    def json(self):
        return self._data


def _conf(monkeypatch, app, *, ativo=True, token="tok-focus",
          amb="homologacao", gateway="focusnfe"):
    monkeypatch.setitem(app.config, "NF_ATIVO", ativo)
    monkeypatch.setitem(app.config, "FISCAL_GATEWAY", gateway)
    monkeypatch.setitem(app.config, "FOCUSNFE_TOKEN", token)
    monkeypatch.setitem(app.config, "FOCUSNFE_AMBIENTE", amb)


def _mock_req(monkeypatch, handler):
    """Intercepta requests.request; `handler(metodo, url, **kw) -> _Resp`."""
    import requests
    monkeypatch.setattr(requests, "request", handler)


def _cfg_emitente(**over):
    base = dict(cnpj="12345678000199", razao_social="Clínica X LTDA",
                email="a@b.com", inscricao_municipal="123",
                codigo_municipio_ibge="4106902", logradouro="Rua A", numero="1",
                complemento="", bairro="Centro", cidade="Curitiba", uf="pr",
                cep="80000000", regime_tributario="simples",
                codigo_servico="4.01")
    base.update(over)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------- fábrica/config

def test_get_gateway_focusnfe_pelo_nome(app):
    with app.app_context():
        assert isinstance(get_gateway("focusnfe"), FocusNFeGateway)


def test_default_continua_nuvemfiscal_sem_env(app, monkeypatch):
    """Comportamento preservado: sem FISCAL_GATEWAY, o default é a Nuvem Fiscal."""
    with app.app_context():
        monkeypatch.setitem(app.config, "FISCAL_GATEWAY", "nuvemfiscal")
        assert isinstance(get_gateway(), NuvemFiscalGateway)


def test_fiscal_gateway_env_muda_o_default(app, monkeypatch):
    with app.app_context():
        monkeypatch.setitem(app.config, "FISCAL_GATEWAY", "focusnfe")
        assert isinstance(get_gateway(), FocusNFeGateway)


def test_nf_disponivel_focusnfe_exige_token(app, monkeypatch):
    with app.app_context():
        _conf(monkeypatch, app, token="")
        assert nf_disponivel() is False
        _conf(monkeypatch, app, token="tok")
        assert nf_disponivel() is True


def test_nf_disponivel_nuvemfiscal_ignora_token_focus(app, monkeypatch):
    """Com o default nuvemfiscal, ter só FOCUSNFE_TOKEN não 'liga' o módulo."""
    with app.app_context():
        monkeypatch.setitem(app.config, "NF_ATIVO", True)
        monkeypatch.setitem(app.config, "FISCAL_GATEWAY", "nuvemfiscal")
        monkeypatch.setitem(app.config, "NUVEMFISCAL_CLIENT_ID", "")
        monkeypatch.setitem(app.config, "NUVEMFISCAL_CLIENT_SECRET", "")
        monkeypatch.setitem(app.config, "FOCUSNFE_TOKEN", "tok")
        assert nf_disponivel() is False


# --------------------------------------------------------------------- ping/auth

def test_ping_sem_token_levanta(app, monkeypatch):
    with app.app_context():
        _conf(monkeypatch, app, token="")
        with pytest.raises(GatewayError):
            get_gateway("focusnfe").ping()


def test_ping_ok(app, monkeypatch):
    visto = {}

    def handler(metodo, url, **kw):
        visto["auth"] = kw.get("auth")
        visto["url"] = url
        return _Resp(200, [])

    _mock_req(monkeypatch, handler)
    with app.app_context():
        _conf(monkeypatch, app)
        assert get_gateway("focusnfe").ping() is True
    # Basic Auth: token como usuário, senha vazia; ambiente homologação.
    assert visto["auth"] == ("tok-focus", "")
    assert visto["url"].startswith("https://homologacao.focusnfe.com.br")


def test_ping_token_invalido_levanta(app, monkeypatch):
    _mock_req(monkeypatch, lambda m, url, **kw: _Resp(
        401, {"codigo": "nao_autorizado", "mensagem": "credenciais inválidas"}))
    with app.app_context():
        _conf(monkeypatch, app, token="tok-ruim")
        with pytest.raises(GatewayError):
            get_gateway("focusnfe").ping()


def test_ambiente_producao_usa_api(app, monkeypatch):
    visto = {}

    def handler(metodo, url, **kw):
        visto["url"] = url
        return _Resp(200, [])

    _mock_req(monkeypatch, handler)
    with app.app_context():
        _conf(monkeypatch, app, amb="producao")
        get_gateway("focusnfe").ping()
    assert visto["url"].startswith("https://api.focusnfe.com.br")


# ---------------------------------------------------------------------- emitente

def test_cadastrar_emitente_exige_campos_minimos(app, monkeypatch):
    with app.app_context():
        _conf(monkeypatch, app)
        with pytest.raises(GatewayError):
            get_gateway("focusnfe").cadastrar_emitente(_cfg_emitente(cnpj=None))


def test_cadastrar_emitente_sucesso_retorna_id_do_gateway(app, monkeypatch):
    visto = {}

    def handler(metodo, url, **kw):
        visto["payload"] = kw.get("json")
        return _Resp(201, {"id": 4242, "token_homologacao": "th"})

    _mock_req(monkeypatch, handler)
    with app.app_context():
        _conf(monkeypatch, app)
        emp = get_gateway("focusnfe").cadastrar_emitente(_cfg_emitente())
    assert emp == "4242"                       # id numérico da Focus, como string
    assert visto["payload"]["cnpj"] == "12345678000199"
    assert visto["payload"]["municipio"] == "Curitiba"
    assert visto["payload"]["uf"] == "PR"
    assert visto["payload"]["regime_tributario"] == 1   # simples -> 1
    assert visto["payload"]["habilita_nfse"] is True


def test_cadastrar_emitente_erro_levanta(app, monkeypatch):
    _mock_req(monkeypatch, lambda m, url, **kw: _Resp(
        422, {"codigo": "dados_invalidos", "mensagem": "CNPJ inválido"}))
    with app.app_context():
        _conf(monkeypatch, app)
        with pytest.raises(GatewayError, match="CNPJ inválido"):
            get_gateway("focusnfe").cadastrar_emitente(_cfg_emitente())


# ----------------------------------------------------------------------- emissão

def _dados_nota(**over):
    base = dict(ref="nota-77",
                tomador={"cpf": "11122233344", "nome": "Paciente Y",
                         "email": "p@y.com"},
                servico={"discriminacao": "Serviços de saúde",
                         "valor_servicos": Decimal("250.00"),
                         "aliquota": Decimal("5.00")})
    base.update(over)
    return base


def test_emitir_envia_ref_e_retorna_enviando(app, monkeypatch):
    visto = {}

    def handler(metodo, url, **kw):
        visto["metodo"], visto["url"] = metodo, url
        visto["payload"] = kw.get("json")
        return _Resp(201, {"status": "processando_autorizacao"})

    _mock_req(monkeypatch, handler)
    with app.app_context():
        _conf(monkeypatch, app)
        res = get_gateway("focusnfe").emitir(_cfg_emitente(), _dados_nota())
    assert res.status == "enviando"
    assert res.gateway_nota_id == "nota-77"
    assert visto["metodo"] == "POST"
    assert visto["url"].endswith("/v2/nfse?ref=nota-77")
    assert visto["payload"]["prestador"]["cnpj"] == "12345678000199"
    assert visto["payload"]["tomador"]["cpf"] == "11122233344"
    assert visto["payload"]["servico"]["valor_servicos"] == 250.0
    # LC116 default sai do config quando o serviço não especifica.
    assert visto["payload"]["servico"]["item_lista_servico"] == "4.01"


def test_emitir_sem_ref_gera_uma(app, monkeypatch):
    _mock_req(monkeypatch, lambda m, url, **kw: _Resp(
        201, {"status": "processando_autorizacao"}))
    with app.app_context():
        _conf(monkeypatch, app)
        dados = _dados_nota()
        dados.pop("ref")
        res = get_gateway("focusnfe").emitir(_cfg_emitente(), dados)
    assert res.status == "enviando"
    assert res.gateway_nota_id                 # ref gerada (uuid4 hex)


def test_emitir_erro_de_validacao_levanta(app, monkeypatch):
    _mock_req(monkeypatch, lambda m, url, **kw: _Resp(
        400, {"codigo": "requisicao_invalida", "mensagem": "CPF do tomador inválido"}))
    with app.app_context():
        _conf(monkeypatch, app)
        with pytest.raises(GatewayError, match="CPF do tomador"):
            get_gateway("focusnfe").emitir(_cfg_emitente(), _dados_nota())


# ---------------------------------------------------------------------- consulta

def test_consultar_autorizada_mapeia_campos(app, monkeypatch):
    _mock_req(monkeypatch, lambda m, url, **kw: _Resp(200, {
        "status": "autorizado", "numero": "123",
        "codigo_verificacao": "ABC123",
        "url_danfse": "https://focus/DANFSEs/x.pdf",
        "caminho_xml_nota_fiscal": "/arquivos/x.xml"}))
    with app.app_context():
        _conf(monkeypatch, app)
        res = get_gateway("focusnfe").consultar(_cfg_emitente(), "nota-77")
    assert res.status == "autorizada"
    assert res.numero == "123"
    assert res.codigo_verificacao == "ABC123"
    assert res.link_pdf == "https://focus/DANFSEs/x.pdf"
    assert res.link_xml == "/arquivos/x.xml"
    assert res.mensagem_erro is None


def test_consultar_rejeitada_junta_mensagens_de_erro(app, monkeypatch):
    _mock_req(monkeypatch, lambda m, url, **kw: _Resp(200, {
        "status": "erro_autorizacao",
        "erros": [{"codigo": "L99", "mensagem": "Regime inválido",
                   "correcao": "Corrija o regime"}]}))
    with app.app_context():
        _conf(monkeypatch, app)
        res = get_gateway("focusnfe").consultar(_cfg_emitente(), "nota-77")
    assert res.status == "rejeitada"
    assert "Regime inválido" in res.mensagem_erro


def test_consultar_processando_vira_enviando(app, monkeypatch):
    _mock_req(monkeypatch, lambda m, url, **kw: _Resp(
        200, {"status": "processando_autorizacao"}))
    with app.app_context():
        _conf(monkeypatch, app)
        res = get_gateway("focusnfe").consultar(_cfg_emitente(), "nota-77")
    assert res.status == "enviando"


def test_consultar_nao_encontrada_levanta(app, monkeypatch):
    _mock_req(monkeypatch, lambda m, url, **kw: _Resp(
        404, {"codigo": "nao_encontrado", "mensagem": "Nota fiscal não encontrada"}))
    with app.app_context():
        _conf(monkeypatch, app)
        with pytest.raises(GatewayError):
            get_gateway("focusnfe").consultar(_cfg_emitente(), "nao-existe")


# ------------------------------------------------------------------ cancelamento

def test_cancelar_ok(app, monkeypatch):
    visto = {}

    def handler(metodo, url, **kw):
        visto["metodo"], visto["url"] = metodo, url
        visto["payload"] = kw.get("json")
        return _Resp(200, {"status": "cancelado"})

    _mock_req(monkeypatch, handler)
    with app.app_context():
        _conf(monkeypatch, app)
        res = get_gateway("focusnfe").cancelar(
            _cfg_emitente(), "nota-77", "Erro na emissão da nota fiscal")
    assert res.status == "cancelada"
    assert visto["metodo"] == "DELETE"
    assert visto["url"].endswith("/v2/nfse/nota-77")
    assert visto["payload"]["justificativa"] == "Erro na emissão da nota fiscal"


def test_cancelar_justificativa_curta_e_completada(app, monkeypatch):
    """Doc Focus: justificativa 15–255 chars; motivo curto é complementado."""
    visto = {}

    def handler(metodo, url, **kw):
        visto["payload"] = kw.get("json")
        return _Resp(200, {"status": "cancelado"})

    _mock_req(monkeypatch, handler)
    with app.app_context():
        _conf(monkeypatch, app)
        get_gateway("focusnfe").cancelar(_cfg_emitente(), "nota-77", "erro")
    assert len(visto["payload"]["justificativa"]) >= 15


def test_cancelar_recusado_levanta(app, monkeypatch):
    _mock_req(monkeypatch, lambda m, url, **kw: _Resp(200, {
        "status": "erro_cancelamento",
        "erros": [{"codigo": "V999",
                   "mensagem": "NFSe fora do prazo de cancelamento"}]}))
    with app.app_context():
        _conf(monkeypatch, app)
        with pytest.raises(GatewayError, match="fora do prazo"):
            get_gateway("focusnfe").cancelar(_cfg_emitente(), "nota-77",
                                             "Erro na emissão da nota fiscal")


def test_cancelar_nao_autorizada_levanta(app, monkeypatch):
    _mock_req(monkeypatch, lambda m, url, **kw: _Resp(400, {
        "codigo": "nfe_nao_autorizada",
        "mensagem": "Nota fiscal não autorizada não pode ser cancelada"}))
    with app.app_context():
        _conf(monkeypatch, app)
        with pytest.raises(GatewayError):
            get_gateway("focusnfe").cancelar(_cfg_emitente(), "nota-77",
                                             "Erro na emissão da nota fiscal")
