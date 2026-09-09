"""
RED: sharpe, sortino, retorno_anualizado, calmar e recovery_factor ainda
não existem em tradefolio.metrics.

mini_fixture_expected.md avisa que Sharpe/Sortino/Calmar "não são hand-
verificáveis com precisão nessa amostra de 5 pontos... trate como
regressão (congele o valor produzido pela implementação de referência)".
Na prática as fórmulas são aritmética simples e determinística (mesma
lógica de sheet.py: DIAS_UTEIS_ANO=252, desvio-padrão amostral ddof=1,
n_anos = dias corridos/365.25) -- foram computadas de forma independente
em Python puro (ver histórico da sessão, inclusive conferindo o
desvio-padrão amostral por soma de quadrados, sem chamar pandas.std())
antes deste teste, então são tratadas aqui como valores hand-verificados,
não como regressão cega.

calmar/recovery_factor recebem o Maximum Drawdown como parâmetro em vez
de recalculá-lo, para não acoplar metrics.py a drawdowns.py -- quem
orquestra (report_data.py, futuramente) é responsável por passar o valor
de tradefolio.drawdowns.maximo_drawdown.
"""
import math

import pandas as pd
import pytest

from tradefolio.metrics import calmar, recovery_factor, retorno_anualizado, sharpe, sortino

SERIE = pd.Series(
    [99.50, -26.00, -150.50, 0.00, -0.50],
    index=pd.DatetimeIndex(
        ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08"]
    ),
)
MAX_DRAWDOWN_MINI_FIXTURE = -177.00  # tests/test_drawdowns.py, já confirmado


def test_sharpe_caso_principal():
    assert sharpe(SERIE) == pytest.approx(-2.7498816613551633, rel=1e-9)


def test_sortino_caso_principal():
    assert sortino(SERIE) == pytest.approx(-3.0657026938917222, rel=1e-9)


def test_retorno_anualizado_caso_principal():
    # 6 dias corridos (02/01 a 08/01) / 365.25, retorno_total=-77.50
    assert retorno_anualizado(SERIE) == pytest.approx(-4717.8125, rel=1e-9)


def test_calmar_caso_principal():
    assert calmar(SERIE, MAX_DRAWDOWN_MINI_FIXTURE) == pytest.approx(-26.65430790960452, rel=1e-9)


def test_recovery_factor_caso_principal():
    assert recovery_factor(SERIE, MAX_DRAWDOWN_MINI_FIXTURE) == pytest.approx(-0.4378531073446328, rel=1e-9)


def test_sharpe_com_desvio_padrao_zero_e_nan():
    assert math.isnan(sharpe(pd.Series([5.0, 5.0, 5.0])))


def test_sortino_sem_dias_negativos_e_nan():
    assert math.isnan(sortino(pd.Series([1.0, 2.0, 3.0])))


def test_sortino_com_um_unico_dia_negativo_e_nan():
    # desvio-padrao de amostra com 1 ponto e indefinido
    assert math.isnan(sortino(pd.Series([1.0, 2.0, -3.0])))


def test_calmar_com_max_drawdown_zero_e_nan():
    # serie sem nenhum drawdown (sempre em novo pico) -> max_drawdown=0
    assert math.isnan(calmar(SERIE, 0.0))


def test_recovery_factor_com_max_drawdown_zero_e_nan():
    assert math.isnan(recovery_factor(SERIE, 0.0))
