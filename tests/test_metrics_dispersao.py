"""
RED: tradefolio.metrics.desvio_padrao/downside_deviation ainda não existem
(AGENTS.md épico 4.3 "métricas de risco" -- ambas já eram usadas
implicitamente dentro de sharpe/sortino, mas não expostas como métricas
nomeadas próprias).

downside_deviation extrai exatamente o cálculo já usado dentro de
tradefolio.metrics.sortino (desvio-padrão amostral, ddof=1, só dos valores
negativos) -- sortino é refatorado para reusá-la em vez de duplicar.

Valores da série principal (mini fixture, já conferidos em
test_metrics_anualizados.py): desvio_padrao ≈ 89.478349, downside_deviation
≈ 80.260513.
"""
import math

import pandas as pd
import pytest

from tradefolio.metrics import desvio_padrao, downside_deviation

SERIE = pd.Series([99.50, -26.00, -150.50, 0.00, -0.50])


def test_desvio_padrao_caso_principal():
    assert desvio_padrao(SERIE) == pytest.approx(89.47834933658532, rel=1e-9)


def test_downside_deviation_caso_principal():
    assert downside_deviation(SERIE) == pytest.approx(80.26051333003048, rel=1e-9)


def test_downside_deviation_sem_perdas_e_nan():
    assert math.isnan(downside_deviation(pd.Series([1.0, 2.0, 3.0])))


def test_downside_deviation_com_um_unico_dia_negativo_e_nan():
    # desvio-padrao de amostra com 1 ponto e indefinido
    assert math.isnan(downside_deviation(pd.Series([1.0, 2.0, -3.0])))
