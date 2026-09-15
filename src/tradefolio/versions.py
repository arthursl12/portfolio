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
    "ingestao_resultados_diarios": "daily_results_v1",  # formato alternativo p/ robos sem export order-level (ex. TradingX) -- carregar_resultados_diarios/montar_diario_resultados/eh_formato_resultados_diarios; bruto/custo/n_trades ficam NaN (desconhecidos, nao inventados), contratos_referencia=1 fixo (decisao do usuario, nao detectada), pagina 2 (trade-level) nao suportada neste formato
    "validacao": "validacao_v2",  # v2: Status/canceladas, UNKNOWN_ASSET, QUANTITY_MISMATCH, INVALID_MONETARY_VALUE
    "agregacao_diaria": "daily_v2",  # v2: exclui ordens nao executadas (Status != "executada")
    "calendario_b3": "alignment_v1",
    "consolidacao_mensal": "monthly_v1",
    "reconstrucao_trades": "trades_v2",  # v2: pula ordens nao executadas (evitava trade fantasma)
    "custos": "custos_v1",
    "custo_mensal": "custo_mensal_v1",  # assinatura/plataforma em degraus por faixa de contratos, pedido do usuario (fora dos epicos do PDF-fonte)
    "metricas": "metrics_v1",
    "drawdowns": "drawdowns_v1",
    "limiar": "limiar_v1",  # decompor_limiar (P95/P99 toggle, reserva = % da margem) + rlt_*/normalizar_por_limiar
    "concentracao": "concentracao_v1",  # participacao_top_n, resultado_sem_top_n, detectar_alertas_curva, etc.
    "vapo": "vapo_v1",  # PoliticaPisoFixo + gerar_serie_vapo (tarefas 7.1/7.3/7.4); outras 6 politicas de 7.2 nao implementadas
    "monte_carlo": "monte_carlo_v1",  # circular_block_bootstrap (tarefas 8.1/8.2 unificadas) + resumo_trajetorias (8.4)
    "deterioracao": "deterioracao_v1",  # reduzir_ganhos/ampliar_perdas/remover_melhores/duplicar_piores/aumentar_custos/aplicar_slippage (tarefa 8.3)
    "portfolio": "portfolio_v2",  # v2: contribuicao_marginal/otimizar_portfolio agora default usar_janela_comum=True (restringe a janela comum de existencia, nao mais uniao) -- muda o DEFAULT numerico dessas duas funcoes (pedido de acompanhamento do usuario); uniao ainda disponivel via usar_janela_comum=False. +restringir_janela_comum, +robustez_portfolio (reusa monte_carlo.circular_block_bootstrap/resumo_trajetorias multi-coluna, nenhuma formula nova), +buscar_combinacoes_portfolio/selecionar_melhores_combinacoes (busca discreta separada da selecao por objetivo), +fronteira_pareto (fronteira de Pareto discreta sobre a busca ja calculada -- Markowitz avaliado e descartado, ver docstring), sincronizar_portfolio/metricas_agregadas (+tuw/pior dia/pior mes/lucro mensal)/6 variantes de correlacao/rlt_e_risco_portfolio/limiar_agregado/beneficio_diversificacao (tarefas 10.1/10.2/10.3-quase completa/10.4-completa/10.5/10.6/10.7/10.8-parcial)
    # não implementadas ainda -- ver roadmap (Épicos 6-10 da lâmina ideal)
    "score": None,
    "alertas": None,
}
