"""Alternative ingestion path for robots without order-level exports.

Some robots' platforms only ever report a daily P&L, no entrada/saída
detail, no contract count -- ex. TradingX
(`dados_exemplo/daily_tradingx.csv`): one row per trading session,
`Data;Mes;Pontos;Resultado_R$;Saldo_Acumulado_R$`. This is genuinely a
different format from the Smarttbot order-level shape
`tradefolio.importers`/`tradefolio.validation.COLUNAS_OBRIGATORIAS`
require -- there is no order to reconstruct a trade from, so this module
does NOT implement `importers.OrderImporter` (that interface's contract
is "produce the `ordens` DataFrame shape"; there is no such shape here).

Consequences of having no order-level detail (documented, not hidden --
AGENTS.md §8):

- Trade-level metrics (Página 2: Profit Factor by trade, win/loss
  streaks, win rate) are structurally IMPOSSIBLE -- there is no
  reconstructed trade, only an already-aggregated daily result. Never
  attempt to compute them for this format.
- `bruto`/`custo` (B3 emolumento) stay UNKNOWN in the `diario` this
  module builds -- not invented as 0 and not copied from `liquido`. 0
  already means "no cost was charged," a different fact from "we don't
  know the cost." Any downstream metric that depends on them (e.g.
  `report_data.calcular_pagina1`'s `retorno_bruto_pct`) degrades
  honestly to NaN ("—" in the UI), never a fabricated number.
- `n_trades` also stays UNKNOWN (NaN) for the same reason -- there is no
  order data to count trades from.
- Monte Carlo deterioration scenarios (`aumentar_custos`/
  `aplicar_slippage`) depend on `bruto`/`custo`/`n_trades` and must not
  be offered for this format -- callers should disable those controls,
  not attempt to run them (they would silently corrupt the trajectories
  with NaN otherwise).
- `contratos_referencia` cannot be DETECTED (no "Quantidade executada"
  column exists to detect from). User-confirmed decision (not invented):
  the reported series already represents 1 contract, so
  `CONTRATOS_REFERENCIA_RESULTADOS_DIARIOS = 1` is fixed, which lets the
  series be scaled the same linear way as any other robot
  (`daily.escalar_por_contratos`) -- an explicit choice, not a detection.

Everything else in the pipeline (drawdown/Sharpe/Sortino/threshold/RLT/
Monte Carlo/portfolio) only depends on `diario['liquido']`/
`['liquido_por_contrato']`/`['operou']`, which this module builds using
the exact same B3-calendar-alignment convention as
`alignment.preencher_calendario_b3` -- no other function needs to know a
robot came from this format instead of orders.
"""
import numpy as np
import pandas as pd
import pandas_market_calendars as mcal

from tradefolio.loaders import detectar_delimitador, ler_primeira_linha

COLUNAS_OBRIGATORIAS_RESULTADOS = ("Data", "Resultado_R$")
CONTRATOS_REFERENCIA_RESULTADOS_DIARIOS = 1


def eh_formato_resultados_diarios(csv_path) -> bool:
    """Detecção rápida (só o cabeçalho, não um parse completo) -- mesmo
    espírito de `importers.SmarttbotOrderImporter.can_parse`, para este
    formato alternativo. Um arquivo real só deveria satisfazer um dos
    dois formatos (as colunas obrigatórias não se sobrepõem)."""
    try:
        delimitador = detectar_delimitador(csv_path)
        primeira_linha = ler_primeira_linha(csv_path)
    except OSError:
        return False
    colunas = {c.strip() for c in primeira_linha.strip().split(delimitador)}
    return set(COLUNAS_OBRIGATORIAS_RESULTADOS).issubset(colunas)


def carregar_resultados_diarios(csv_path) -> pd.DataFrame:
    """Lê um CSV de resultados diários já agregados (sem detalhe de
    ordem) -- `;` delimitador, BOM UTF-8, `Data` em dd/mm/yyyy,
    `Resultado_R$` já numérico (conferido no arquivo real do TradingX --
    diferente do Smarttbot, não é uma string BR com vírgula decimal).
    Demais colunas (`Mes`, `Pontos`, `Saldo_Acumulado_R$`) são
    ignoradas -- não fazem parte do que o resto do pipeline precisa.

    Levanta `ValueError` se faltar `Resultado_R$` ou se houver datas
    duplicadas (uma linha por pregão é a premissa deste formato; mais de
    uma pro mesmo dia é dado ambíguo, não um caso a resolver
    silenciosamente)."""
    delimitador = detectar_delimitador(csv_path)
    df = pd.read_csv(csv_path, sep=delimitador, encoding="utf-8-sig")

    faltantes = set(COLUNAS_OBRIGATORIAS_RESULTADOS) - set(df.columns)
    if faltantes:
        raise ValueError(
            f"CSV de resultados diários sem coluna(s) obrigatória(s): {sorted(faltantes)}"
        )

    df["data"] = pd.to_datetime(df["Data"], format="%d/%m/%Y")
    if df["data"].duplicated().any():
        duplicadas = sorted(df.loc[df["data"].duplicated(), "Data"].unique())
        raise ValueError(
            f"data(s) duplicada(s) no CSV de resultados diários: {duplicadas}"
        )

    resultado = df.set_index("data")["Resultado_R$"].astype(float).sort_index()
    resultado.name = "liquido"
    return resultado.to_frame()


def montar_diario_resultados(resultados: pd.DataFrame) -> pd.DataFrame:
    """Constrói um `diario` no mesmo formato usado pelo resto do
    pipeline a partir de uma série de resultados diários já agregados
    (`carregar_resultados_diarios`). Alinha ao calendário B3 real: um
    pregão ausente do arquivo vira `liquido=0`/`operou=False` -- mesma
    convenção de `alignment.preencher_calendario_b3`, só que `operou` é
    derivado da PRESENÇA da linha no arquivo (não de `n_trades`, que não
    existe neste formato).

    `bruto`/`custo`/`n_trades` ficam `NaN` -- genuinamente desconhecidos
    aqui, nunca inventados como 0 (ver docstring do módulo).
    `resultado_zero` usa `liquido==0` em vez de `bruto==0`
    (`alignment.preencher_calendario_b3`'s definição) -- mesma
    divergência pela mesma razão: sem `bruto`, não há como usar a
    definição original. `liquido_por_contrato` = `liquido` porque
    `CONTRATOS_REFERENCIA_RESULTADOS_DIARIOS=1` (decisão do usuário, não
    detectada)."""
    calendario = mcal.get_calendar("B3")
    inicio, fim = resultados.index.min(), resultados.index.max()
    pregoes = calendario.schedule(start_date=inicio, end_date=fim).index

    liquido = resultados["liquido"].reindex(pregoes, fill_value=0.0)
    operou = pd.Series(True, index=resultados.index).reindex(pregoes, fill_value=False)

    diario = pd.DataFrame({
        "liquido": liquido,
        "liquido_por_contrato": liquido / CONTRATOS_REFERENCIA_RESULTADOS_DIARIOS,
        "bruto": np.nan,
        "custo": np.nan,
        "n_trades": np.nan,
        "operou": operou,
    })
    diario.index.name = "data"
    diario["resultado_zero"] = diario["operou"] & (diario["liquido"] == 0)
    return diario
