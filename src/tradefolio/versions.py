"""Methodology versioning (AGENTS.md épico 0, tarefa 0.3).

Every pipeline stage that exists gets an explicit version tag, bumped
whenever its formula or convention changes -- this is what
`tradefolio.metric_registry` references so a consumer (human or AI) can
tell which formula version produced a given number. Stages that don't
exist yet in this codebase are listed as None rather than given an
invented version: a version tag implies "this formula is frozen and
documented," which isn't true for code that hasn't been written.
"""

VERSOES = {
    # implementadas
    "parser_ordens": "smarttbot_orders_v2",  # v2: BOM UTF-8 + deteccao de delimitador
    "validacao": "validacao_v2",  # v2: Status/canceladas, UNKNOWN_ASSET, QUANTITY_MISMATCH, INVALID_MONETARY_VALUE
    "agregacao_diaria": "daily_v2",  # v2: exclui ordens nao executadas (Status != "executada")
    "calendario_b3": "alignment_v1",
    "consolidacao_mensal": "monthly_v1",
    "reconstrucao_trades": "trades_v2",  # v2: pula ordens nao executadas (evitava trade fantasma)
    "custos": "custos_v1",
    "metricas": "metrics_v1",
    "drawdowns": "drawdowns_v1",
    "limiar": "limiar_v1",  # decompor_limiar (P95/P99 toggle, reserva = % da margem) + rlt_*/normalizar_por_limiar
    # não implementadas ainda -- ver roadmap (Épicos 6-10 da lâmina ideal)
    "vapo": None,
    "monte_carlo": None,
    "deterioracao": None,
    "portfolio": None,
    "score": None,
    "alertas": None,
}
