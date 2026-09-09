"""Trade reconstruction from net position changes.

Convention (CLAUDE.md > "Trade reconstruction", AGENTS.md §9): a trade is
the span from when net position leaves zero to when it returns to zero, not
a single order row or a single "saída" row — a "saída" can be split across
multiple partial fills, so counting raw rows overstates trade count.
"""
import pandas as pd

from tradefolio.costs import CUSTO_POR_PERNA_PADRAO, custo_b3


def reconstruir_trades(ordens: pd.DataFrame, custo_por_perna: float = CUSTO_POR_PERNA_PADRAO) -> pd.DataFrame:
    posicao = 0
    trades = []
    atual = None

    for _, ordem in ordens.iterrows():
        qtd = ordem["Quantidade executada"]
        sinal = 1 if ordem["C/V"] == "C" else -1
        if posicao == 0:
            atual = {
                "inicio": ordem["dt"],
                "direcao": "compra" if sinal > 0 else "venda",
                "resultado_bruto": 0.0,
                "qtd_negociada": 0,
            }
        posicao += sinal * qtd
        atual["qtd_negociada"] += qtd
        if ordem["Tipo"] == "saída" and not pd.isna(ordem["Resultado (R$)"]):
            atual["resultado_bruto"] += ordem["Resultado (R$)"]
        if posicao == 0:
            atual["fim"] = ordem["dt"]
            trades.append(atual)

    trades_df = pd.DataFrame(trades)
    trades_df["custo"] = custo_b3(trades_df["qtd_negociada"], custo_por_perna)
    trades_df["resultado_liquido"] = trades_df["resultado_bruto"] - trades_df["custo"]
    return trades_df
