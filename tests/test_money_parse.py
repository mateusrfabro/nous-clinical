"""Regressão dos parsers de dinheiro: ponto de milhar BR sem vírgula NÃO pode
virar centavo (1.234 = R$ 1.234, não R$ 1,23). Achados #3/#4 da auditoria."""
from decimal import Decimal


def test_dec_caixa_milhar_sem_virgula():
    from app.routes.financeiro import _dec
    assert _dec("1.234") == Decimal("1234.00")     # milhar, não 1,23
    assert _dec("1.500") == Decimal("1500.00")
    assert _dec("1234,56") == Decimal("1234.56")   # decimal BR
    assert _dec("1.234,56") == Decimal("1234.56")  # milhar + decimal BR
    assert _dec("1234.56") == Decimal("1234.56")   # decimal com ponto (teclado)
    assert _dec("") == Decimal("0.00")
    assert _dec("0") == Decimal("0.00")


def test_parse_valor_milhar_sem_virgula():
    from app.routes.financeiro import _parse_valor
    assert _parse_valor("1.234") == Decimal("1234.00")
    assert _parse_valor("R$ 1.500") == Decimal("1500.00")
    assert _parse_valor("1.234,56") == Decimal("1234.56")
    assert _parse_valor("199,90") == Decimal("199.90")
    assert _parse_valor("0") is None     # ≤0 rejeitado no lançamento


def test_num_br_extrato_milhar_sem_virgula():
    from app.services.extrato import _num_br
    assert _num_br("1.500") == Decimal("1500")     # crédito de R$ 1.500, não 1,50
    assert _num_br("1234.56") == Decimal("1234.56")
    assert _num_br("1.234,56") == Decimal("1234.56")
    assert _num_br("(50,00)") == Decimal("-50.00")  # parêntese = débito
