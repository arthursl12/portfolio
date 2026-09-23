"""
Lâmina de robô — Fase 1
Parser de ordens (formato Smarttbot) -> dataframe diário -> métricas de resumo,
curva/drawdown e distribuição/cauda.
"""

import sys

import pandas as pd
import numpy as np
import pandas_market_calendars as mcal

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
CSV_PATH = "/mnt/user-data/uploads/orders_romanos.csv"
CUSTO_POR_CONTRATO_PERNA = 0.25  # R$ B3, emolumento por contrato, por perna (entrada OU saída)
CONTRATOS_REFERENCIA = 2          # quantidade padrão usada no backtest (p/ normalizar R$/contrato)


def parse_valor_br(s: pd.Series) -> pd.Series:
    """Converte string BR ('1.234,56' ou '-') para float."""
    s = s.astype(str).str.strip()
    s = s.replace({"-": np.nan, "nan": np.nan})
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def carregar_ordens(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path, sep=";", quotechar='"', encoding="utf-8")
    df["dt"] = pd.to_datetime(df["Data/Hora"], format="%d/%m/%Y / %H:%M:%S")
    df["data"] = df["dt"].dt.normalize()
    df["Resultado (R$)"] = parse_valor_br(df["Resultado (R$)"])
    df["Quantidade executada"] = pd.to_numeric(df["Quantidade executada"], errors="coerce")
    return df.sort_values("dt").reset_index(drop=True)


