"""B3 emolumento cost model.

Convention (CLAUDE.md > "Domain conventions validated against the Smarttbot
platform" > Costs): R$0.25 per contract, per leg. Both entrada and saída
legs of a round trip incur the fee, so callers must pass the total executed
quantity across all legs, not just the exit leg.
"""

CUSTO_POR_PERNA_PADRAO = 0.25


def custo_b3(quantidade_contratos: float, custo_por_perna: float = CUSTO_POR_PERNA_PADRAO) -> float:
    return quantidade_contratos * custo_por_perna
