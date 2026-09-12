"""Daily -> monthly consolidation (AGENTS.md épico 3.4 "consolidar
resultados mensais").

Input is a daily series already aligned to the B3 calendar
(`tradefolio.alignment.preencher_calendario_b3`), so there are no internal
gaps -- every B3 session between the data's first and last date has a row.

`trades` sums `n_trades`, the same approximate saída-row proxy documented in
`tradefolio.daily` (counts saída rows, not reconstructed trades) -- it is
not the exact count from `tradefolio.trades.reconstruir_trades`.

`melhor_dia`/`pior_dia` use `liquido_por_contrato`, the same basis
`tradefolio.report_data.calcular_pagina1` uses for the daily-level
pior_dia/melhor_dia figures.

`mes_completo` is True when the first and last B3 session of the calendar
month coincide with the first and last session present in the data for that
month. Because the input has no internal gaps, this can only be False for
the first or last month of the series (the data started or ended mid-month).

Two fields from the épico's list are deliberately not implemented here:
"distância para o limiar" and "vapo elegível" -- both depend on the limiar
and vapo modules, which don't exist yet. Adding them now would mean
inventing placeholder values (AGENTS.md §8: never invent a financial
convention silently).
"""
import warnings

import pandas as pd
import pandas_market_calendars as mcal

from tradefolio.validation import AvisoValidacao


def _primeiro_e_ultimo_pregao_do_mes(mes: pd.Period) -> tuple[pd.Timestamp, pd.Timestamp]:
    calendario = mcal.get_calendar("B3")
    pregoes = calendario.schedule(start_date=mes.start_time, end_date=mes.end_time).index
    return pregoes.min(), pregoes.max()


def agregar_mensal(diario: pd.DataFrame) -> pd.DataFrame:
    grupos = diario.groupby(diario.index.to_period("M"))

    mensal = grupos.agg(
        bruto=("bruto", "sum"),
        custo=("custo", "sum"),
        liquido=("liquido", "sum"),
        dias_operados=("operou", "sum"),
        pregoes=("operou", "size"),
        trades=("n_trades", "sum"),
        melhor_dia=("liquido_por_contrato", "max"),
        pior_dia=("liquido_por_contrato", "min"),
    )
    mensal.index.name = "mes"

    completo = []
    for mes, grupo in grupos:
        primeiro, ultimo = _primeiro_e_ultimo_pregao_do_mes(mes)
        completo.append(grupo.index.min() == primeiro and grupo.index.max() == ultimo)
    mensal["mes_completo"] = completo

    incompletos = mensal.index[~mensal["mes_completo"]]
    if len(incompletos):
        warnings.warn(
            AvisoValidacao(
                f"{len(incompletos)} mês(es) incompleto(s) na série: "
                f"{[str(m) for m in incompletos]} -- processando mesmo assim",
                codigo="INCOMPLETE_MONTH",
            ),
            stacklevel=2,
        )

    return mensal
