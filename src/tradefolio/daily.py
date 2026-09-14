"""Orders -> daily P&L series, before B3 calendar alignment.

`n_trades` counts "saída" rows per day -- an approximate proxy (matches the
original code's own `operacoes_aprox` naming), distinct from the precise
trade count in tradefolio.trades.reconstruir_trades, which groups partial
fills. The two coincide only when no trade that day has a split saída.

Non-executed orders (Status != "executada" -- cancelada/expirada) are
excluded before aggregation (AGENTS.md épico 1, tarefa 1.1): counting a
cancelled order in n_trades would be factually wrong (nothing executed),
even though its Quantidade executada == 0 already keeps it from moving
bruto/custo.
"""
import pandas as pd
import pandas_market_calendars as mcal

from tradefolio.costs import CUSTO_POR_PERNA_PADRAO, custo_b3
from tradefolio.validation import STATUS_EXECUTADA, extrair_raiz_ativo

CONTRATOS_REFERENCIA_PADRAO = 2

FRACAO_MINIMA_DOMINANTE = 0.9


def agregar_diario(
    ordens: pd.DataFrame,
    custo_por_perna: float = CUSTO_POR_PERNA_PADRAO,
    contratos_referencia: int = CONTRATOS_REFERENCIA_PADRAO,
) -> pd.DataFrame:
    ordens = ordens[ordens["Status"] == STATUS_EXECUTADA]
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


def agregar_diario_por_ativo(
    ordens: pd.DataFrame,
    custo_por_perna: float = CUSTO_POR_PERNA_PADRAO,
) -> pd.DataFrame:
    """Como agregar_diario, mas quebrado por (data, raiz do ativo) --
    AGENTS.md épico 3, tarefa 3.1: robôs multi-ativo (ex. WIN + WDO) tinham
    o resultado somado sem distinção de ativo. Agrupa pela RAIZ do código
    de contrato (ex. "WINV26" -> "WIN"), não o código completo, para não
    quebrar a série a cada rolagem de vencimento. Um (data, raiz) sem
    nenhuma ordem simplesmente não aparece no índice (não é preenchido com
    zero -- isso é papel de tradefolio.alignment no nível agregado, não
    aqui, onde "esse ativo não operou nesse dia" e "não existe calendário
    desse ativo" seriam fáceis de confundir).
    """
    ordens = ordens[ordens["Status"] == STATUS_EXECUTADA].copy()
    ordens["ativo_raiz"] = ordens["Ativo"].map(extrair_raiz_ativo)
    saidas = ordens[ordens["Tipo"] == "saída"]

    chaves = ["data", "ativo_raiz"]
    bruto = saidas.groupby(chaves)["Resultado (R$)"].sum().rename("bruto")
    custo = custo_b3(
        ordens.groupby(chaves)["Quantidade executada"].sum(), custo_por_perna
    ).rename("custo")
    quantidade = ordens.groupby(chaves)["Quantidade executada"].sum().rename("quantidade")
    n_trades = saidas.groupby(chaves).size().rename("n_trades")

    diario = pd.concat([bruto, custo, quantidade, n_trades], axis=1).fillna(0)
    diario["liquido"] = diario["bruto"] - diario["custo"]
    return diario


def pivotar_liquido_por_ativo(ordens: pd.DataFrame) -> pd.DataFrame:
    """Reshape largo de agregar_diario_por_ativo['liquido'] (colunas =
    ativo_raiz), reindexado no mesmo calendário B3 completo que a
    agregação principal usaria (range de datas das ordens executadas) --
    base para MDD/correlação por ativo (AGENTS.md épico 3.1/12). Uma
    sessão sem NENHUMA ordem some no reindex (0); um (data, ativo) sem
    ordem DENTRO do range (ex. um ativo que só passou a operar depois do
    início do histórico) vira 0 via fillna -- mesma convenção NO_TRADE=0
    já usada em tradefolio.alignment, não deixado como NaN."""
    executadas = ordens[ordens["Status"] == STATUS_EXECUTADA]
    largo = agregar_diario_por_ativo(ordens)["liquido"].unstack("ativo_raiz")

    calendario = mcal.get_calendar("B3")
    pregoes = calendario.schedule(
        start_date=executadas["data"].min(), end_date=executadas["data"].max()
    ).index
    largo = largo.reindex(pregoes, fill_value=0.0).fillna(0.0)
    largo.index.name = "data"
    return largo


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

    Ordens não executadas (Status != "executada") são excluídas antes de
    contar -- elas legitimamente têm Quantidade executada == 0 e não devem
    ser tratadas como "mais um valor" na distribuição.
    """
    ordens = ordens[ordens["Status"] == STATUS_EXECUTADA]
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


def contratos_referencia_por_ativo(ordens: pd.DataFrame, dias_recentes: int = None) -> dict:
    """Detecta a quantidade de referência (`detectar_contratos_referencia`)
    PARA CADA `ativo_raiz` separadamente -- necessário para robôs
    multi-ativo com proporção FIXA e indivisível entre pernas (ex. Robô
    Raiz: 3 WIN + 2 WDO por unidade -- não dá pra aumentar só um lado).
    Misturar as pernas numa única distribuição de 'Quantidade executada'
    (como `detectar_contratos_referencia` sozinho faria) não detecta
    nada -- nem WIN nem WDO dominam a mistura.

    `dias_recentes` (opcional): restringe a detecção aos últimos N dias
    corridos a partir da última data presente em `ordens`. Existe porque
    mesmo POR PERNA o histórico inteiro pode não ter uma quantidade
    dominante -- a proporção pode ter mudado ao longo do tempo (ex.
    Robô Raiz mudou de 1 para 2 WDO por unidade em algum momento,
    Épico 2.2). Restringir a uma janela recente assume que a proporção
    ATUAL é o que importa -- não segmenta a história inteira em múltiplas
    configurações (isso seria um passo maior, ainda não implementado)."""
    executadas = ordens[ordens["Status"] == STATUS_EXECUTADA]
    if dias_recentes is not None:
        corte = executadas["data"].max() - pd.Timedelta(days=dias_recentes)
        executadas = executadas[executadas["data"] > corte]
    executadas = executadas.copy()
    executadas["ativo_raiz"] = executadas["Ativo"].map(extrair_raiz_ativo)

    return {
        raiz: detectar_contratos_referencia(executadas[executadas["ativo_raiz"] == raiz])
        for raiz in sorted(executadas["ativo_raiz"].unique())
    }


def detectar_contratos_referencia_multi_ativo(ordens: pd.DataFrame, dias_recentes: int = None) -> int:
    """Soma as quantidades de referência por ativo
    (`contratos_referencia_por_ativo`) -- para um robô multi-ativo com
    proporção fixa entre pernas, "1 unidade" é o pacote inteiro (ex. 3
    WIN + 2 WDO = 5), não uma perna isolada. Para um robô de ativo
    único, dá exatamente o mesmo resultado de `detectar_contratos_referencia`."""
    return sum(contratos_referencia_por_ativo(ordens, dias_recentes).values())


def escalar_por_contratos(valores, n_contratos: float):
    """Escala um valor absoluto (ou série) já normalizado por-contrato
    para um número hipotético de contratos `n_contratos`. Escala linear
    direta (AGENTS.md §9) -- só use em valores/séries em R$ absolutos;
    métricas percentuais e razões (Sharpe, Calmar, Profit Factor, etc.)
    são invariantes ao número de contratos e não devem passar por aqui."""
    if n_contratos < 0:
        raise ValueError("n_contratos não pode ser negativo")
    return valores * n_contratos
