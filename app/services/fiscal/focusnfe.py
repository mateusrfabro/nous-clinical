"""Adaptador Focus NFe (NFS-e).

Substituto da Nuvem Fiscal (gateway será desativado em 31/07/2026). API REST
confirmada na doc oficial (doc.focusnfe.com.br, jul/2026):

- Auth: HTTP Basic — token como usuário, senha VAZIA (``auth=(token, "")``).
- Ambientes: homologacao -> https://homologacao.focusnfe.com.br
             producao    -> https://api.focusnfe.com.br  (prefixo /v2)
- Emissão ASSÍNCRONA: ``POST /v2/nfse?ref=<ref>`` (201 -> processando_autorizacao);
  status final via ``GET /v2/nfse/<ref>`` (ou webhook). A ``ref`` é gerada por NÓS
  e identifica a nota no gateway (equivale ao ``gateway_nota_id``).
- Cancelamento: ``DELETE /v2/nfse/<ref>`` (justificativa 15–255 chars).
- Empresas: ``POST /v2/empresas`` (payload FLAT, retorna ``id`` numérico).

Segredos vêm do config (env ``FOCUSNFE_TOKEN``) — nunca do código/repo. HTTP via
``requests`` (import lazy, como no resto do projeto).
"""
import logging
import uuid

from flask import current_app

from .base import GatewayNFSe, GatewayError, ResultadoEmissao

logger = logging.getLogger(__name__)

_BASE_URLS = {
    "homologacao": "https://homologacao.focusnfe.com.br",
    "producao": "https://api.focusnfe.com.br",
}

# Status Focus -> status normalizado do módulo (ResultadoEmissao/NotaFiscal).
_STATUS_MAP = {
    "processando_autorizacao": "enviando",
    "autorizado": "autorizada",
    "erro_autorizacao": "rejeitada",
    "cancelado": "cancelada",
}

# Regime do nosso domínio -> código Focus (1=Simples Nacional, 3=Regime Normal).
_REGIME_MAP = {"simples": 1, "presumido": 3, "real": 3}


