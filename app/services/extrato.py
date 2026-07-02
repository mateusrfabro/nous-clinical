"""Dispatcher de extrato bancário: OFX (services/ofx) ou CSV genérico.

OFX é o caminho preferido (estruturado). CSV varia por banco, então o parser
abaixo é TOLERANTE: detecta o delimitador, acha a linha de cabeçalho pelas
palavras-chave das colunas (data / valor / histórico) e ignora preâmbulo. Como
CSV raramente traz um id de transação, sintetizamos um `fitid` por hash de
(data, valor, descrição) — permitindo o mesmo dedup de reimportação do OFX.
"""
import csv
import hashlib
import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from app.services.ofx import (
    parse_ofx, OFXError, ExtratoOFX, TransacaoOFX, _decodifica,
)

_COLS_DATA = ("data", "date", "dt ")
_COLS_VALOR = ("valor", "value", "amount", "montante")
_COLS_DESC = ("histor", "descri", "memo", "lancamento", "lançamento",
              "detalhe", "transa")
_COLS_CRED = ("credito", "crédito", "entrada")
_COLS_DEB = ("debito", "débito", "saida", "saída")


def parse_extrato(filename, conteudo):
    """Faz o parse pelo tipo do arquivo. .csv -> CSV; resto -> OFX."""
    if (filename or "").lower().endswith(".csv"):
        return parse_csv(conteudo)
    return parse_ofx(conteudo)


def _norm(s):
    # Remove acentos p/ casar cabeçalho "Histórico"/"Crédito"/"Débito" com as
    # chaves sem acento (senão a coluna não é detectada).
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s.strip().lower())


def _match(cols_norm, chaves):
    """Índice da 1ª coluna cujo nome contém alguma das chaves. None se nenhuma."""
    for i, nome in enumerate(cols_norm):
        if any(k in nome for k in chaves):
            return i
    return None


def _data_br(valor):
    """'dd/mm/aaaa' ou 'aaaa-mm-dd' (com hora opcional) -> date. None se inválida."""
    s = (valor or "").strip()
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        d, mth, y = (int(x) for x in m.groups())
    else:
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
        if not m:
            return None
        y, mth, d = (int(x) for x in m.groups())
    try:
        return date(y, mth, d)
    except ValueError:
        return None


def _num_br(valor):
    """'1.234,56' / '1234.56' / '-50,00' / 'R$ 12,00' / '(50,00)' -> Decimal.
    Parênteses = negativo (formato contábil de débito). None se vazio/inválido."""
    bruto = (valor or "").strip()
    # Débito em formato contábil: (50,00) ou trailing 'D'.
    neg = (bruto.startswith("(") and bruto.endswith(")")) \
        or bool(re.search(r"\bD$", bruto))
    s = re.sub(r"[^\d,.\-]", "", bruto)
    if not s:
        return None
    # Se tem vírgula, ela é o decimal (formato BR) e ponto é milhar.
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") >= 1 and len(s.rsplit(".", 1)[1]) == 3:
        # Ponto + 3 dígitos no fim, sem vírgula = milhar (1.500 = 1500), não
        # decimal — senão um crédito de R$ 1.500 entraria como R$ 1,50.
        s = s.replace(".", "")
    try:
        v = Decimal(s)
    except InvalidOperation:
        return None
    if not v.is_finite():          # NaN/Infinity: ilegível (evita 500 no quantize)
        return None
    return -abs(v) if neg else v


def parse_csv(conteudo):
    texto = _decodifica(conteudo)
    delim = ";" if texto.count(";") >= texto.count(",") else ","
    linhas = [ln for ln in texto.splitlines() if ln.strip()]
    rows = list(csv.reader(linhas, delimiter=delim))

    cols = None
    inicio = 0
    for i, r in enumerate(rows):
        low = [_norm(c) for c in r]
        di = _match(low, _COLS_DATA)
        vi = _match(low, _COLS_VALOR)
        ci = _match(low, _COLS_CRED)
        if di is not None and (vi is not None or ci is not None):
            cols = {"data": di, "valor": vi, "desc": _match(low, _COLS_DESC),
                    "cred": ci, "deb": _match(low, _COLS_DEB)}
            inicio = i + 1
            break
    if cols is None:
        raise OFXError("CSV sem colunas reconhecíveis (precisa de data e valor).")

    ext = ExtratoOFX()
    for r in rows[inicio:]:
        if cols["data"] >= len(r):
            continue
        d = _data_br(r[cols["data"]])
        if d is None:
            continue
        valor = None
        if cols["valor"] is not None and cols["valor"] < len(r):
            valor = _num_br(r[cols["valor"]])
        if valor is None and cols["cred"] is not None:
            c = _num_br(r[cols["cred"]]) or Decimal("0")
            dv = (_num_br(r[cols["deb"]]) if cols["deb"] is not None
                  and cols["deb"] < len(r) else None) or Decimal("0")
            valor = c - dv
        if valor is None:
            continue
        desc = (r[cols["desc"]].strip() if cols["desc"] is not None
                and cols["desc"] < len(r) else "")
        fit = hashlib.sha1(
            f"{d.isoformat()}|{valor}|{desc}".encode(),
            usedforsecurity=False).hexdigest()[:16]
        ext.transacoes.append(TransacaoOFX(
            data=d, valor=abs(valor).quantize(Decimal("0.01")),
            tipo="credito" if valor >= 0 else "debito",
            descricao=desc[:200], fitid="csv" + fit))

    if not ext.transacoes:
        raise OFXError("Nenhuma transação reconhecida no CSV.")
    return ext
