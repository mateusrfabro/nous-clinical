"""Pacote fiscal — emissão de NFS-e via gateway (adaptador agnóstico de provedor).

`get_gateway(nome)` devolve a implementação; `nf_disponivel()` diz se o módulo está
ligado globalmente E com credenciais. Ver docs/11-emissao-nf.md.
"""
from flask import current_app

from .base import GatewayError, GatewayNFSe, ResultadoEmissao
from .nuvemfiscal import NuvemFiscalGateway

__all__ = ["GatewayError", "GatewayNFSe", "ResultadoEmissao",
           "get_gateway", "nf_disponivel"]

_GATEWAYS = {
    "nuvemfiscal": NuvemFiscalGateway,
}


def get_gateway(nome=None):
    """Instância do gateway pelo nome (default: nuvemfiscal). GatewayError se inválido."""
    nome = (nome or "nuvemfiscal").lower()
    cls = _GATEWAYS.get(nome)
    if not cls:
        raise GatewayError(f"Gateway fiscal desconhecido: {nome}")
    return cls()


def nf_disponivel():
    """Módulo de NF ligado globalmente E com credenciais do gateway configuradas."""
    c = current_app.config
    return bool(c.get("NF_ATIVO")
                and c.get("NUVEMFISCAL_CLIENT_ID")
                and c.get("NUVEMFISCAL_CLIENT_SECRET"))
