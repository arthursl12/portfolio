"""Orchestration: composes the calculation modules into the page-1/2/3
dicts that report.py renders. Pure data assembly -- no HTML/matplotlib
here (AGENTS.md §16: keep business logic separate from presentation).
"""
import pandas as pd

from tradefolio import concentracao, drawdowns, limiar, metrics
from tradefolio.alignment import preencher_calendario_b3
from tradefolio.daily import (
    CONTRATOS_REFERENCIA_PADRAO,
    agregar_diario,
    agregar_diario_por_ativo,
    detectar_contratos_referencia,
    pivotar_liquido_por_ativo,
)
from tradefolio.drawdowns import CAPITAL_POR_CONTRATO_PADRAO
from tradefolio.loaders import carregar_ordens
from tradefolio.monthly import agregar_mensal
from tradefolio.trades import reconstruir_trades

PERCENTIS_PAGINA3 = (1, 5, 10, 25, 50, 75, 90, 95, 99)

JANELAS_DISPONIVEIS = (
    "1 semana", "1 mês", "3 meses", "6 meses", "1 ano", "2 anos", "desde o início",
)

_OFFSET_POR_JANELA = {
    "1 semana": pd.DateOffset(weeks=1),
    "1 mês": pd.DateOffset(months=1),
    "3 meses": pd.DateOffset(months=3),
    "6 meses": pd.DateOffset(months=6),
    "1 ano": pd.DateOffset(years=1),
    "2 anos": pd.DateOffset(years=2),
}


def filtrar_por_janela(diario: pd.DataFrame, janela: str) -> pd.DataFrame:
    """Recorta `diario` para os últimos `janela` a partir da ÚLTIMA data
    presente nos dados (não da data de hoje -- o histórico pode terminar
    no passado). "desde o início" retorna os dados sem filtrar. Um
    rótulo desconhecido levanta erro em vez de silenciosamente não
    filtrar."""
    if janela == "desde o início":
        return diario
    if janela not in _OFFSET_POR_JANELA:
        raise ValueError(
            f"janela desconhecida: {janela!r} -- use uma de {JANELAS_DISPONIVEIS}"
        )
    inicio = diario.index.max() - _OFFSET_POR_JANELA[janela]
    return diario.loc[inicio:]


def montar_dataframe_diario(csv_path, contratos_referencia: int = None) -> pd.DataFrame:
    """`contratos_referencia=None` (padrão) detecta automaticamente a
    partir do próprio CSV (tradefolio.daily.detectar_contratos_referencia)
    -- AGENTS.md §9: cada robô tem seu próprio tamanho de posição, não
    pode ser assumido igual a outro. Passe um valor explícito só se
    precisar sobrepor a detecção."""
    ordens = carregar_ordens(csv_path)
    if contratos_referencia is None:
        contratos_referencia = detectar_contratos_referencia(ordens)
    diario = agregar_diario(ordens, contratos_referencia=contratos_referencia)
    return preencher_calendario_b3(diario)


