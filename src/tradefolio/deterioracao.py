"""Deterioration scenarios (AGENTS.md épico 8, tarefa 8.3).

Six independent, composable transformations on a daily result series --
"permitir independentemente" in the source PDF, not one combined
function. All are Series-in, Series-out (same index, same length) so
they chain with plain function composition and feed directly into
`tradefolio.monte_carlo.circular_block_bootstrap`, e.g.:

    circular_block_bootstrap(
        ampliar_perdas(reduzir_ganhos(serie, 0.10), 0.10), ...
    )

which reproduces "lâmina ideal.pdf" §10's deterioration grid (reduction
of gains x amplification of losses, 0/10/20/30%) once bootstrapped and
summarized -- that composition itself (a heatmap of Monte Carlo runs per
grid cell) is not built here, only the two transforms it would combine.

Design decisions (documented, not hidden -- AGENTS.md §8):

- `reduzir_ganhos`/`ampliar_perdas` only touch strictly positive/negative
  days respectively -- a day at exactly zero is untouched (same
  "sequence break" convention already used by `metrics.maior_sequencia`).
- `remover_melhores_dias` ZEROES (doesn't delete) the N largest values --
  the series must keep its original index/length to keep feeding
  drawdown/bootstrap correctly.
- `duplicar_piores_dias`: the source PDF gives no single literal
  definition ("duplicate" the day in place, or insert a new date?).
  Chosen: double the value IN PLACE (multiply by 2) -- inserting a new
  date would require deciding where on the B3 calendar it lands,
  breaking alignment with `alignment.preencher_calendario_b3`.
- `aumentar_custos`/`aplicar_slippage` take the component series
  (`bruto`/`custo`/`n_trades`) rather than a whole `diario`, keeping the
  same Series-in/Series-out shape as the other four. This also sidesteps
  deciding whether an eventual `custo_mensal` (the user's own monthly
  subscription feature, unrelated to this PDF task) should be included:
  "aumento de custos" here is about B3 trading costs only.
"""
import pandas as pd


def _validar_fracao_nao_negativa(fracao: float, nome: str) -> None:
    if fracao < 0:
        raise ValueError(f"{nome} não pode ser negativa, recebido {fracao}")


def reduzir_ganhos(serie: pd.Series, fracao: float) -> pd.Series:
    """Multiplica os dias estritamente positivos por `(1 - fracao)`.
    `fracao=0.10` reduz os ganhos em 10%."""
    _validar_fracao_nao_negativa(fracao, "fracao")
    ajustada = serie.copy()
    ajustada[ajustada > 0] *= (1 - fracao)
    return ajustada


def ampliar_perdas(serie: pd.Series, fracao: float) -> pd.Series:
    """Multiplica os dias estritamente negativos por `(1 + fracao)` --
    torna-os mais negativos. `fracao=0.10` amplia as perdas em 10%."""
    _validar_fracao_nao_negativa(fracao, "fracao")
    ajustada = serie.copy()
    ajustada[ajustada < 0] *= (1 + fracao)
    return ajustada


def remover_melhores_dias(serie: pd.Series, n: int) -> pd.Series:
    """Zera os N maiores valores da série (não remove a data)."""
    ajustada = serie.copy()
    ajustada.loc[serie.nlargest(n).index] = 0.0
    return ajustada


def duplicar_piores_dias(serie: pd.Series, n: int) -> pd.Series:
    """Dobra (multiplica por 2) o valor dos N menores (mais negativos)
    dias, NO LUGAR -- ver docstring do módulo para por que não insere
    uma data nova."""
    ajustada = serie.copy()
    piores = serie.nsmallest(n).index
    ajustada.loc[piores] = ajustada.loc[piores] * 2
    return ajustada


def aumentar_custos(bruto: pd.Series, custo: pd.Series, fracao: float) -> pd.Series:
    """Aumenta o custo B3 em `(1 + fracao)` e recomputa o líquido
    (`bruto - custo_novo`). `fracao=0.5`/`1.0` reproduzem os cenários
    "custos +50%"/"custos +100%" da "lâmina ideal.pdf" §10."""
    _validar_fracao_nao_negativa(fracao, "fracao")
    return bruto - custo * (1 + fracao)


def aplicar_slippage(liquido: pd.Series, n_trades: pd.Series, valor_por_trade: float) -> pd.Series:
    """Custo extra fixo por trade (`n_trades * valor_por_trade`),
    subtraído do líquido -- um componente de custo adicional ao
    emolumento B3 (`tradefolio.costs`), não um substituto dele."""
    if valor_por_trade < 0:
        raise ValueError(f"valor_por_trade não pode ser negativo, recebido {valor_por_trade}")
    return liquido - n_trades * valor_por_trade