class FocusNFeGateway(GatewayNFSe):
    nome = "focusnfe"

    def _cfg(self):
        c = current_app.config
        token = c.get("FOCUSNFE_TOKEN")
        amb = (c.get("FOCUSNFE_AMBIENTE") or "homologacao").lower()
        if not token:
            raise GatewayError(
                "Credenciais da Focus NFe não configuradas "
                "(defina FOCUSNFE_TOKEN).")
        if amb not in _BASE_URLS:
            amb = "homologacao"
        return token, amb

    def _base_url(self):
        return _BASE_URLS[self._cfg()[1]]

    def _req(self, metodo, path, **kw):
        import requests
        token, _ = self._cfg()
        try:
            # Basic Auth: token como usuário, senha vazia (doc oficial Focus).
            return requests.request(metodo, self._base_url() + path,
                                    auth=(token, ""), timeout=30, **kw)
        except requests.RequestException as exc:
            raise GatewayError("Falha de comunicação com a Focus NFe.") from exc

    def _erro_msg(self, r):
        """Mensagem amigável do corpo de erro (mesma semântica do adaptador
        Nuvem Fiscal). A Focus retorna `{codigo, mensagem}` em erros de request
        e `{erros: [{codigo, mensagem, correcao}]}` em rejeições da prefeitura."""
        try:
            d = r.json()
            if isinstance(d.get("erros"), list) and d["erros"]:
                return "; ".join(
                    e.get("mensagem") or e.get("codigo") or "?"
                    for e in d["erros"])[:400]
            return d.get("mensagem") or d.get("codigo") or str(d)[:200]
        except Exception:   # noqa: BLE001 — corpo não-JSON
            return f"HTTP {r.status_code}"

    def ping(self):
        """Valida o token listando as empresas da conta (não emite nada)."""
        r = self._req("GET", "/v2/empresas")
        if r.status_code == 200:
            return True
        if r.status_code in (401, 403):
            logger.warning("FOCUSNFE auth HTTP %s", r.status_code)
            raise GatewayError(
                "Token da Focus NFe inválido (verifique FOCUSNFE_TOKEN "
                "e o ambiente).")
        raise GatewayError(
            f"Focus NFe indisponível: {self._erro_msg(r)}")

    def cadastrar_emitente(self, config):
        """Cadastra a empresa emitente (POST /v2/empresas — token da CONTA).
        Retorna o `id` (numérico na Focus) como string -> `gateway_empresa_id`.

        Diferenças p/ Nuvem Fiscal: payload FLAT (sem objeto `endereco`) e o
        identificador é um id próprio do gateway, não o CNPJ.
        """
        if not (config.cnpj and config.razao_social
                and config.inscricao_municipal and config.codigo_municipio_ibge):
            raise GatewayError(
                "Preencha CNPJ, razão social, inscrição municipal e código IBGE "
                "do município antes de cadastrar o emitente.")
        payload = {
            "nome": config.razao_social,
            "cnpj": config.cnpj,
            "email": config.email or "",
            "inscricao_municipal": config.inscricao_municipal,
            "logradouro": config.logradouro or "",
            "numero": config.numero or "",
            "complemento": config.complemento or "",
            "bairro": config.bairro or "",
            "municipio": config.cidade or "",
            "uf": (config.uf or "").upper(),
            "cep": config.cep or "",
            "regime_tributario": _REGIME_MAP.get(config.regime_tributario, 1),
            "habilita_nfse": True,
        }
        r = self._req("POST", "/v2/empresas", json=payload)
        if r.status_code in (200, 201):
            emp_id = r.json().get("id")
            if emp_id is None:
                raise GatewayError("Focus NFe não retornou o id da empresa.")
            return str(emp_id)
        # TODO(focusnfe): idempotência — a doc confirma 422 p/ dados inválidos,
        # mas NÃO confirma o comportamento quando o CNPJ já está cadastrado
        # (a Nuvem Fiscal devolvia 409). Recadastro/atualização seria
        # PUT /v2/empresas/{id}; tratar quando formos migrar emitentes reais.
        raise GatewayError(
            f"Não foi possível cadastrar o emitente: {self._erro_msg(r)}")

    def emitir(self, config, dados):
        """Emite (assíncrono): POST /v2/nfse?ref=<ref>. A `ref` identifica a nota
        no gateway; se `dados` não trouxer uma, geramos uuid4. `dados` esperado:
        `{ref?, tomador{cpf, nome, email?}, servico{discriminacao, valor_servicos,
        aliquota?, item_lista_servico?, iss_retido?}}` — prestador sai do `config`.
        Retorna status `enviando`; o resultado final vem de `consultar()`."""
        ref = (dados.get("ref") or uuid.uuid4().hex)
        tomador = dados.get("tomador") or {}
        servico = dados.get("servico") or {}
        payload = {
            "prestador": {
                "cnpj": config.cnpj,
                "inscricao_municipal": config.inscricao_municipal,
                "codigo_municipio": config.codigo_municipio_ibge,
            },
            "tomador": {
                "cpf": tomador.get("cpf"),
                "razao_social": tomador.get("nome"),
                "email": tomador.get("email") or "",
            },
            "servico": {
                # Descrição GENÉRICA (sigilo profissional/LGPD) — o chamador
                # nunca manda diagnóstico/procedimento aqui.
                "discriminacao": servico.get("discriminacao"),
                # Dinheiro é Decimal no domínio; float aqui é só serialização
                # JSON na borda HTTP (a Focus espera número).
                "valor_servicos": float(servico["valor_servicos"]),
                "aliquota": (float(servico["aliquota"])
                             if servico.get("aliquota") is not None else None),
                "iss_retido": bool(servico.get("iss_retido", False)),
                "item_lista_servico": (servico.get("item_lista_servico")
                                       or config.codigo_servico),
                "codigo_municipio": config.codigo_municipio_ibge,
            },
        }
        r = self._req("POST", f"/v2/nfse?ref={ref}", json=payload)
        # Doc: 201 na pré-validação; aceitamos 202 por robustez (assíncrono).
        if r.status_code in (200, 201, 202):
            return ResultadoEmissao(status="enviando", gateway_nota_id=ref)
        raise GatewayError(f"Emissão recusada pela Focus NFe: {self._erro_msg(r)}")

    def consultar(self, config, gateway_nota_id):
        """GET /v2/nfse/<ref> — traduz o status Focus pro normalizado e extrai
        número/verificação/links quando autorizada."""
        r = self._req("GET", f"/v2/nfse/{gateway_nota_id}")
        if r.status_code == 404:
            raise GatewayError("Nota não encontrada na Focus NFe.")
        if r.status_code != 200:
            raise GatewayError(f"Falha ao consultar a nota: {self._erro_msg(r)}")
        d = r.json()
        status = _STATUS_MAP.get(d.get("status"), "erro")
        erro = None
        if d.get("status") == "erro_autorizacao":
            erros = d.get("erros") or []
            erro = "; ".join(
                e.get("mensagem") or e.get("codigo") or "?" for e in erros)[:400] \
                or "Nota rejeitada pela prefeitura."
        return ResultadoEmissao(
            status=status,
            gateway_nota_id=gateway_nota_id,
            numero=d.get("numero"),
            codigo_verificacao=d.get("codigo_verificacao"),
            # NFS-e não tem chave de acesso de NF-e; a Focus expõe URL pública
            # da nota + XML/DANFSE. chave_acesso fica None.
            link_pdf=d.get("url_danfse") or d.get("url"),
            link_xml=d.get("caminho_xml_nota_fiscal"),
            mensagem_erro=erro,
        )

    def cancelar(self, config, gateway_nota_id, motivo):
        """DELETE /v2/nfse/<ref>. Justificativa: 15–255 chars (doc oficial) —
        completamos motivos curtos pra não tomar 400 bobo."""
        just = (motivo or "Cancelamento solicitado pela clínica").strip()
        if len(just) < 15:
            just = (just + " — cancelamento solicitado pela clínica")[:255]
        r = self._req("DELETE", f"/v2/nfse/{gateway_nota_id}",
                      json={"justificativa": just[:255]})
        if r.status_code == 200:
            d = r.json()
            if d.get("status") == "cancelado":
                return ResultadoEmissao(status="cancelada",
                                        gateway_nota_id=gateway_nota_id)
            # 200 com status=erro_cancelamento (ex.: fora do prazo).
            raise GatewayError(
                f"Cancelamento recusado: {self._erro_msg(r)}")
        raise GatewayError(
            f"Não foi possível cancelar a nota: {self._erro_msg(r)}")
