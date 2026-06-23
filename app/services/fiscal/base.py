"""Interface do adaptador de gateway de NFS-e.

NFS-e é municipal e nenhum gateway cobre 100% das cidades — por isso o módulo fala
com os provedores por trás desta interface única (`GatewayNFSe`). Trocar/somar
provedor (Nuvem Fiscal, Focus NFe, ...) ou ir direto na NFS-e Nacional no futuro
não toca o resto do código. Ver docs/11-emissao-nf.md.
"""
from dataclasses import dataclass
from typing import Optional


class GatewayError(Exception):
    """Falha de comunicação/validação no gateway. `args[0]` é mensagem amigável."""


@dataclass
class ResultadoEmissao:
    """Retorno normalizado de uma emissão/consulta, agnóstico de provedor."""
    status: str                                   # enviando|autorizada|rejeitada|erro
    gateway_nota_id: Optional[str] = None
    numero: Optional[str] = None
    codigo_verificacao: Optional[str] = None
    chave_acesso: Optional[str] = None
    link_pdf: Optional[str] = None
    link_xml: Optional[str] = None
    mensagem_erro: Optional[str] = None


class GatewayNFSe:
    """Contrato que cada provedor implementa. Métodos levantam GatewayError em falha."""
    nome = "base"

    def ping(self) -> bool:
        """Valida credenciais (autentica). True se ok, senão GatewayError."""
        raise NotImplementedError

    def cadastrar_emitente(self, config) -> str:
        """Cadastra/atualiza a empresa emitente; retorna o id dela no gateway."""
        raise NotImplementedError

    def emitir(self, config, dados) -> ResultadoEmissao:
        raise NotImplementedError

    def consultar(self, config, gateway_nota_id) -> ResultadoEmissao:
        raise NotImplementedError

    def cancelar(self, config, gateway_nota_id, motivo) -> ResultadoEmissao:
        raise NotImplementedError
