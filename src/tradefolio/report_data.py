"""Orchestration: composes the calculation modules into the page-1/2/3
dicts that report.py renders. Pure data assembly -- no HTML/matplotlib
here (AGENTS.md §16: keep business logic separate from presentation).
"""
import pandas as pd

from tradefolio import drawdowns, metrics
from tradefolio.alignment import preencher_calendario_b3
from tradefolio.daily import CONTRATOS_REFERENCIA_PADRAO, agregar_diario
from tradefolio.drawdowns import CAPITAL_POR_CONTRATO_PADRAO
from tradefolio.loaders import carregar_ordens
from tradefolio.trades import reconstruir_trades

PERCENTIS_PAGINA3 = (1, 5, 10, 25, 50, 75, 90, 95, 99)

JANELAS_DISPONIVEIS = (
    "1 semana", "1 mês", "3 meses", "6 meses", "1 ano", "2 anos", "desde o início",
)

_OFFSET_POR_JANELA = {
    "1 semana": pd.DateOffset(weeks=1),
    "1 mês": pd.DateOffset(months=1),
    "3 meses": pd.DateOffset(months=3),
    "6 meses": pd.DateOffset(months=6),
    "1 ano": pd.DateOffset(years=1),
    "2 anos": pd.DateOffset(years=2),
}


def filtrar_por_janela(diario: pd.DataFrame, janela: str) -> pd.DataFrame:
    """Recorta `diario` para os últimos `janela` a partir da ÚLTIMA data
    presente nos dados (não da data de hoje -- o histórico pode terminar
    no passado). "desde o início" retorna os dados sem filtrar. Um
    rótulo desconhecido levanta erro em vez de silenciosamente não
    filtrar."""
    if janela == "desde o início":
        return diario
    if janela not in _OFFSET_POR_JANELA:
        raise ValueError(
            f"janela desconhecida: {janela!r} -- use uma de {JANELAS_DISPONIVEIS}"
        )
    inicio = diario.index.max() - _OFFSET_POR_JANELA[janela]
    return diario.loc[inicio:]


def montar_dataframe_diario(csv_path) -> pd.DataFrame:
    ordens = carregar_ordens(csv_path)
    diario = agregar_diario(ordens)
    return preencher_calendario_b3(diario)


def calcular_pagina1(diario: pd.DataFrame) -> tuple[dict, pd.Series, pd.Series]:
    serie = diario["liquido_por_contrato"]

    equity = drawdowns.curva_equity(serie)
    dd = drawdowns.drawdown(equity)
    dd_pct = drawdowns.drawdown_pct(drawdowns.patrimonio(equity))
    max_dd = drawdowns.maximo_drawdown(dd)

    m = {
        "periodo": (diario.index.min().date(), diario.index.max().date()),
        "pregoes": len(diario),
        "lucro_liquido_2c": diario["liquido"].sum(),
        "lucro_liquido_por_contrato": serie.sum(),
        "media_diaria": serie.mean(),
        "mediana_diaria": serie.median(),
        "pct_dias_positivos": metrics.taxa_positivos(serie),
        "pct_dias_negativos": metrics.taxa_negativos(serie),
        "pct_dias_neutros": metrics.taxa_neutros(serie),
        "gain_medio": metrics.ganho_medio(serie),
        "loss_medio": metrics.perda_media(serie),
        "payoff": metrics.payoff(serie),
        "expectancia_diaria": metrics.expectancia(serie),
        "profit_factor_diario": metrics.profit_factor(serie),
        "pior_dia": serie.min(),
        "melhor_dia": serie.max(),
        "max_drawdown": max_dd,
        "max_drawdown_pct": drawdowns.maximo_drawdown_pct(dd_pct),
        "retorno_bruto_pct": (diario["bruto"].sum() / CONTRATOS_REFERENCIA_PADRAO)
        / CAPITAL_POR_CONTRATO_PADRAO
        * 100,
        "retorno_liquido_pct": serie.sum() / CAPITAL_POR_CONTRATO_PADRAO * 100,
        "time_under_water_max_pregoes": drawdowns.time_under_water_max(dd),
        "ulcer_index_rs": drawdowns.ulcer_index(dd),
        "ulcer_index_pct": drawdowns.ulcer_index_pct(dd_pct),
        "sharpe": metrics.sharpe(serie),
        "sortino": metrics.sortino(serie),
        "calmar": metrics.calmar(serie, max_dd),
        "recovery_factor": metrics.recovery_factor(serie, max_dd),
    }
    return m, equity, dd


def calcular_pagina2(diario: pd.DataFrame, ordens: pd.DataFrame) -> dict:
    trades = reconstruir_trades(ordens)
    resultado = trades["resultado_liquido"]

    _, equity, _ = calcular_pagina1(diario)

    return {
        "trades": trades,
        "n_trades": len(trades),
        "win_rate_trades": metrics.taxa_positivos(resultado),
        "profit_factor_trades": metrics.profit_factor(resultado),
        "lucro_medio_trade": metrics.ganho_medio(resultado),
        "prejuizo_medio_trade": metrics.perda_media(resultado),
        "maior_sequencia_positiva_trades": metrics.maior_sequencia_detalhada(
            resultado, True, trades["inicio"], trades["fim"]
        ),
        "maior_sequencia_negativa_trades": metrics.maior_sequencia_detalhada(
            resultado, False, trades["inicio"], trades["fim"]
        ),
        "maior_sequencia_positiva_dias": metrics.maior_sequencia_detalhada(
            diario["liquido_por_contrato"], True
        ),
        "maior_sequencia_negativa_dias": metrics.maior_sequencia_detalhada(
            diario["liquido_por_contrato"], False
        ),
        "episodios_drawdown": drawdowns.episodios_drawdown(equity, top_n=10),
        "piores_tuw": drawdowns.piores_time_under_water(equity, top_n=10),
    }


def calcular_pagina3(diario: pd.DataFrame) -> dict:
    serie = diario["liquido_por_contrato"]
    dias_neg = serie[serie < 0]

    percentis = {p: metrics.percentil(serie, p) for p in PERCENTIS_PAGINA3}
    piores_5 = serie.nsmallest(5)
    melhores_5 = serie.nlargest(5)

    return {
        "serie": serie,
        "media": serie.mean(),
        "mediana": serie.median(),
        "desvio_padrao": serie.std(),
        "skewness": metrics.skewness(serie),
        "kurtosis": metrics.kurtosis_excedente(serie),
        "percentis": percentis,
        "piores_5_media": piores_5.mean(),
        "piores_5": piores_5,
        "melhores_5_media": melhores_5.mean(),
        "melhores_5": melhores_5,
        "var_95": metrics.var_historico(serie, 0.95),
        "var_99": metrics.var_historico(serie, 0.99),
        "es_95": metrics.expected_shortfall(serie, 0.95),
        "es_99": metrics.expected_shortfall(serie, 0.99),
        "n_dias_negativos": len(dias_neg),
    }
