"""Curve-quality metrics: concentration and event-removal (AGENTS.md épico
5, tarefas 5.1/5.2).

participacao_top_n and resultado_sem_top_n are generic over any classified
series (AGENTS.md §8.1) -- the same formula serves the daily series
("participação dos 5 melhores dias") and the monthly one ("participação
dos 3 melhores meses"). Deliberately NOT clamped to [0, 1]: a ratio above
100% (top N alone exceeds total profit) is a genuine concentration
red flag ("lâmina ideal.pdf" §9 has exactly this as an alert example --
"Os três melhores meses representam 118% do lucro"), not an error to hide.

resultado_antes_dos_ultimos_n_dias is positional (chronological order),
not ranking-based -- it only makes sense for the daily series (a "month"
doesn't have a stable window-of-N-days-back reading the same way).
"""
import math

import numpy as np
import pandas as pd

from tradefolio import metrics
from tradefolio.drawdowns import curva_equity, drawdown, maximo_drawdown


def participacao_top_n(serie: pd.Series, n: int) -> float:
    total = serie.sum()
    if total == 0:
        return math.nan
    return serie.nlargest(n).sum() / total


def resultado_sem_top_n(serie: pd.Series, n: int) -> float:
    return serie.sum() - serie.nlargest(n).sum()


def resultado_antes_dos_ultimos_n_dias(serie: pd.Series, n: int = 60) -> float:
    if len(serie) <= n:
        return math.nan
    return serie.iloc[:-n].sum()


def pct_dias_abaixo_de_zero(equity: pd.Series) -> float:
    """AGENTS.md épico 5.4: fração de pregões com equity acumulada (não
    relativa ao pico -- ver tradefolio.drawdowns para isso) negativa."""
    return (equity < 0).mean()


def primeira_data_positiva(equity: pd.Series):
    """Primeira data em que a equity acumulada é >= 0. None se a equity
    nunca chega a zero/positiva na amostra."""
    positivos = equity[equity >= 0]
    return positivos.index[0] if len(positivos) else None


def ultima_data_negativa(equity: pd.Series):
    """Última data em que a equity acumulada é < 0. None se a equity nunca
    fica negativa na amostra."""
    negativos = equity[equity < 0]
    return negativos.index[-1] if len(negativos) else None


def escolher_numero_de_blocos(serie: pd.Series) -> int:
    """AGENTS.md épico 5.5: número de blocos conforme a duração total do
    histórico, por CONTAGEM DE PREGÕES (não mês-calendário -- ver limitação
    no docstring do módulo/TASKS.md). < 6 meses não subdivide (histórico
    curto demais para blocos significativos)."""
    meses = (serie.index.max() - serie.index.min()).days / 30.44
    if meses < 6:
        return 1
    if meses <= 12:
        return 3
    if meses <= 24:
        return 4
    return max(4, round(meses / 6))  # semestres aproximados


def dividir_em_subperiodos(serie: pd.Series, n_blocos: int = None) -> list:
    """Divide `serie` em `n_blocos` blocos contíguos de tamanho
    aproximadamente igual (por posição/contagem de pregões, não alinhados
    a mês-calendário -- ver limitação no docstring do módulo)."""
    if n_blocos is None:
        n_blocos = escolher_numero_de_blocos(serie)
    return [serie.loc[idx] for idx in np.array_split(serie.index, n_blocos)]


def metricas_por_subperiodo(serie: pd.Series, n_blocos: int = None) -> pd.DataFrame:
    """Lucro, Maximum Drawdown, Profit Factor e % de dias positivos por
    subperíodo (AGENTS.md épico 5.5). Dois campos do épico NÃO
    implementados, documentados em vez de inventados: RLT (bloqueado pelo
    Épico 6 -- limiar não existe) e "estabilidade" (termo não definido em
    lugar nenhum do PDF-fonte). "Meses positivos" também não é
    implementado por bloco -- os blocos são por contagem de pregões, não
    alinhados a mês-calendário, então usa-se % de DIAS positivos como
    proxy equivalente e já disponível (metrics.taxa_positivos)."""
    blocos = dividir_em_subperiodos(serie, n_blocos)
    linhas = []
    for bloco in blocos:
        equity = curva_equity(bloco)
        dd = drawdown(equity)
        linhas.append({
            "inicio": bloco.index.min(),
            "fim": bloco.index.max(),
            "lucro": bloco.sum(),
            "max_drawdown": maximo_drawdown(dd),
            "profit_factor": metrics.profit_factor(bloco),
            "pct_dias_positivos": metrics.taxa_positivos(bloco),
        })
    return pd.DataFrame(linhas)


def detectar_alertas_curva(serie_diaria: pd.Series, serie_mensal: pd.Series, dias_recentes: int = 60) -> list[dict]:
    """Regras determinísticas de "curva salva recentemente" (AGENTS.md
    épico 5.3), diretamente do PDF-fonte. Cada alerta segue o schema de
    épico 17 (warning_code/severity/metric/observed_value/threshold/
    message) -- dict simples, não uma classe nova, já que é exatamente o
    contrato externo que um consumidor (API/IA) esperaria.
    """
    alertas = []

    lucro_antes = resultado_antes_dos_ultimos_n_dias(serie_diaria, dias_recentes)
    if not math.isnan(lucro_antes) and lucro_antes <= 0:
        alertas.append({
            "warning_code": "NEGATIVE_BEFORE_LAST_60_DAYS",
            "severity": "high",
            "metric": "profit_before_last_60_days",
            "observed_value": lucro_antes,
            "threshold": 0.0,
            "message": f"Resultado antes dos últimos {dias_recentes} dias é {lucro_antes:.2f} (<= 0).",
        })

    participacao_melhor_mes = participacao_top_n(serie_mensal, 1)
    if not math.isnan(participacao_melhor_mes) and participacao_melhor_mes > 0.75:
        alertas.append({
            "warning_code": "PROFIT_SAVED_BY_BEST_MONTH",
            "severity": "high",
            "metric": "best_month_profit_share",
            "observed_value": participacao_melhor_mes,
            "threshold": 0.75,
            "message": f"O melhor mês representa {participacao_melhor_mes:.1%} do lucro total.",
        })

    participacao_top3_meses = participacao_top_n(serie_mensal, 3)
    if not math.isnan(participacao_top3_meses) and participacao_top3_meses > 1.0:
        alertas.append({
            "warning_code": "TOP3_EXCEEDS_TOTAL_PROFIT",
            "severity": "critical",
            "metric": "top3_months_profit_share",
            "observed_value": participacao_top3_meses,
            "threshold": 1.0,
            "message": f"Os três melhores meses representam {participacao_top3_meses:.1%} do lucro total.",
        })

    return alertas


def pregoes_desde_consolidacao_positiva(equity: pd.Series) -> int:
    """Pregões desde a última vez que a equity esteve negativa (AGENTS.md
    épico 5.4). Se a amostra termina negativa (ainda não recuperou), o
    valor é 0 -- não faz sentido contar uma consolidação que não
    aconteceu. Se a equity nunca ficou negativa, toda a amostra conta como
    consolidada (retorna len(equity) - 1)."""
    negativos = equity[equity < 0]
    if not len(negativos):
        return len(equity) - 1
    posicao_ultima_negativa = equity.index.get_loc(negativos.index[-1])
    return len(equity) - 1 - posicao_ultima_negativa
