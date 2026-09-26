"""Trade reconstruction from net position changes.

Convention (CLAUDE.md > "Trade reconstruction", AGENTS.md §9): a trade is
the span from when net position leaves zero to when it returns to zero, not
a single order row or a single "saída" row — a "saída" can be split across
multiple partial fills, so counting raw rows overstates trade count.

Non-executed orders (Status != "executada") are skipped entirely (AGENTS.md
épico 1, tarefa 1.1): a cancelled/expired row has Quantidade executada == 0
and doesn't move the position, but if it arrives while position is already
0 it would otherwise open AND immediately close a phantom zero-length
trade in the same iteration (position stays 0 before and after a 0-qty
row) -- skipping it avoids fabricating a trade that never happened.

Multi-instrument robots (found while grounding a LinkedIn post about this
module, not from a task list -- AGENTS.md §8: document the correction
instead of hiding it): net position is tracked PER INSTRUMENT ROOT
(`validation.extrair_raiz_ativo`, the same grouping
`daily.agregar_diario_por_ativo` already uses), not across the whole
`ordens` argument. Two unrelated instruments (ex. WIN and WDO) can both be
"open" at once without either one closing the other's trade -- tracking a
single combined position merges these into fewer, coarser trades (verified
against `dados_exemplo/orders_roboraiz.csv`: 900 combined vs. 1,592 when
reconstructed per instrument). `report_data.calcular_pagina2` (Profit
Factor, win rate, streaks) was silently wrong for any multi-instrument
robot until this fix -- see `tests/test_trades_multi_ativo.py`.
"""
import pandas as pd

from tradefolio.costs import CUSTO_POR_PERNA_PADRAO, custo_b3
from tradefolio.validation import STATUS_EXECUTADA, extrair_raiz_ativo


def _reconstruir_trades_de_um_ativo(ordens: pd.DataFrame) -> list:
    posicao = 0
    trades = []
    atual = None

    for _, ordem in ordens.iterrows():
        if ordem["Status"] != STATUS_EXECUTADA:
            continue
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

    return trades


def reconstruir_trades(ordens: pd.DataFrame, custo_por_perna: float = CUSTO_POR_PERNA_PADRAO) -> pd.DataFrame:
    trades = []
    for _, ordens_do_ativo in ordens.groupby(ordens["Ativo"].map(extrair_raiz_ativo)):
        trades.extend(_reconstruir_trades_de_um_ativo(ordens_do_ativo))
    trades.sort(key=lambda t: t["inicio"])

    trades_df = pd.DataFrame(trades)
    trades_df["custo"] = custo_b3(trades_df["qtd_negociada"], custo_por_perna)
    trades_df["resultado_liquido"] = trades_df["resultado_bruto"] - trades_df["custo"]
    return trades_df