def calcular_pagina1(
    diario: pd.DataFrame,
    contratos_referencia: int = CONTRATOS_REFERENCIA_PADRAO,
    ordens: pd.DataFrame = None,
) -> tuple[dict, pd.Series, pd.Series]:
    serie = diario["liquido_por_contrato"]

    equity = drawdowns.curva_equity(serie)
    dd = drawdowns.drawdown(equity)
    dd_pct = drawdowns.drawdown_pct(drawdowns.patrimonio(equity))
    max_dd = drawdowns.maximo_drawdown(dd)

    m = {
        "periodo": (diario.index.min().date(), diario.index.max().date()),
        "pregoes": len(diario),
        "lucro_liquido_2c": diario["liquido"].sum(),
        "lucro_liquido_por_contrato": serie.sum(),
        "media_diaria": serie.mean(),
        "media_diaria_dias_operados": serie[diario["operou"]].mean(),
        "mediana_diaria": serie.median(),
        "pct_dias_positivos": metrics.taxa_positivos(serie),
        "pct_dias_negativos": metrics.taxa_negativos(serie),
        "pct_dias_neutros": metrics.taxa_neutros(serie),
        "gain_medio": metrics.ganho_medio(serie),
        "loss_medio": metrics.perda_media(serie),
        "payoff": metrics.payoff(serie),
        "expectancia_diaria": metrics.expectancia(serie),
        "profit_factor_diario": metrics.profit_factor(serie),
        "pior_dia": serie.min(),
        "melhor_dia": serie.max(),
        "max_drawdown": max_dd,
        "max_drawdown_pct": drawdowns.maximo_drawdown_pct(dd_pct),
        "retorno_bruto_pct": (diario["bruto"].sum() / contratos_referencia)
        / CAPITAL_POR_CONTRATO_PADRAO
        * 100,
        "retorno_liquido_pct": serie.sum() / CAPITAL_POR_CONTRATO_PADRAO * 100,
        "time_under_water_max_pregoes": drawdowns.time_under_water_max(dd),
        "ulcer_index_rs": drawdowns.ulcer_index(dd),
        "ulcer_index_pct": drawdowns.ulcer_index_pct(dd_pct),
        "sharpe": metrics.sharpe(serie),
        "sortino": metrics.sortino(serie),
        "calmar": metrics.calmar(serie, max_dd),
        "recovery_factor": metrics.recovery_factor(serie, max_dd),
    }
    if ordens is not None:
        # Escala bruta (não normalizada por contrato): um robô multi-ativo
        # pode não ter uma única referência de contratos estável por ativo
        # (ver tarefa 2.2/TASKS.md -- WDO do Robô Raiz é um caso real disso),
        # então dividir por contratos_referencia aqui misturaria escalas.
        m["lucro_por_ativo"] = (
            agregar_diario_por_ativo(ordens).groupby("ativo_raiz")["liquido"].sum().to_dict()
        )
    return m, equity, dd


def calcular_pagina2(diario: pd.DataFrame, ordens: pd.DataFrame) -> dict:
    trades = reconstruir_trades(ordens)
    resultado = trades["resultado_liquido"]

    _, equity, _ = calcular_pagina1(diario)

    return {
        "trades": trades,
        "n_trades": len(trades),
        "win_rate_trades": metrics.taxa_positivos(resultado),
        "profit_factor_trades": metrics.profit_factor(resultado),
        "lucro_medio_trade": metrics.ganho_medio(resultado),
        "prejuizo_medio_trade": metrics.perda_media(resultado),
        "expectancia_por_trade": metrics.expectancia(resultado),
        "maior_sequencia_positiva_trades": metrics.maior_sequencia_detalhada(
            resultado, True, trades["inicio"], trades["fim"]
        ),
        "maior_sequencia_negativa_trades": metrics.maior_sequencia_detalhada(
            resultado, False, trades["inicio"], trades["fim"]
        ),
        "maior_sequencia_positiva_dias": metrics.maior_sequencia_detalhada(
            diario["liquido_por_contrato"], True
        ),
        "maior_sequencia_negativa_dias": metrics.maior_sequencia_detalhada(
            diario["liquido_por_contrato"], False
        ),
        "episodios_drawdown": drawdowns.episodios_drawdown(equity, top_n=10),
        "piores_tuw": drawdowns.piores_time_under_water(equity, top_n=10),
    }


