"""
RED: tradefolio.costs.custo_b3 ainda não existe.

Convenção testada (CLAUDE.md > "Domain conventions validated against the
Smarttbot platform" > Costs, e tests/fixtures/mini_fixture_expected.md):
R$0,25 por contrato, por perna. Custo aplicado sobre a quantidade executada
total (entrada + saída), não apenas sobre a saída.
"""
from tradefolio.costs import custo_b3


def test_custo_b3_quantidade_zero_e_zero():
    assert custo_b3(0) == 0.0


def test_custo_b3_uma_perna_padrao():
    # 2 contratos em uma perna, custo padrão R$0,25/contrato/perna -> R$0,50
    assert custo_b3(2) == 0.50


def test_custo_b3_trade_completo_2_contratos():
    # mini_fixture_expected.md: trade de 2 contratos (entrada + saida = 4
    # unidades executadas) custa R$1,00 no total (R$0,25 x 4).
    assert custo_b3(4) == 1.00


def test_custo_b3_aceita_custo_por_perna_customizado():
    assert custo_b3(2, custo_por_perna=0.50) == 1.00
