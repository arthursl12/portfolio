"""Monthly platform/subscription cost, tiered by contract count.

Not a B3 exchange fee (see `tradefolio.costs` for that -- a flat R$/
contract/leg charged on every order) -- this is a recurring monthly
charge that steps up in tiers as the robot's contract count grows (ex.
1-5 contracts costs X, 6-10 costs Y). Requested explicitly by the user,
outside the source PDFs' own épicos.

Design decisions (documented, not hidden -- AGENTS.md §8):

- Tiers are `[min_contratos, max_contratos]` with BOTH bounds inclusive
  (`max_contratos=None` = no upper bound). Overlapping tiers raise a
  `ValueError` at construction instead of picking a silent tie-break for
  an ambiguous boundary -- the user's own example ("1-5" and "5-8")
  overlaps at 5, so whoever defines the table must resolve that
  explicitly rather than have this module guess.
- The cost is debited on the LAST B3 TRADING SESSION of each calendar
  month present in `diario` -- the same "apuração no último pregão do
  mês" convention `tradefolio.vapo` and "lâmina ideal.pdf" §6 already
  use, not a new one invented here. Applies even on a NO_TRADE day (the
  subscription is owed whether or not the robot traded) and even for a
  partial month (same choice `tradefolio.monthly` already makes: process
  an incomplete month rather than discard it).
- A NEW, separate `custo_mensal` column -- never folded into `custo`
  (which stays B3-fees-only everywhere else in the codebase). `liquido`
  becomes `bruto - custo - custo_mensal`; `liquido_por_contrato` is
  rescaled by the same `contratos_referencia` so the two columns stay
  consistent with each other.
- Scoped to the whole-robot `diario` only, not the per-asset breakdown
  (`daily.agregar_diario_por_ativo`) -- a platform subscription isn't
  attributable to one leg of a multi-asset robot; splitting it would be
  a new, arbitrary convention.

Because this only touches `diario['liquido']`/`liquido_por_contrato`
(before any drawdown/metrics/monthly/limiar/vapo function runs), every
downstream calculation that already consumes those columns picks up the
monthly cost automatically -- no other module needs to change.
"""
import math
from dataclasses import dataclass


@dataclass(frozen=True)
class FaixaCustoMensal:
    min_contratos: int
    max_contratos: int | None  # None = sem limite superior
    custo_mensal: float


@dataclass(frozen=True)
class TabelaCustoMensal:
    faixas: tuple[FaixaCustoMensal, ...]

    def __post_init__(self):
        ordenadas = sorted(self.faixas, key=lambda f: f.min_contratos)
        for anterior, atual in zip(ordenadas, ordenadas[1:]):
            limite_sup_anterior = anterior.max_contratos if anterior.max_contratos is not None else math.inf
            if limite_sup_anterior >= atual.min_contratos:
                raise ValueError(
                    f"faixas de custo mensal sobrepostas: {anterior} e {atual} -- "
                    "resolva a fronteira explicitamente antes de construir a tabela"
                )

    def custo_para(self, n_contratos: int) -> float:
        for faixa in self.faixas:
            limite_sup = faixa.max_contratos if faixa.max_contratos is not None else math.inf
            if faixa.min_contratos <= n_contratos <= limite_sup:
                return faixa.custo_mensal
        raise ValueError(
            f"nenhuma faixa de custo mensal cobre {n_contratos} contratos -- "
            f"faixas definidas: {self.faixas}"
        )


def custo_mensal_zero() -> TabelaCustoMensal:
    """Convenience para quando o usuário opta por não ter custo mensal
    (AGENTS.md §8: 0 é uma escolha explícita, não um padrão inventado)."""
    return TabelaCustoMensal(faixas=(FaixaCustoMensal(1, None, 0.0),))


def aplicar_custo_mensal(diario, tabela: TabelaCustoMensal, contratos_referencia: int):
    """Debita o custo mensal (da faixa correspondente a
    `contratos_referencia`) no último pregão B3 de cada mês presente em
    `diario` -- ver docstring do módulo para as convenções. `diario`
    precisa já estar alinhado no calendário B3
    (`tradefolio.alignment.preencher_calendario_b3`)."""
    custo = tabela.custo_para(contratos_referencia)
    diario = diario.copy()
    diario["custo_mensal"] = 0.0
    if custo == 0.0:
        return diario

    ultimos_pregoes = diario.groupby(diario.index.to_period("M")).apply(lambda g: g.index.max())
    diario.loc[ultimos_pregoes, "custo_mensal"] = custo
    diario.loc[ultimos_pregoes, "liquido"] -= custo
    diario.loc[ultimos_pregoes, "liquido_por_contrato"] -= custo / contratos_referencia
    return diario