def agregar_diario(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega ordens em série diária de resultado líquido, já descontando custos B3."""
    saidas = df[df["Tipo"] == "saída"]
    bruto_dia = saidas.groupby("data")["Resultado (R$)"].sum().rename("bruto")

    # custo: 0,25 por contrato por perna, aplicado em TODA linha (entrada e saída)
    custo_dia = (
        df.groupby("data")["Quantidade executada"].sum() * CUSTO_POR_CONTRATO_PERNA
    ).rename("custo")

    n_trades_dia = saidas.groupby("data").size().rename("n_trades")

    diario = pd.concat([bruto_dia, custo_dia, n_trades_dia], axis=1).fillna(0)
    diario["liquido"] = diario["bruto"] - diario["custo"]
    diario["liquido_por_contrato"] = diario["liquido"] / CONTRATOS_REFERENCIA
    return diario


def preencher_calendario_b3(diario: pd.DataFrame) -> pd.DataFrame:
    """Reindexa a série diária no calendário de pregões da B3, preenchendo dias sem operação com 0."""
    cal = mcal.get_calendar("B3")
    inicio, fim = diario.index.min(), diario.index.max()
    pregoes = cal.schedule(start_date=inicio, end_date=fim).index

    diario = diario.reindex(pregoes, fill_value=0)
    diario.index.name = "data"

    # dias operados vs. dias apenas presentes no calendário (sem trade)
    diario["operou"] = diario["n_trades"] > 0
    return diario


def montar_dataframe_diario(csv_path: str = CSV_PATH) -> pd.DataFrame:
    ordens = carregar_ordens(csv_path)
    diario = agregar_diario(ordens)
    diario = preencher_calendario_b3(diario)
    return diario


DIAS_UTEIS_ANO = 252
CAPITAL_POR_CONTRATO = 1000.0  # margem sugerida pelo autor do robô, usada pela Smarttbot como saldo inicial


def calcular_metricas_pagina1(diario: pd.DataFrame) -> dict:
    serie = diario["liquido_por_contrato"]

    dias_pos = serie[serie > 0]
    dias_neg = serie[serie < 0]

    equity = serie.cumsum()
    pico = equity.cummax()
    drawdown = equity - pico  # em R$, <= 0

    # Time under water: maior sequência de dias com drawdown < 0
    submerso = (drawdown < 0).astype(int)
    # tamanho de cada sequência contínua de 1s
    grupos = (submerso != submerso.shift()).cumsum()
    tuw_max = submerso.groupby(grupos).sum().max() if submerso.any() else 0

    n_anos = (diario.index.max() - diario.index.min()).days / 365.25
    retorno_total = serie.sum()
    retorno_anualizado = retorno_total / n_anos if n_anos > 0 else np.nan

    max_dd = drawdown.min()
    std_dia = serie.std()
    std_neg = dias_neg.std() if len(dias_neg) > 1 else np.nan

    # patrimônio e drawdown percentual, na mesma lógica da Smarttbot:
    # saldo inicial = R$1.000/contrato; drawdown% relativo ao pico móvel do patrimônio
    patrimonio = CAPITAL_POR_CONTRATO + equity
    pico_patrimonio = patrimonio.cummax()
    drawdown_pct = (patrimonio - pico_patrimonio) / pico_patrimonio

    m = {
        "periodo": (diario.index.min().date(), diario.index.max().date()),
        "pregoes": len(diario),
        "operacoes_aprox": int(diario["n_trades"].sum()),
        "lucro_liquido_2c": diario["liquido"].sum(),
        "lucro_liquido_por_contrato": retorno_total,
        "media_diaria": serie.mean(),
        "mediana_diaria": serie.median(),
        "pct_dias_positivos": len(dias_pos) / len(diario),
        "pct_dias_negativos": len(dias_neg) / len(diario),
        "pct_dias_neutros": (len(diario) - len(dias_pos) - len(dias_neg)) / len(diario),
        "gain_medio": dias_pos.mean(),
        "loss_medio": dias_neg.mean(),
        "payoff": dias_pos.mean() / abs(dias_neg.mean()),
        "expectancia_diaria": serie.mean(),
        "profit_factor_diario": dias_pos.sum() / abs(dias_neg.sum()),
        "pior_dia": serie.min(),
        "melhor_dia": serie.max(),
        "max_drawdown": max_dd,
        "max_drawdown_pct": drawdown_pct.min() * 100,
        "retorno_bruto_pct": (diario["bruto"].sum() / CONTRATOS_REFERENCIA) / CAPITAL_POR_CONTRATO * 100,
        "retorno_liquido_pct": retorno_total / CAPITAL_POR_CONTRATO * 100,
        "time_under_water_max_pregoes": int(tuw_max),
        "ulcer_index_rs": np.sqrt((drawdown**2).mean()),
        "ulcer_index_pct": np.sqrt((drawdown_pct**2).mean()) * 100,
        "sharpe": (serie.mean() / std_dia) * np.sqrt(DIAS_UTEIS_ANO) if std_dia else np.nan,
        "sortino": (serie.mean() / std_neg) * np.sqrt(DIAS_UTEIS_ANO) if std_neg and not np.isnan(std_neg) else np.nan,
        "calmar": retorno_anualizado / abs(max_dd) if max_dd else np.nan,
        "recovery_factor": retorno_total / abs(max_dd) if max_dd else np.nan,
    }
    return m, equity, drawdown


def reconstruir_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Reconstrói trades a partir da posição líquida, agrupando fills parciais.
    Um trade começa quando a posição sai de 0 e termina quando volta a 0."""
    pos = 0
    trades = []
    atual = None

    for _, row in df.iterrows():
        qty = row["Quantidade executada"]
        sinal = 1 if row["C/V"] == "C" else -1
        if pos == 0:
            atual = {
                "inicio": row["dt"], "direcao": "compra" if sinal > 0 else "venda",
                "resultado_bruto": 0.0, "qtd_negociada": 0,
            }
        pos += sinal * qty
        atual["qtd_negociada"] += qty  # conta a perna (entrada OU saída) individualmente
        if row["Tipo"] == "saída" and not pd.isna(row["Resultado (R$)"]):
            atual["resultado_bruto"] += row["Resultado (R$)"]
        if pos == 0:
            atual["fim"] = row["dt"]
            trades.append(atual)

    trades_df = pd.DataFrame(trades)
    trades_df["custo"] = trades_df["qtd_negociada"] * CUSTO_POR_CONTRATO_PERNA
    trades_df["resultado_liquido"] = trades_df["resultado_bruto"] - trades_df["custo"]
    return trades_df


def maior_sequencia(serie_sinal: pd.Series, positivo: bool) -> int:
    alvo = serie_sinal > 0 if positivo else serie_sinal < 0
    grupos = (alvo != alvo.shift()).cumsum()
    tamanhos = alvo.groupby(grupos).sum()
    return int(tamanhos.max()) if len(tamanhos) else 0


def maior_sequencia_detalhada(serie: pd.Series, positivo: bool, datas_inicio: pd.Series = None, datas_fim: pd.Series = None) -> dict:
    """Retorna comprimento, valor R$ acumulado e datas de início-fim da maior sequência.
    Para séries diárias, datas_inicio/datas_fim podem ser omitidas (usa o próprio índice).
    Para trades (índice inteiro), passe as colunas 'inicio'/'fim' do dataframe de trades."""
    alvo = serie > 0 if positivo else serie < 0
    grupos = (alvo != alvo.shift()).cumsum()

    tamanhos = alvo.groupby(grupos).sum()
    tamanhos = tamanhos[tamanhos > 0]  # só blocos onde alvo é True
    if tamanhos.empty:
        return {"comprimento": 0, "valor_total": 0.0, "inicio": None, "fim": None}

    grupo_recorde = tamanhos.idxmax()
    mascara_recorde = grupos == grupo_recorde
    indices_recorde = serie.index[mascara_recorde]

    if datas_inicio is not None:
        data_inicio = datas_inicio.loc[indices_recorde[0]]
        data_fim = datas_fim.loc[indices_recorde[-1]]
    else:
        data_inicio, data_fim = indices_recorde[0], indices_recorde[-1]

    return {
        "comprimento": int(tamanhos.max()),
        "valor_total": serie.loc[mascara_recorde].sum(),
        "inicio": data_inicio,
        "fim": data_fim,
    }


def calcular_episodios_drawdown(equity: pd.Series) -> pd.DataFrame:
    """Calcula TODOS os episódios de drawdown (sem cortar top_n) — base para os rankings."""
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
    """Top N episódios por profundidade (R$)."""
    todos = calcular_episodios_drawdown(equity)
    return todos.sort_values("profundidade_rs").head(top_n).reset_index(drop=True)


def piores_time_under_water(equity: pd.Series, top_n: int = 10) -> pd.DataFrame:
    """Top N episódios por tempo submerso (pregões), independente da profundidade."""
    todos = calcular_episodios_drawdown(equity)
    return todos.sort_values("pregoes_submerso", ascending=False).head(top_n).reset_index(drop=True)


def calcular_metricas_pagina2(diario: pd.DataFrame, ordens: pd.DataFrame) -> dict:
    trades = reconstruir_trades(ordens)
    trades["resultado_liquido_por_contrato"] = trades["resultado_liquido"] / CONTRATOS_REFERENCIA

    ganhos = trades[trades["resultado_liquido"] > 0]["resultado_liquido"]
    perdas = trades[trades["resultado_liquido"] < 0]["resultado_liquido"]

    _, equity, drawdown = calcular_metricas_pagina1(diario)[0], *calcular_metricas_pagina1(diario)[1:]

    return {
        "trades": trades,
        "n_trades": len(trades),
        "win_rate_trades": len(ganhos) / len(trades),
        "profit_factor_trades": ganhos.sum() / abs(perdas.sum()),
        "lucro_medio_trade": ganhos.mean(),
        "prejuizo_medio_trade": perdas.mean(),
        "maior_sequencia_positiva_trades": maior_sequencia_detalhada(
            trades["resultado_liquido"], True, trades["inicio"], trades["fim"]),
        "maior_sequencia_negativa_trades": maior_sequencia_detalhada(
            trades["resultado_liquido"], False, trades["inicio"], trades["fim"]),
        "maior_sequencia_positiva_dias": maior_sequencia_detalhada(diario["liquido_por_contrato"], True),
        "maior_sequencia_negativa_dias": maior_sequencia_detalhada(diario["liquido_por_contrato"], False),
        "episodios_drawdown": episodios_drawdown(equity, top_n=10),
        "piores_tuw": piores_time_under_water(equity, top_n=10),
    }


def calcular_metricas_pagina3(diario: pd.DataFrame) -> dict:
    """Distribuição e risco de cauda sobre o resultado diário (por contrato)."""
    serie = diario["liquido_por_contrato"]
    dias_neg = serie[serie < 0]

    percentis = {p: serie.quantile(p / 100) for p in [1, 5, 10, 25, 50, 75, 90, 95, 99]}

    piores_5 = serie.nsmallest(5)
    melhores_5 = serie.nlargest(5)

    var_95 = serie.quantile(0.05)
    var_99 = serie.quantile(0.01)
    es_95 = serie[serie <= var_95].mean()
    es_99 = serie[serie <= var_99].mean()

    return {
        "serie": serie,
        "media": serie.mean(),
        "mediana": serie.median(),
        "desvio_padrao": serie.std(),
        "skewness": serie.skew(),
        "kurtosis": serie.kurt(),  # excesso de curtose (normal = 0)
        "percentis": percentis,
        "piores_5_media": piores_5.mean(),
        "piores_5": piores_5,
        "melhores_5_media": melhores_5.mean(),
        "melhores_5": melhores_5,
        "var_95": var_95,
        "var_99": var_99,
        "es_95": es_95,
        "es_99": es_99,
        "n_dias_negativos": len(dias_neg),
    }


if __name__ == "__main__":
    # Script de referência legado (README: "não é mais o caminho usado por
    # report.py") -- aceita o CSV como argumento opcional em vez de exigir
    # editar CSV_PATH; sem argumento, mantém o default acima inalterado.
    csv_path = sys.argv[1] if len(sys.argv) > 1 else CSV_PATH

    diario = montar_dataframe_diario(csv_path)
    metricas, equity, drawdown = calcular_metricas_pagina1(diario)
    for k, v in metricas.items():
        print(f"{k:35s}: {v}")

    ordens = carregar_ordens(csv_path)
    p2 = calcular_metricas_pagina2(diario, ordens)
    print("\n--- Página 2 ---")
    print("Maior sequência positiva (trades):", p2["maior_sequencia_positiva_trades"])
    print("Maior sequência negativa (trades):", p2["maior_sequencia_negativa_trades"])
    print("Maior sequência positiva (dias):  ", p2["maior_sequencia_positiva_dias"])
    print("Maior sequência negativa (dias):  ", p2["maior_sequencia_negativa_dias"])
    print("\nTrades reconstruídos:", len(p2["trades"]))
    t = p2["trades"]
    print("Win rate (trades):", (t["resultado"] > 0).mean())
    print("Lucro médio (trades c/ lucro):", t.loc[t["resultado"] > 0, "resultado"].mean())
    print("Prejuízo médio (trades c/ prejuízo):", t.loc[t["resultado"] < 0, "resultado"].mean())
    print("\nTop 10 episódios de drawdown (por contrato):")
    print(p2["episodios_drawdown"].to_string(index=False))