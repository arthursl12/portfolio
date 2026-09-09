"""Orders -> daily P&L series, before B3 calendar alignment.

`n_trades` counts "saída" rows per day -- an approximate proxy (matches the
original code's own `operacoes_aprox` naming), distinct from the precise
trade count in tradefolio.trades.reconstruir_trades, which groups partial
fills. The two coincide only when no trade that day has a split saída.
"""
import pandas as pd

from tradefolio.costs import CUSTO_POR_PERNA_PADRAO, custo_b3

CONTRATOS_REFERENCIA_PADRAO = 2


def agregar_diario(
    ordens: pd.DataFrame,
    custo_por_perna: float = CUSTO_POR_PERNA_PADRAO,
    contratos_referencia: int = CONTRATOS_REFERENCIA_PADRAO,
) -> pd.DataFrame:
    saidas = ordens[ordens["Tipo"] == "saída"]

    bruto_dia = saidas.groupby("data")["Resultado (R$)"].sum().rename("bruto")
    custo_dia = custo_b3(
        ordens.groupby("data")["Quantidade executada"].sum(), custo_por_perna
    ).rename("custo")
    n_trades_dia = saidas.groupby("data").size().rename("n_trades")

    diario = pd.concat([bruto_dia, custo_dia, n_trades_dia], axis=1).fillna(0)
    diario["liquido"] = diario["bruto"] - diario["custo"]
    diario["liquido_por_contrato"] = diario["liquido"] / contratos_referencia
    return diario
