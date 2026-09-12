"""Generic ratio/descriptive metrics over a classified result series.

Same formulas serve day-level and trade-level series (AGENTS.md §8.1) --
callers must not mix the two bases, only pass one classified series at a
time and label which basis it is.
"""
import math

import pandas as pd

DIAS_UTEIS_ANO_PADRAO = 252


def payoff(serie: pd.Series) -> float:
    """AGENTS.md §8.3: avg gain / abs(avg loss).

    Edge cases (defined per §8.3's requirement, not left implicit):
    no losses -> +inf; no gains -> 0.0; neither -> nan.
    """
    n_ganhos = (serie > 0).sum()
    n_perdas = (serie < 0).sum()
    if n_ganhos == 0 and n_perdas == 0:
        return math.nan
    if n_ganhos == 0:
        return 0.0
    if n_perdas == 0:
        return math.inf
    return ganho_medio(serie) / abs(perda_media(serie))


def profit_factor(serie: pd.Series) -> float:
    """AGENTS.md §8.5: gross positive / abs(gross negative).

    Edge cases (defined per §8.5's requirement, not left implicit):
    no losses -> +inf; neither gains nor losses -> nan. No-gains case
    resolves naturally to 0.0 via the formula itself (positivos == 0).
    """
    positivos = serie[serie > 0].sum()
    negativos = serie[serie < 0].sum()
    if positivos == 0 and negativos == 0:
        return math.nan
    if negativos == 0:
        return math.inf
    return positivos / abs(negativos)


def expectancia(serie: pd.Series) -> float:
    """AGENTS.md §8.4: win_prob*avg_gain - loss_prob*abs(avg_loss).

    Algebraically identical to serie.mean() in every case, including the
    no-gain/no-loss edges where the decomposed formula would hit 0*NaN --
    the neutral-day term always contributes exactly 0 to the mean.
    """
    return serie.mean()


def ganho_medio(serie: pd.Series) -> float:
    ganhos = serie[serie > 0]
    return ganhos.mean() if len(ganhos) else math.nan


def perda_media(serie: pd.Series) -> float:
    perdas = serie[serie < 0]
    return perdas.mean() if len(perdas) else math.nan


def taxa_positivos(serie: pd.Series) -> float:
    return (serie > 0).sum() / len(serie) if len(serie) else math.nan


def taxa_negativos(serie: pd.Series) -> float:
    return (serie < 0).sum() / len(serie) if len(serie) else math.nan


def taxa_neutros(serie: pd.Series) -> float:
    return (serie == 0).sum() / len(serie) if len(serie) else math.nan


def percentil(serie: pd.Series, p: float) -> float:
    """p em [0, 100], interpolação linear (padrão pandas/numpy)."""
    return serie.quantile(p / 100)


def var_historico(serie: pd.Series, confianca: float = 0.95) -> float:
    """VaR histórico = quantile(1 - confianca).

    Convenção de sinal (AGENTS.md §8.10): valor bruto com sinal, perda como
    número negativo -- não convertido para magnitude positiva.
    """
    return serie.quantile(1 - confianca)


def expected_shortfall(serie: pd.Series, confianca: float = 0.95) -> float:
    """Média dos valores <= VaR histórico na mesma confiança."""
    limite = var_historico(serie, confianca)
    return serie[serie <= limite].mean()


def skewness(serie: pd.Series) -> float:
    """Assimetria amostral ajustada (Fisher-Pearson), igual pandas .skew()."""
    return serie.skew()


def kurtosis_excedente(serie: pd.Series) -> float:
    """Curtose em excesso amostral ajustada (normal = 0), igual pandas .kurt()."""
    return serie.kurt()


def maior_sequencia(serie: pd.Series, positivo: bool) -> int:
    """Comprimento da maior corrida de valores estritamente positivos
    (ou negativos, se positivo=False) consecutivos. Um valor exatamente
    zero quebra a sequência em ambos os sentidos."""
    alvo = serie > 0 if positivo else serie < 0
    grupos = (alvo != alvo.shift()).cumsum()
    tamanhos = alvo.groupby(grupos).sum()
    return int(tamanhos.max()) if len(tamanhos) else 0


