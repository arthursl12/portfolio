"""Threshold ("limiar") engine -- AGENTS.md épico 6.

Only tarefas 6.3 (history-uncertainty premium) and 6.4 (rounding) are
implemented here. Tarefas 6.1/6.2/6.5 (the full threshold decomposition
-- minimum_margin + tail_drawdown_reserve + uncertainty_premium +
operational_reserve -- and its named profiles) are deliberately NOT
implemented: they require deciding, before writing any formula, which
percentile (P95 or P99), on which series (raw R$ drawdown? % of capital?
per contract?), deteriorated or not, and what the operational_reserve
even is -- none of that is specified precisely enough in the source PDF
to implement without inventing a financial convention (AGENTS.md §8/§24).
"""
import math

_DEGRAUS_INCERTEZA = (
    (6, math.inf),
    (9, 2.0),
    (12, 1.5),
    (24, 1.2),
    (36, 1.1),
)


def history_uncertainty_multiplier(months: int) -> float:
    """Prêmio por histórico curto (AGENTS.md épico 6.3), exatamente os
    degraus do PDF-fonte. Política configurável, não verdade estatística
    -- o próprio PDF exige que isso fique explícito."""
    for limite, multiplicador in _DEGRAUS_INCERTEZA:
        if months < limite:
            return multiplicador
    return 1.0


def arredondar_limiar(valor_bruto: float, increment: float, margem: float = None) -> float:
    """`recommended_threshold = ceil(raw_threshold / increment) * increment`
    (AGENTS.md épico 6.4). `increment` é um valor absoluto em R$ (ex. 500,
    1000) OU, se `margem` for informada, uma fração da margem (ex. 0.10
    para 10% de `margem`)."""
    incremento_absoluto = increment * margem if margem is not None else increment
    return math.ceil(valor_bruto / incremento_absoluto) * incremento_absoluto
