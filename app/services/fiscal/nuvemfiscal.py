"""Adaptador Nuvem Fiscal (NFS-e).

OAuth2 `client_credentials` -> Bearer token (cacheado até expirar). Base URL por
ambiente (sandbox|producao). HTTP via `requests` (import lazy, como no resto do
projeto). Os segredos vêm do config (variáveis de ambiente) — nunca do código/repo.

Esta fase entrega a fundação (auth + plumbing). Cadastro de emitente e emissão são
preenchidos nas fases seguintes (precisam do certificado A1 e do modelo de dados).
"""
import logging
import time

from flask import current_app

from .base import GatewayNFSe, GatewayError

logger = logging.getLogger(__name__)

_AUTH_URL = "https://auth.nuvemfiscal.com.br/oauth/token"
_BASE_URLS = {
    "sandbox": "https://api.sandbox.nuvemfiscal.com.br",
    "producao": "https://api.nuvemfiscal.com.br",
}
_SCOPES = "conta empresa nfse cnpj cep"


class NuvemFiscalGateway(GatewayNFSe):
    nome = "nuvemfiscal"
    # Cache de token por client_id: {client_id: (token, expira_epoch)}. Por processo.
    _token_cache: dict = {}

    def _cfg(self):
        c = current_app.config
        cid = c.get("NUVEMFISCAL_CLIENT_ID")
        secret = c.get("NUVEMFISCAL_CLIENT_SECRET")
        amb = (c.get("NUVEMFISCAL_AMBIENTE") or "sandbox").lower()
        if not cid or not secret:
            raise GatewayError(
                "Credenciais da Nuvem Fiscal não configuradas "
                "(defina NUVEMFISCAL_CLIENT_ID e NUVEMFISCAL_CLIENT_SECRET).")
        if amb not in _BASE_URLS:
            amb = "sandbox"
        return cid, secret, amb

    def _token(self):
        cid, secret, _ = self._cfg()
        agora = time.time()
        cache = NuvemFiscalGateway._token_cache.get(cid)
        if cache and cache[1] - 60 > agora:      # 60s de folga antes de expirar
            return cache[0]
        import requests
        try:
            r = requests.post(_AUTH_URL, data={
                "grant_type": "client_credentials",
                "client_id": cid,
                "client_secret": secret,
                "scope": _SCOPES,
            }, timeout=20)
        except requests.RequestException as exc:
            raise GatewayError("Falha ao autenticar na Nuvem Fiscal.") from exc
        if r.status_code != 200:
            logger.warning("NUVEMFISCAL auth HTTP %s", r.status_code)
            raise GatewayError(
                "Credenciais da Nuvem Fiscal inválidas (verifique CLIENT_ID/SECRET "
                "e o ambiente).")
        dados = r.json()
        token = dados.get("access_token")
        if not token:
            raise GatewayError("Nuvem Fiscal não retornou token de acesso.")
        expira = agora + int(dados.get("expires_in", 3600))
        NuvemFiscalGateway._token_cache[cid] = (token, expira)
        return token

    def _base_url(self):
        return _BASE_URLS[self._cfg()[2]]

    def _req(self, metodo, path, **kw):
        import requests
        headers = kw.pop("headers", {})
        headers["Authorization"] = "Bearer " + self._token()
        try:
            return requests.request(metodo, self._base_url() + path,
                                    headers=headers, timeout=30, **kw)
        except requests.RequestException as exc:
            raise GatewayError("Falha de comunicação com a Nuvem Fiscal.") from exc

    def ping(self):
        """Valida as credenciais autenticando (não emite nada). True ou GatewayError."""
        self._token()
        return True

    def _erro_msg(self, r):
        try:
            d = r.json()
            return d.get("message") or d.get("error") or str(d)[:200]
        except Exception:   # noqa: BLE001 — corpo não-JSON
            return f"HTTP {r.status_code}"

    def cadastrar_emitente(self, config):
        """Cadastra a empresa emitente (POST /empresas). NÃO exige certificado.
        Retorna o identificador no gateway (o CNPJ). Idempotente: se já existe
        (HTTP 409), considera ok."""
        if not (config.cnpj and config.razao_social
                and config.inscricao_municipal and config.codigo_municipio_ibge):
            raise GatewayError(
                "Preencha CNPJ, razão social, inscrição municipal e código IBGE "
                "do município antes de cadastrar o emitente.")
        payload = {
            "cpf_cnpj": config.cnpj,
            "nome_razao_social": config.razao_social,
            "email": config.email or "",
            "inscricao_municipal": config.inscricao_municipal,
            "endereco": {
                "logradouro": config.logradouro or "",
                "numero": config.numero or "",
                "complemento": config.complemento or "",
                "bairro": config.bairro or "",
                "codigo_municipio": config.codigo_municipio_ibge,
                "cidade": config.cidade or "",
                "uf": (config.uf or "").upper(),
                "cep": config.cep or "",
            },
        }
        r = self._req("POST", "/empresas", json=payload)
        if r.status_code in (200, 201, 409):     # 409 = já cadastrada -> ok
            return config.cnpj
        raise GatewayError(
            f"Não foi possível cadastrar o emitente: {self._erro_msg(r)}")