def calcular_pagina4(
    diario: pd.DataFrame,
    minimum_margin: float,
    percentil_cauda: int = 95,
    fracao_reserva_operacional: float = 0.0,
    increment: float = 500,
) -> dict:
    """Limiar, RLT e risco normalizado pelo limiar (lâmina ideal.pdf
    §4/5/7). Escala TOTAL (`diario['liquido']`), não por contrato --
    `minimum_margin` é da posição total (decisão confirmada com o
    usuário nesta sessão, ver tradefolio.limiar). `limiar_p95`/`limiar_p99`
    são sempre os DOIS calculados (resolução do usuário: "use both...
    toggle button somewhere"); `percentil_cauda` só escolhe qual alimenta
    o resto da página (`limiar_ativo`, RLT, normalizações de risco)."""
    serie = diario["liquido"]
    equity = drawdowns.curva_equity(serie)
    dd = drawdowns.drawdown(equity)
    mdd = drawdowns.maximo_drawdown(dd)
    pior_dia = serie.min()
    es95 = metrics.expected_shortfall(serie, 0.95)
    ulcer = drawdowns.ulcer_index(dd)
    mensal = agregar_mensal(diario)
    pior_mes = mensal["liquido"].min()
    meses_historico = (serie.index.max() - serie.index.min()).days / 30.44

    limiar_p95 = limiar.decompor_limiar(
        minimum_margin, dd, meses_historico, 95, fracao_reserva_operacional, increment
    )
    limiar_p99 = limiar.decompor_limiar(
        minimum_margin, dd, meses_historico, 99, fracao_reserva_operacional, increment
    )
    limiar_escolhido = limiar_p95 if percentil_cauda == 95 else limiar_p99
    limiar_ativo = limiar_escolhido.get("limiar_recomendado", limiar_escolhido["limiar_bruto"])

    liquido_mensal = mensal["liquido"]
    rlt_mensal_serie = limiar.rlt_mensal(liquido_mensal, limiar_ativo)

    return {
        "meses_historico": meses_historico,
        "limiar_p95": limiar_p95,
        "limiar_p99": limiar_p99,
        "percentil_cauda_ativo": percentil_cauda,
        "limiar_ativo": limiar_ativo,
        "rlt_acumulado": limiar.rlt_acumulado(serie.sum(), limiar_ativo),
        "rlt_anualizado": limiar.rlt_anualizado(serie, limiar_ativo),
        "rlt_mensal_medio": rlt_mensal_serie.mean(),
        "rlt_mensal_mediano": rlt_mensal_serie.median(),
        "rlt_movel_3": limiar.rlt_movel(liquido_mensal, limiar_ativo, 3).iloc[-1],
        "rlt_movel_6": limiar.rlt_movel(liquido_mensal, limiar_ativo, 6).iloc[-1],
        "rlt_movel_12": limiar.rlt_movel(liquido_mensal, limiar_ativo, 12).iloc[-1],
        "mdd_total": mdd,
        "mdd_sobre_limiar": limiar.normalizar_por_limiar(mdd, limiar_ativo),
        "pior_dia_total": pior_dia,
        "pior_dia_sobre_limiar": limiar.normalizar_por_limiar(pior_dia, limiar_ativo),
        "es95_total": es95,
        "es95_sobre_limiar": limiar.normalizar_por_limiar(es95, limiar_ativo),
        "ulcer_total": ulcer,
        "ulcer_sobre_limiar": limiar.normalizar_por_limiar(ulcer, limiar_ativo),
        "pior_mes_total": pior_mes,
        "pior_mes_sobre_limiar": limiar.normalizar_por_limiar(pior_mes, limiar_ativo),
    }


