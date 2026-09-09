"""
RED: tradefolio.drawdowns ainda não existe.

Grupo A -- valores exatos de tests/fixtures/mini_fixture_expected.md
(equity, drawdown R$, Maximum Drawdown, Time Under Water, Ulcer Index R$
já vêm calculados à mão no próprio fixture) mais drawdown%/Ulcer% dessa
mesma série, calculados de forma independente por script antes deste
teste (ver histórico da sessão) usando a convenção abaixo.

Convenção de capital de referência (resolve a ambiguidade que
tests/fixtures/romanos_expected.md deixava em aberto -- "R$1.000/contrato
... R$2.000,00 de saldo inicial para 2 contratos"): confirmado por
cross-check nesta sessão contra o CSV real (tests/fixtures/romanos_orders.csv)
que o cálculo que reproduz o 35,36% documentado usa **R$1.000 fixo**
somado à equity JÁ por contrato -- não R$1.000 x número de contratos.
patrimonio = capital_por_contrato (padrão 1000.0) + equity_por_contrato.

Grupo B -- regressão contra o robô real (tests/fixtures/romanos_orders.csv),
valores documentados em romanos_expected.md como conferidos contra o
relatório nativo da Smarttbot (custo, drawdown% exato) ou reproduzíveis e
estáveis (demais): Maximum Drawdown R$, Time Under Water máximo, Maximum
Drawdown %, e os dois episódios de drawdown citados por nome (maior
profundidade e maior TUW são episódios DIFERENTES nesse robô -- um bom
teste de que a ordenação de cada ranking está correta).
"""
from pathlib import Path

import pandas as pd
import pytest

