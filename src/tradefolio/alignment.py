"""B3 trading-calendar alignment.

Convention (CLAUDE.md > "Trading calendar", AGENTS.md §10/§14/§15): reindex
the daily series onto the B3 trading sessions between the first and last
date present in the data (never extending into the future), filling missing
sessions with 0 and flagging them so "no trade that day" stays distinguishable
from "no data for that day".
"""
import pandas as pd
import pandas_market_calendars as mcal


def preencher_calendario_b3(diario: pd.DataFrame) -> pd.DataFrame:
    calendario = mcal.get_calendar("B3")
    inicio, fim = diario.index.min(), diario.index.max()
    pregoes = calendario.schedule(start_date=inicio, end_date=fim).index

    diario = diario.reindex(pregoes, fill_value=0)
    diario.index.name = "data"
    diario["operou"] = diario["n_trades"] > 0
    return diario
