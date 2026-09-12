"""Threshold ("limiar") engine -- AGENTS.md épico 6.

Tarefas 6.3 (history-uncertainty premium), 6.4 (rounding) and 6.1/6.5
(full decomposition) are implemented. The two conventions tarefa 6.1
needed -- which the source PDF left ambiguous -- were resolved by the
user rather than invented here:

- Tail drawdown reserve: `abs(percentile(drawdown_serie, 100 - p))` on
  the caller-supplied drawdown series (per-contract R$, same series
  tradefolio.drawdowns already produces), with `percentil_cauda` a
  required *toggle* between 95 and 99 -- not a single hardcoded choice
  ("Use both. I mean, have a toggle button somewhere").
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
