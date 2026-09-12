"""Threshold ("limiar") engine -- AGENTS.md épicos 4.2/4.4 and 6.

Épico 6 (tarefas 6.1/6.3/6.4/6.5, full decomposition) is implemented. The
two conventions tarefa 6.1 needed -- which the source PDF left
ambiguous -- were resolved by the user rather than invented here:

- Tail drawdown reserve: `abs(percentile(drawdown_serie, 100 - p))` on
  the caller-supplied drawdown series, with `percentil_cauda` a required
  *toggle* between 95 and 99 -- not a single hardcoded choice ("Use
  both. I mean, have a toggle button somewhere").
- Operational reserve: `fracao_reserva_operacional * minimum_margin`,
  a percentage of the margin -- not a flat R$ amount ("Percentage of
  minimum_margin").

The uncertainty premium is *derived* from history_uncertainty_multiplier
rather than a separate free parameter: it is the extra amount the
multiplier adds on top of the raw tail reserve
(`tail_drawdown_reserve - raw_tail_reserve`), so a robot with enough
history (multiplier 1.0) shows zero premium instead of a phantom
non-zero term.

Tarefa 6.2 (named profiles Técnico/Histórico/Prudente/Personalizado) is
NOT implemented as separate functions -- per AGENTS.md's own
no-premature-abstraction guidance, a "profile" is just a fixed choice of
`percentil_cauda`/`fracao_reserva_operacional` passed to
`decompor_limiar`; adding four trivial wrapper functions would be
abstraction the task doesn't need. Whoever wires up the profile picker
in a report/UI layer should map profile names to those two parameters
directly.

Scale convention (confirmed with the user in a follow-up question, after
decompor_limiar already existed): `minimum_margin` is for the TOTAL
configured position, not per contract. So every `drawdown_serie`/return
series fed into this module's functions for a real threshold/RLT
calculation must be on the TOTAL scale (`diario['liquido']`), not
`liquido_por_contrato` -- mixing the two breaks the ratio, the same
basis-consistency risk already documented in tradefolio.drawdowns.

Tarefas 4.2 (RLT -- `rlt_acumulado`/`rlt_mensal`/`rlt_anualizado`/
`rlt_movel`) and 4.4 (`normalizar_por_limiar`, generic per AGENTS.md
§8.1: same division serves both retorno and risco figures) are pure
functions that take an already-computed `limiar` float -- they are NOT
wired into `report_data.calcular_pagina1/2/3` automatically. That's
deliberate: a real `limiar` needs `StrategyConfiguration.minimum_margin`
(tradefolio.domain, Épico 2), and Épico 2's own resolved scope keeps
`domain.py` additive, never feeding back into the functional pipeline.
Whoever holds both a `StrategyConfiguration` and a `calcular_pagina1/3`
result composes these functions externally.
"""
import math

import pandas as pd

from tradefolio import metrics

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


_PERCENTIS_CAUDA_VALIDOS = (95, 99)


def decompor_limiar(
    minimum_margin: float,
    drawdown_serie: pd.Series,
    meses_historico: float,
    percentil_cauda: int = 95,
    fracao_reserva_operacional: float = 0.0,
    increment: float = None,
) -> dict:
    """Decompõe o limiar recomendado em seus termos (AGENTS.md épicos 6.1 e
    6.5): `minimum_margin + tail_drawdown_reserve + uncertainty_premium +
    operational_reserve`. Ver docstring do módulo para a origem das duas
    convenções (percentil como toggle, reserva operacional como % da
    margem) -- decisões do usuário, não inventadas aqui.

    `drawdown_serie` é a série de drawdown já calculada (per contrato, R$
    -- ver tradefolio.drawdowns.drawdown), não a equity bruta: este módulo
    não deve decidir qual curva usar, apenas compor o que recebe.
    """
    if percentil_cauda not in _PERCENTIS_CAUDA_VALIDOS:
        raise ValueError(
            f"percentil_cauda deve ser um de {_PERCENTIS_CAUDA_VALIDOS}, recebido {percentil_cauda}"
        )

    reserva_cauda_bruta = abs(metrics.percentil(drawdown_serie, 100 - percentil_cauda))
    multiplicador = history_uncertainty_multiplier(meses_historico)
    reserva_cauda_ajustada = reserva_cauda_bruta * multiplicador
    premio_incerteza = reserva_cauda_ajustada - reserva_cauda_bruta
    reserva_operacional = fracao_reserva_operacional * minimum_margin
    limiar_bruto = minimum_margin + reserva_cauda_ajustada + reserva_operacional

    resultado = {
        "minimum_margin": minimum_margin,
        "percentil_cauda": percentil_cauda,
        "uncertainty_multiplier": multiplicador,
        "tail_drawdown_reserve": reserva_cauda_ajustada,
        "uncertainty_premium": premio_incerteza,
        "operational_reserve": reserva_operacional,
        "limiar_bruto": limiar_bruto,
    }
    if increment is not None:
        resultado["limiar_recomendado"] = arredondar_limiar(limiar_bruto, increment)
    return resultado


def normalizar_por_limiar(valor: float, limiar: float) -> float:
    """`valor / limiar`, genérica (AGENTS.md §8.1) -- mesma fórmula serve
    tanto para retorno (RLT, tarefa 4.2, ver rlt_acumulado) quanto para
    risco (tarefa 4.4: MDD/L, Pior dia/L, ES95/L, Ulcer/L, Pior mês/L).
    NaN se `limiar` for 0 (nunca deveria acontecer na prática -- um
    limiar real é sempre positivo -- mas evita ZeroDivisionError em vez
    de inventar um valor)."""
    if not limiar:
        return math.nan
    return valor / limiar


def rlt_acumulado(retorno_total: float, limiar: float) -> float:
    """AGENTS.md épico 4.2: retorno acumulado / limiar.

    Escala confirmada com o usuário: `limiar` (via decompor_limiar) e
    `retorno_total` devem estar na mesma base -- minimum_margin é da
    POSIÇÃO TOTAL, não por contrato, então `retorno_total` deve vir de
    `diario['liquido']` (total), não de `liquido_por_contrato`.
    """
    return normalizar_por_limiar(retorno_total, limiar)


def rlt_mensal(liquido_mensal: pd.Series, limiar: float) -> pd.Series:
    """Como rlt_acumulado, mas uma razão por mês (mesmo `limiar` fixo como
    denominador em todos os meses -- não recalculado por período)."""
    if not limiar:
        return pd.Series(math.nan, index=liquido_mensal.index)
    return liquido_mensal / limiar


def rlt_anualizado(serie_diaria: pd.Series, limiar: float) -> float:
    """Retorno anualizado (tradefolio.metrics.retorno_anualizado) / limiar."""
    if not limiar:
        return math.nan
    return metrics.retorno_anualizado(serie_diaria) / limiar


def rlt_movel(liquido_mensal: pd.Series, limiar: float, janela_meses: int) -> pd.Series:
    """RLT sobre a soma móvel de `janela_meses` meses (AGENTS.md épico 4.2
    "móvel 3-6-12m") -- uma função genérica com a janela como parâmetro
    (AGENTS.md §8.1), não três funções fixas. Os primeiros `janela_meses -
    1` meses ficam NaN (janela incompleta), não um número inventado."""
    if not limiar:
        return pd.Series(math.nan, index=liquido_mensal.index)
    return liquido_mensal.rolling(janela_meses).sum() / limiar
