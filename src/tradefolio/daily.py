"""Orders -> daily P&L series, before B3 calendar alignment.

`n_trades` counts "saída" rows per day -- an approximate proxy (matches the
original code's own `operacoes_aprox` naming), distinct from the precise
trade count in tradefolio.trades.reconstruir_trades, which groups partial
fills. The two coincide only when no trade that day has a split saída.
"""
import pandas as pd

from tradefolio.costs import CUSTO_POR_PERNA_PADRAO, custo_b3

CONTRATOS_REFERENCIA_PADRAO = 2

FRACAO_MINIMA_DOMINANTE = 0.9


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


def detectar_contratos_referencia(ordens: pd.DataFrame) -> int:
    """Infere o número de contratos de referência do backtest a partir do
    valor mais frequente de 'Quantidade executada'.

    AGENTS.md §9: cada robô tem seu próprio tamanho de posição -- não
    pode ser assumido (CONTRATOS_REFERENCIA_PADRAO é o default de
    agregar_diario/calcular_pagina1 apenas por retrocompatibilidade;
    quem orquestra o carregamento deve chamar esta função em vez de
    confiar no default). Tolera uma minoria de linhas com quantidade
    diferente (fills parciais -- o próprio romanos_orders.csv já
    validado tem 4 linhas com 1 contrato em 1645, ~99.76% dominante) via
    FRACAO_MINIMA_DOMINANTE; abaixo desse limiar não é seguro inferir
    uma única referência (ex.: um robô com tamanho de posição dinâmico)
    e a ambiguidade é levantada em vez de adivinhada.
    """
    contagem = ordens["Quantidade executada"].value_counts()
    valor_dominante = contagem.idxmax()
    fracao_dominante = contagem.max() / contagem.sum()
    if fracao_dominante < FRACAO_MINIMA_DOMINANTE:
        raise ValueError(
            "não foi possível inferir um único número de contratos de referência "
            f"(nenhum valor atinge {FRACAO_MINIMA_DOMINANTE:.0%} das linhas) -- "
            f"distribuição de 'Quantidade executada': {contagem.to_dict()}"
        )
    return int(valor_dominante)


def escalar_por_contratos(valores, n_contratos: float):
    """Escala um valor absoluto (ou série) já normalizado por-contrato
    para um número hipotético de contratos `n_contratos`. Escala linear
    direta (AGENTS.md §9) -- só use em valores/séries em R$ absolutos;
    métricas percentuais e razões (Sharpe, Calmar, Profit Factor, etc.)
    são invariantes ao número de contratos e não devem passar por aqui."""
    if n_contratos < 0:
        raise ValueError("n_contratos não pode ser negativo")
    return valores * n_contratos
