"""
RED: percentil, var_historico, expected_shortfall, skewness e
kurtosis_excedente ainda não existem em tradefolio.metrics.

Convenções (AGENTS.md §8.10 exige documentar quantile/sinal antes de
implementar):
- percentil usa interpolação linear (padrão do pandas/numpy).
- VaR histórico a `confianca` = quantile(1 - confianca) da série (ex.:
  confianca=0.95 -> percentil 5, o pior extremo à esquerda).
- VaR e Expected Shortfall retornam o valor bruto com sinal (perda como
  número negativo, ex. -125,60 = perda de R$125,60), não magnitude
  positiva.
- Expected Shortfall = média dos valores <= VaR naquela confiança.
- skewness/kurtosis usam o estimador amostral ajustado (Fisher-Pearson,
  igual pandas .skew()/.kurt(), kurtosis em excesso: normal = 0).

Valores esperados calculados à mão (aritmética pura em Python, sem chamar
as funções sob teste) sobre a série diária por contrato da
tests/fixtures/mini_fixture_expected.md, já alinhada no calendário B3:
[99.50, -26.00, -150.50, 0.00, -0.50]. A fórmula ajustada de
skewness/kurtosis foi verificada de forma independente (ver conversa) e
bate com a saída do pandas até a precisão de ponto flutuante -- não é
"o que o pandas retornar", é a definição estatística padrão.
"""
import pandas as pd
import pytest

from tradefolio.metrics import (
    expected_shortfall,
    kurtosis_excedente,
    percentil,
    skewness,
    var_historico,
)

SERIE = pd.Series([99.50, -26.00, -150.50, 0.00, -0.50])


@pytest.mark.parametrize(
    "p,esperado",
    [
        (1, -145.52),
        (5, -125.60),
        (10, -100.70),
        (25, -26.00),
        (50, -0.50),
        (75, 0.00),
        (90, 59.70),
        (95, 79.60),
        (99, 95.52),
    ],
)
def test_percentil(p, esperado):
    assert percentil(SERIE, p) == pytest.approx(esperado, abs=1e-6)


def test_var_historico_95_e_99():
    assert var_historico(SERIE, confianca=0.95) == pytest.approx(-125.60, abs=1e-6)
    assert var_historico(SERIE, confianca=0.99) == pytest.approx(-145.52, abs=1e-6)


def test_var_historico_retorna_valor_com_sinal_nao_magnitude():
    # perda deve vir negativa, nao como magnitude positiva
    assert var_historico(SERIE, confianca=0.95) < 0


def test_expected_shortfall_95_e_99():
    # so -150.50 fica <= VaR95(-125.60) e <= VaR99(-145.52) nesta amostra
    assert expected_shortfall(SERIE, confianca=0.95) == pytest.approx(-150.50, abs=1e-6)
    assert expected_shortfall(SERIE, confianca=0.99) == pytest.approx(-150.50, abs=1e-6)


def test_skewness():
    assert skewness(SERIE) == pytest.approx(-0.5429708576351356, rel=1e-9)


def test_kurtosis_excedente():
    assert kurtosis_excedente(SERIE) == pytest.approx(1.8899298886667832, rel=1e-9)
