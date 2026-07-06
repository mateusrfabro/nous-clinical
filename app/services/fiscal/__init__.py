"""Pacote fiscal — emissão de NFS-e via gateway (adaptador agnóstico de provedor).

`get_gateway(nome)` devolve a implementação; `nf_disponivel()` diz se o módulo está
ligado globalmente E com credenciais. O gateway padrão vem da env `FISCAL_GATEWAY`
(`nuvemfiscal` | `focusnfe`; default nuvemfiscal — a Nuvem Fiscal será desativada
em 31/07/2026, migração p/ Focus NFe). Ver docs/11-emissao-nf.md.
"""
from flask import current_app

from .base import GatewayError, GatewayNFSe, ResultadoEmissao
from .focusnfe import FocusNFeGateway
from .nuvemfiscal import NuvemFiscalGateway

__all__ = ["GatewayError", "GatewayNFSe", "ResultadoEmissao",
           "get_gateway", "nf_disponivel"]

_GATEWAYS = {
    "nuvemfiscal": NuvemFiscalGateway,
    "focusnfe": FocusNFeGateway,
}


def _gateway_padrao():
    """Nome do gateway padrão da plataforma (env FISCAL_GATEWAY)."""
    return (current_app.config.get("FISCAL_GATEWAY") or "nuvemfiscal").lower()


def get_gateway(nome=None):
    """Instância do gateway pelo nome (default: env FISCAL_GATEWAY, que por sua
    vez default pra nuvemfiscal). GatewayError se inválido."""
    nome = (nome or _gateway_padrao()).lower()
    cls = _GATEWAYS.get(nome)
    if not cls:
        raise GatewayError(f"Gateway fiscal desconhecido: {nome}")
    return cls()


def _credenciais_ok(c):
    """Credenciais do gateway padrão presentes? (cada provedor tem as suas)."""
    if _gateway_padrao() == "focusnfe":
        return bool(c.get("FOCUSNFE_TOKEN"))
    return bool(c.get("NUVEMFISCAL_CLIENT_ID")
                and c.get("NUVEMFISCAL_CLIENT_SECRET"))


def nf_disponivel():
    """Módulo de NF ligado globalmente E com credenciais do gateway configuradas."""
    c = current_app.config
    return bool(c.get("NF_ATIVO") and _credenciais_ok(c))
