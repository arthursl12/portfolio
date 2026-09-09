"""Equity curve, drawdown, Ulcer Index and drawdown-episode reconstruction.

Reference-capital convention (AGENTS.md §8.6/§8.9, resolved by cross-check
against tests/fixtures/romanos_orders.csv in this session): patrimonio =
capital_por_contrato (fixed, default R$1,000) + equity_por_contrato. The
capital is NOT multiplied by the number of contracts -- it's added directly
to the already-per-contract equity series. This is the convention that
reproduces the 35.36% Maximum Drawdown % documented in
tests/fixtures/romanos_expected.md as matching the Smarttbot platform
exactly.

Percentage metrics (maximo_drawdown_pct, ulcer_index_pct) are returned in
percentage points (e.g. -35.36, not -0.3536), matching the fixture's own
convention.
"""
import numpy as np
import pandas as pd

CAPITAL_POR_CONTRATO_PADRAO = 1000.0


def curva_equity(serie: pd.Series) -> pd.Series:
    return serie.cumsum()


def drawdown(equity: pd.Series) -> pd.Series:
    return equity - equity.cummax()


def maximo_drawdown(drawdown_serie: pd.Series) -> float:
    return drawdown_serie.min()


def time_under_water_max(drawdown_serie: pd.Series) -> int:
    submerso = (drawdown_serie < 0).astype(int)
    if not submerso.any():
        return 0
    grupos = (submerso != submerso.shift()).cumsum()
    return int(submerso.groupby(grupos).sum().max())


def ulcer_index(drawdown_serie: pd.Series) -> float:
    return (drawdown_serie**2).mean() ** 0.5


def patrimonio(equity: pd.Series, capital_por_contrato: float = CAPITAL_POR_CONTRATO_PADRAO) -> pd.Series:
    return capital_por_contrato + equity


def drawdown_pct(patrimonio_serie: pd.Series) -> pd.Series:
    pico = patrimonio_serie.cummax()
    return (patrimonio_serie - pico) / pico


def maximo_drawdown_pct(drawdown_pct_serie: pd.Series) -> float:
    return drawdown_pct_serie.min() * 100


def ulcer_index_pct(drawdown_pct_serie: pd.Series) -> float:
    return (drawdown_pct_serie**2).mean() ** 0.5 * 100


def calcular_episodios_drawdown(equity: pd.Series) -> pd.DataFrame:
    """Todos os episódios de drawdown (sem cortar top_n) -- base para os rankings."""
    pico = equity.cummax()
    submerso = equity < pico

    episodios = []
    grupos = (submerso != submerso.shift()).cumsum()
    for _, idx in equity.groupby(grupos).groups.items():
        if not submerso.loc[idx[0]]:
            continue
        pos_pico = equity.index.get_loc(idx[0]) - 1
        data_pico = equity.index[pos_pico] if pos_pico >= 0 else idx[0]
        valor_pico = equity.loc[data_pico]

        trecho = equity.loc[idx]
        data_fundo = trecho.idxmin()
        valor_fundo = trecho.min()
        profundidade = valor_fundo - valor_pico

        pos_fim_episodio = equity.index.get_loc(idx[-1])
        recuperado = pos_fim_episodio + 1 < len(equity)
        data_recuperacao = equity.index[pos_fim_episodio + 1] if recuperado else pd.NaT
        duracao_total = (pos_fim_episodio + 1 - pos_pico) if recuperado else np.nan

        episodios.append({
            "inicio_pico": data_pico,
            "data_fundo": data_fundo,
            "profundidade_rs": profundidade,
            "data_recuperacao": data_recuperacao,
            "pregoes_ate_fundo": equity.index.get_loc(data_fundo) - pos_pico,
            "pregoes_submerso": len(idx),
            "duracao_total_pregoes": duracao_total,
            "recuperado": recuperado,
        })

    return pd.DataFrame(episodios)


def episodios_drawdown(equity: pd.Series, top_n: int = 10) -> pd.DataFrame:
    """Top N episódios por profundidade (R$, mais negativo primeiro)."""
    todos = calcular_episodios_drawdown(equity)
    return todos.sort_values("profundidade_rs").head(top_n).reset_index(drop=True)


def piores_time_under_water(equity: pd.Series, top_n: int = 10) -> pd.DataFrame:
    """Top N episódios por tempo submerso (pregões), independente da profundidade."""
    todos = calcular_episodios_drawdown(equity)
    return todos.sort_values("pregoes_submerso", ascending=False).head(top_n).reset_index(drop=True)
