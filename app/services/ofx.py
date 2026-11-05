"""Parser de extrato OFX (Open Financial Exchange) — sem dependência externa.

Tolera os dois sabores que os bancos BR exportam:
- OFX 1.x (SGML): cabeçalho em linhas `CHAVE:VALOR`, tags-folha SEM fechamento
  (`<TRNAMT>150.00` termina na quebra de linha), agregados COM fechamento
  (`<STMTTRN>...</STMTTRN>`).
- OFX 2.x (XML): tags com fechamento (`<TRNAMT>150.00</TRNAMT>`).

A extração por regex captura o valor de uma tag até a próxima quebra de linha
OU o próximo `<` — funciona nos dois formatos. Não é um parser SGML completo,
mas cobre `STMTTRN` (que é o que precisamos pra conciliação) de forma robusta.

Uso:
    extrato = parse_ofx(file_bytes)
    extrato.banco, extrato.conta, extrato.transacoes  # lista de TransacaoOFX
"""
from __future__ import annotations

import hashlib
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


class OFXError(ValueError):
    """Arquivo OFX inválido ou ilegível."""


@dataclass
class TransacaoOFX:
    data: date
    valor: Decimal          # SEMPRE positivo; o sentido vai em `tipo`
    tipo: str               # "credito" (entrada) | "debito" (saida)
    descricao: str
    fitid: str


@dataclass
class ExtratoOFX:
    banco: str = ""
    conta: str = ""
    transacoes: list[TransacaoOFX] = field(default_factory=list)


_STMTTRN_RE = re.compile(r"<STMTTRN>(.*?)</STMTTRN>", re.S | re.I)


def _campo(bloco: str, tag: str) -> str:
    """Valor de uma tag-folha: do `>` até a quebra de linha ou o próximo `<`."""
    m = re.search(r"<" + tag + r">\s*([^\r\n<]*)", bloco, re.I)
    return m.group(1).strip() if m else ""


def _valor_ofx(bruto: str) -> Decimal | None:
    """TRNAMT -> Decimal. OFX canônico é ponto-decimal (US: "1234.56"), mas
    alguns bancos BR exportam vírgula ("1.234,56" = milhar '.' + decimal ',').
    Detecta o sabor pela presença de vírgula. Retorna None se ilegível."""
    s = (bruto or "").strip().replace(" ", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        v = Decimal(s)
    except (InvalidOperation, ValueError):
        return None
    # NaN/Infinity constroem um Decimal válido mas estouram no >=/quantize
    # depois (500). Descarta não-finitos como ilegíveis.
    return v if v.is_finite() else None


def _para_data(dtposted: str) -> date | None:
    """DTPOSTED -> date. Formato: YYYYMMDD[HHMMSS][.xxx][tz]. Usa os 8 primeiros."""
    digitos = re.sub(r"\D", "", dtposted or "")
    if len(digitos) < 8:
        return None
    try:
        return date(int(digitos[0:4]), int(digitos[4:6]), int(digitos[6:8]))
    except ValueError:
        return None


def _decodifica(conteudo: bytes | str) -> str:
    """OFX 1.x costuma ser cp1252/latin-1; 2.x é utf-8. Tenta na ordem segura."""
    if isinstance(conteudo, str):
        return conteudo
    for enc in ("utf-8", "cp1252", "latin-1"):
        try:
            return conteudo.decode(enc)
        except UnicodeDecodeError:
            continue
    return conteudo.decode("latin-1", errors="replace")


def parse_ofx(conteudo: bytes | str) -> ExtratoOFX:
    """Faz o parse de um arquivo OFX e retorna o ExtratoOFX.

    Lança OFXError se não houver nenhuma transação reconhecível (arquivo que
    não é OFX, ou extrato vazio sem STMTTRN).
    """
    texto = _decodifica(conteudo)
    if "<OFX>" not in texto.upper() and "<STMTTRN>" not in texto.upper():
        raise OFXError("Arquivo não parece ser um extrato OFX.")

    extrato = ExtratoOFX(
        banco=(_campo(texto, "ORG") or _campo(texto, "BANKID")),
        conta=_campo(texto, "ACCTID"),
    )

    vistos: Counter = Counter()
    for bloco in _STMTTRN_RE.findall(texto):
        valor = _valor_ofx(_campo(bloco, "TRNAMT"))
        if valor is None:
            # Não engolir em silêncio: um valor ilegível some da conciliação e
            # vira divergência de caixa fantasma. Loga pra rastrear.
            logger.warning("OFX_TRNAMT_ILEGIVEL bruto=%r", _campo(bloco, "TRNAMT"))
            continue
        dt = _para_data(_campo(bloco, "DTPOSTED"))
        if dt is None:
            logger.warning("OFX_DTPOSTED_ILEGIVEL")
            continue
        descricao = (_campo(bloco, "MEMO") or _campo(bloco, "NAME"))[:200]
        tipo = "credito" if valor >= 0 else "debito"
        fitid = _campo(bloco, "FITID")[:80]
        if not fitid:
            # Banco não forneceu FITID: gera chave sintética ESTÁVEL a partir do
            # conteúdo, pra reimportação do mesmo extrato deduplicar (senão cada
            # reimport recria a transação — caixa fantasma). O índice de
            # ocorrência separa transações idênticas dentro do mesmo arquivo.
            base = f"{dt.isoformat()}|{valor}|{tipo}|{descricao}"
            n = vistos[base]
            vistos[base] += 1
            h = hashlib.sha1(base.encode("utf-8"),
                             usedforsecurity=False).hexdigest()[:24]
            fitid = f"SYN:{h}:{n}"
        extrato.transacoes.append(TransacaoOFX(
            data=dt,
            valor=abs(valor).quantize(Decimal("0.01")),
            tipo=tipo,
            descricao=descricao,
            fitid=fitid,
        ))

    if not extrato.transacoes:
        raise OFXError("Nenhuma transação encontrada no extrato.")
    return extrato