from tradefolio.drawdowns import (
    curva_equity,
    drawdown,
    drawdown_pct,
    episodios_drawdown,
    maximo_drawdown,
    maximo_drawdown_pct,
    patrimonio,
    piores_time_under_water,
    time_under_water_max,
    ulcer_index,
    ulcer_index_pct,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _parse_valor_br(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip().replace({"-": None})
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def _carregar_ordens(caminho: Path) -> pd.DataFrame:
    df = pd.read_csv(caminho, sep=";", quotechar='"', encoding="utf-8")
    df["dt"] = pd.to_datetime(df["Data/Hora"], format="%d/%m/%Y / %H:%M:%S")
    df["data"] = df["dt"].dt.normalize()
    df["Resultado (R$)"] = _parse_valor_br(df["Resultado (R$)"])
    df["Quantidade executada"] = pd.to_numeric(df["Quantidade executada"], errors="coerce")
    return df.sort_values("dt").reset_index(drop=True)


def _serie_diaria(caminho: Path) -> pd.Series:
    from tradefolio.alignment import preencher_calendario_b3
    from tradefolio.daily import agregar_diario

    diario = agregar_diario(_carregar_ordens(caminho))
    diario = preencher_calendario_b3(diario)
    return diario["liquido_por_contrato"]


# ---------------------------------------------------------------------------
# Grupo A: mini fixture, valores exatos
# ---------------------------------------------------------------------------

SERIE_MINI = pd.Series(
    [99.50, -26.00, -150.50, 0.00, -0.50],
    index=pd.DatetimeIndex(
        ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08"]
    ),
)


def test_curva_equity_mini_fixture():
    esperado = pd.Series(
        [99.50, 73.50, -77.00, -77.00, -77.50], index=SERIE_MINI.index
    )
    pd.testing.assert_series_equal(curva_equity(SERIE_MINI), esperado, check_names=False)


def test_drawdown_mini_fixture():
    equity = curva_equity(SERIE_MINI)
    esperado = pd.Series(
        [0.0, -26.00, -176.50, -176.50, -177.00], index=SERIE_MINI.index
    )
    pd.testing.assert_series_equal(drawdown(equity), esperado, check_names=False)


def test_maximo_drawdown_mini_fixture():
    dd = drawdown(curva_equity(SERIE_MINI))
    assert maximo_drawdown(dd) == pytest.approx(-177.00)


def test_time_under_water_max_mini_fixture():
    dd = drawdown(curva_equity(SERIE_MINI))
    # 03/01 a 08/01, ainda nao recuperado no fim da fixture: 4 pregoes
    assert time_under_water_max(dd) == 4


def test_ulcer_index_mini_fixture():
    dd = drawdown(curva_equity(SERIE_MINI))
    assert ulcer_index(dd) == pytest.approx(137.338633, abs=1e-6)


def test_drawdown_pct_e_ulcer_pct_mini_fixture():
    # calculados por script independente (ver docstring do modulo) usando
    # capital_por_contrato=1000.0 fixo somado a equity por contrato.
    equity = curva_equity(SERIE_MINI)
    pat = patrimonio(equity)
    dd_pct = drawdown_pct(pat)
    assert maximo_drawdown_pct(dd_pct) == pytest.approx(-16.098226, abs=1e-6)
    assert ulcer_index_pct(dd_pct) == pytest.approx(12.491008, abs=1e-6)


def test_episodio_unico_mini_fixture():
    # unico episodio: pico 02/01 (99.50), fundo 08/01 (-77.50), nao
    # recuperado ate o fim da amostra.
    equity = curva_equity(SERIE_MINI)
    episodios = episodios_drawdown(equity, top_n=10)
    assert len(episodios) == 1
    ep = episodios.iloc[0]
    assert ep["inicio_pico"] == pd.Timestamp("2025-01-02")
    assert ep["data_fundo"] == pd.Timestamp("2025-01-08")
    assert ep["profundidade_rs"] == pytest.approx(-177.00)
    assert ep["recuperado"] == False
    assert pd.isna(ep["data_recuperacao"])
    assert ep["pregoes_submerso"] == 4


def test_piores_tuw_mini_fixture_mesmo_episodio_unico():
    equity = curva_equity(SERIE_MINI)
    piores = piores_time_under_water(equity, top_n=10)
    assert len(piores) == 1
    assert piores.iloc[0]["pregoes_submerso"] == 4


# ---------------------------------------------------------------------------
# Grupo B: regressao contra o robo real (romanos_expected.md)
# ---------------------------------------------------------------------------


def test_regressao_maximo_drawdown_romanos():
    serie = _serie_diaria(FIXTURES / "romanos_orders.csv")
    dd = drawdown(curva_equity(serie))
    assert maximo_drawdown(dd) == pytest.approx(-1441.50)


def test_regressao_time_under_water_romanos():
    serie = _serie_diaria(FIXTURES / "romanos_orders.csv")
    dd = drawdown(curva_equity(serie))
    assert time_under_water_max(dd) == 52


def test_regressao_maximo_drawdown_pct_romanos_bate_com_smarttbot():
    # romanos_expected.md: 35,36% exato contra o relatorio nativo da Smarttbot
    serie = _serie_diaria(FIXTURES / "romanos_orders.csv")
    equity = curva_equity(serie)
    dd_pct = drawdown_pct(patrimonio(equity))
    assert maximo_drawdown_pct(dd_pct) == pytest.approx(-35.36, abs=0.01)


def test_regressao_maior_episodio_por_profundidade():
    # romanos_expected.md: "-R$1.441,50 (pico 02/07/2026 -> fundo 21/07/2026 -> recuperado 30/07/2026)"
    serie = _serie_diaria(FIXTURES / "romanos_orders.csv")
    equity = curva_equity(serie)
    maior = episodios_drawdown(equity, top_n=1).iloc[0]
    assert maior["profundidade_rs"] == pytest.approx(-1441.50)
    assert maior["inicio_pico"] == pd.Timestamp("2026-07-02")
    assert maior["data_fundo"] == pd.Timestamp("2026-07-21")
    assert maior["data_recuperacao"] == pd.Timestamp("2026-07-30")
    assert maior["recuperado"] == True


def test_regressao_pior_tuw_e_episodio_diferente_do_maior_drawdown():
    # romanos_expected.md: "52 pregoes (episodio 08/09/2025 -> 21/11/2025)"
    # -- episodio diferente do de maior profundidade, confirma que os dois
    # rankings (por profundidade vs. por tempo submerso) ordenam por
    # criterios distintos.
    serie = _serie_diaria(FIXTURES / "romanos_orders.csv")
    equity = curva_equity(serie)
    pior_tuw = piores_time_under_water(equity, top_n=1).iloc[0]
    assert pior_tuw["pregoes_submerso"] == 52
    assert pior_tuw["inicio_pico"] == pd.Timestamp("2025-09-08")
    assert pior_tuw["data_recuperacao"] == pd.Timestamp("2025-11-21")
