"""B3 trading-calendar alignment.

Convention (CLAUDE.md > "Trading calendar", AGENTS.md §10/§14/§15): reindex
the daily series onto the B3 trading sessions between the first and last
date present in the data (never extending into the future), filling missing
sessions with 0 and flagging them so "no trade that day" stays distinguishable
from "no data for that day".

`resultado_zero` distinguishes two of the "three types of zero" (AGENTS.md
§10, épico 3.3 da lâmina): a day with `operou=False` is NO_TRADE (no order
rows that session); a day with `operou=True` and `resultado_zero=True` is
ZERO_RESULT (traded, gross result landed exactly on zero). The basis is
`bruto` (gross), not `liquido` (net) -- exchange costs are a deterministic
function of executed quantity, orthogonal to whether the trading outcome
itself was flat, so classifying on net would mark a day "not zero" purely
because of the per-leg fee. A third category, MISSING_DATA (day present in
the B3 calendar but the underlying data itself is absent, as opposed to the
robot legitimately not trading), is deliberately NOT implemented here: a
single robot's order CSV has no field that distinguishes "robot chose not to
trade" from "data gap in the export" (AGENTS.md §24 -- missing data that
cannot be distinguished from zero activity is a stop condition, not a guess
to make). Revisit once there is an independent signal for it (e.g. a
portfolio-level robot-existence window, épico 10).
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
    diario["resultado_zero"] = diario["operou"] & (diario["bruto"] == 0)
    return diario
