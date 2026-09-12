"""
RED: tradefolio.drawdowns.drawdown_corrente/tempo_recuperacao_mediano ainda
não existem (AGENTS.md épico 4.3 "drawdown corrente", "tempo de
recuperação").

drawdown_corrente é o ÚLTIMO valor da série de drawdown -- distinto do
Maximum Drawdown (o mínimo histórico). Na mini fixture os dois coincidem
(a amostra termina no fundo do único episódio, ainda não recuperado), por
isso o valor de regressão contra romanos_orders.csv é o que prova que são
métricas diferentes (-48.5 vs. -1441.5 de Maximum Drawdown, já coberto em
test_drawdowns.py).

tempo_recuperacao_mediano é a mediana de `duracao_total_pregoes` só entre
episódios RECUPERADOS (duração de um episódio não recuperado é
indefinida, não deve contaminar a mediana com NaN nem ser tratada como
zero). Valores conferidos por script contra tests/fixtures/romanos_orders.csv
antes deste teste (32 episódios, 31 recuperados, mediana 4.0 pregões).
"""
import math
from pathlib import Path

import pandas as pd
import pytest

from tradefolio.drawdowns import curva_equity, drawdown, drawdown_corrente, tempo_recuperacao_mediano

SERIE_MINI = pd.Series(
    [99.50, -26.00, -150.50, 0.00, -0.50],
    index=pd.DatetimeIndex(
        ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08"]
    ),
)


def _parse_valor_br(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip().replace({"-": None})
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def _serie_diaria_romanos() -> pd.Series:
    import warnings

    from tradefolio.alignment import preencher_calendario_b3
    from tradefolio.daily import agregar_diario
    from tradefolio.loaders import carregar_ordens

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ordens = carregar_ordens(Path(__file__).parent / "fixtures" / "romanos_orders.csv")
    diario = preencher_calendario_b3(agregar_diario(ordens))
    return diario["liquido_por_contrato"]


def test_drawdown_corrente_mini_fixture():
    dd = drawdown(curva_equity(SERIE_MINI))
    assert drawdown_corrente(dd) == pytest.approx(-177.00)


def test_drawdown_corrente_e_diferente_do_maximo_historico_em_romanos():
    equity = curva_equity(_serie_diaria_romanos())
    dd = drawdown(equity)
    assert drawdown_corrente(dd) == pytest.approx(-48.5)
    assert dd.min() == pytest.approx(-1441.50)  # Maximum Drawdown, ja coberto em test_drawdowns.py


def test_tempo_recuperacao_mediano_mini_fixture_sem_episodio_recuperado_e_nan():
    equity = curva_equity(SERIE_MINI)
    assert math.isnan(tempo_recuperacao_mediano(equity))


def test_tempo_recuperacao_mediano_romanos():
    equity = curva_equity(_serie_diaria_romanos())
    assert tempo_recuperacao_mediano(equity) == pytest.approx(4.0)