def maior_sequencia_detalhada(
    serie: pd.Series,
    positivo: bool,
    datas_inicio: pd.Series = None,
    datas_fim: pd.Series = None,
) -> dict:
    """Como maior_sequencia, mas retorna também o valor total somado na
    corrida recorde e o início/fim dessa corrida. Por padrão usa o próprio
    índice de `serie` para início/fim; passe `datas_inicio`/`datas_fim`
    (indexadas como `serie`) quando cada elemento tiver seu próprio
    início/fim distintos -- caso de trades, onde um trade pode abrir e
    fechar em instantes diferentes. Quando não há nenhuma ocorrência,
    retorna início/fim None em vez de inventar uma data/posição."""
    alvo = serie > 0 if positivo else serie < 0
    grupos = (alvo != alvo.shift()).cumsum()

    tamanhos = alvo.groupby(grupos).sum()
    tamanhos = tamanhos[tamanhos > 0]
    if tamanhos.empty:
        return {"comprimento": 0, "valor_total": 0.0, "inicio": None, "fim": None}

    grupo_recorde = tamanhos.idxmax()
    mascara_recorde = grupos == grupo_recorde
    indices_recorde = serie.index[mascara_recorde]

    if datas_inicio is not None:
        inicio = datas_inicio.loc[indices_recorde[0]]
        fim = datas_fim.loc[indices_recorde[-1]]
    else:
        inicio, fim = indices_recorde[0], indices_recorde[-1]

    return {
        "comprimento": int(tamanhos.max()),
        "valor_total": serie.loc[mascara_recorde].sum(),
        "inicio": inicio,
        "fim": fim,
    }


def sharpe(serie: pd.Series, periodos_por_ano: int = DIAS_UTEIS_ANO_PADRAO) -> float:
    desvio = serie.std()
    if not desvio or pd.isna(desvio):
        return math.nan
    return serie.mean() / desvio * math.sqrt(periodos_por_ano)


def desvio_padrao(serie: pd.Series) -> float:
    """Desvio-padrão amostral (ddof=1) -- AGENTS.md épico 4.3."""
    return serie.std()


def downside_deviation(serie: pd.Series) -> float:
    """Desvio-padrão amostral (ddof=1) só dos valores negativos -- AGENTS.md
    épico 4.3. Mesmo cálculo já usado dentro de sortino(); exposta aqui
    como métrica nomeada própria."""
    perdas = serie[serie < 0]
    return perdas.std() if len(perdas) > 1 else math.nan


def sortino(serie: pd.Series, periodos_por_ano: int = DIAS_UTEIS_ANO_PADRAO) -> float:
    desvio_perdas = downside_deviation(serie)
    if not desvio_perdas or pd.isna(desvio_perdas):
        return math.nan
    return serie.mean() / desvio_perdas * math.sqrt(periodos_por_ano)


def retorno_anualizado(serie: pd.Series) -> float:
    """Retorno total / anos corridos (dias corridos entre a primeira e a
    última data do índice, / 365.25)."""
    n_anos = (serie.index.max() - serie.index.min()).days / 365.25
    if n_anos <= 0:
        return math.nan
    return serie.sum() / n_anos


def calmar(serie: pd.Series, max_drawdown_valor: float) -> float:
    """Retorno anualizado / |Maximum Drawdown|. Recebe o Maximum Drawdown
    já calculado (tradefolio.drawdowns.maximo_drawdown) em vez de
    recalculá-lo, para não acoplar este módulo a drawdowns.py."""
    if not max_drawdown_valor:
        return math.nan
    return retorno_anualizado(serie) / abs(max_drawdown_valor)


def recovery_factor(serie: pd.Series, max_drawdown_valor: float) -> float:
    """Retorno total / |Maximum Drawdown|."""
    if not max_drawdown_valor:
        return math.nan
    return serie.sum() / abs(max_drawdown_valor)