def calcular_pagina5(diario: pd.DataFrame, dias_recentes: int = 60) -> dict:
    """Qualidade da curva (lâmina ideal.pdf §9) -- só compõe
    tradefolio.concentracao (AGENTS.md épico 5, já implementado). Escala
    TOTAL (`diario['liquido']`), mesma decisão de calcular_pagina4."""
    serie = diario["liquido"]
    equity = drawdowns.curva_equity(serie)
    mensal = agregar_mensal(diario)["liquido"]

    return {
        "top1_dia": concentracao.participacao_top_n(serie, 1),
        "top5_dias": concentracao.participacao_top_n(serie, 5),
        "top10_dias": concentracao.participacao_top_n(serie, 10),
        "melhor_mes_share": concentracao.participacao_top_n(mensal, 1),
        "top3_meses_share": concentracao.participacao_top_n(mensal, 3),
        "lucro_sem_melhor_dia": concentracao.resultado_sem_top_n(serie, 1),
        "lucro_sem_top5_dias": concentracao.resultado_sem_top_n(serie, 5),
        "lucro_sem_melhor_mes": concentracao.resultado_sem_top_n(mensal, 1),
        "lucro_sem_top3_meses": concentracao.resultado_sem_top_n(mensal, 3),
        "lucro_antes_dos_ultimos_60_dias": concentracao.resultado_antes_dos_ultimos_n_dias(
            serie, dias_recentes
        ),
        "pct_dias_abaixo_de_zero": concentracao.pct_dias_abaixo_de_zero(equity),
        "ultima_data_negativa": concentracao.ultima_data_negativa(equity),
        "pregoes_desde_consolidacao_positiva": concentracao.pregoes_desde_consolidacao_positiva(equity),
        "alertas": concentracao.detectar_alertas_curva(serie, mensal, dias_recentes),
    }


def calcular_pagina6(ordens: pd.DataFrame, n_piores_dias: int = 5) -> dict:
    """Comparação entre ativos internos (lâmina ideal.pdf §12) -- só faz
    sentido para robôs multi-ativo; quem chama decide SE chama (checar
    nunique(ativo_raiz) > 1 antes), esta função não guarda essa lógica.
    Reusa tradefolio.daily.pivotar_liquido_por_ativo + drawdowns/correlação
    já existentes, nenhuma fórmula nova. "compensacao_piores_dias" responde
    à pergunta do próprio PDF ("Nos piores dias do WIN, quanto o WDO
    ganhou?"): para os N piores dias de CADA ativo, o resultado dos
    demais ativos nas mesmas datas."""
    largo = pivotar_liquido_por_ativo(ordens)

    mdd_por_ativo = {}
    for col in largo.columns:
        equity = drawdowns.curva_equity(largo[col])
        dd = drawdowns.drawdown(equity)
        mdd_por_ativo[col] = drawdowns.maximo_drawdown(dd)

    compensacao_piores_dias = {}
    for col in largo.columns:
        piores = largo[col].nsmallest(n_piores_dias)
        tabela = largo.loc[piores.index].reset_index()
        compensacao_piores_dias[col] = tabela

    return {
        "ativos": list(largo.columns),
        "lucro_por_ativo": largo.sum().to_dict(),
        "mdd_por_ativo": mdd_por_ativo,
        "correlacao_ativos": largo.corr(),
        "compensacao_piores_dias": compensacao_piores_dias,
    }


def calcular_pagina3(diario: pd.DataFrame) -> dict:
    serie = diario["liquido_por_contrato"]
    dias_neg = serie[serie < 0]

    percentis = {p: metrics.percentil(serie, p) for p in PERCENTIS_PAGINA3}
    piores_5 = serie.nsmallest(5)
    melhores_5 = serie.nlargest(5)

    return {
        "serie": serie,
        "media": serie.mean(),
        "mediana": serie.median(),
        "desvio_padrao": serie.std(),
        "skewness": metrics.skewness(serie),
        "kurtosis": metrics.kurtosis_excedente(serie),
        "percentis": percentis,
        "piores_5_media": piores_5.mean(),
        "piores_5": piores_5,
        "melhores_5_media": melhores_5.mean(),
        "melhores_5": melhores_5,
        "var_95": metrics.var_historico(serie, 0.95),
        "var_99": metrics.var_historico(serie, 0.99),
        "es_95": metrics.expected_shortfall(serie, 0.95),
        "es_99": metrics.expected_shortfall(serie, 0.99),
        "n_dias_negativos": len(dias_neg),
    }
