"""Quick demo: gera uma lâmina a partir do CSV de exemplo incluso no repositório
(tests/fixtures/romanos_orders.csv), sem precisar de dados próprios.

Uso:
    .venv/bin/python demo.py
"""
import report

CSV_EXEMPLO = "tests/fixtures/romanos_orders.csv"
OUT_PATH = "lamina_exemplo.html"

if __name__ == "__main__":
    diario = report.montar_dataframe_diario(CSV_EXEMPLO)
    metricas, equity, drawdown = report.calcular_metricas_pagina1(diario)
    grafico_b64 = report.gerar_grafico_curva_drawdown(equity, drawdown)

    ordens = report.carregar_ordens(CSV_EXEMPLO)
    p2 = report.calcular_metricas_pagina2(diario, ordens)
    metricas.update({
        "n_trades_reconstruidos": p2["n_trades"],
        "win_rate_trades": p2["win_rate_trades"],
        "profit_factor_trades": p2["profit_factor_trades"],
        "lucro_medio_trade": p2["lucro_medio_trade"],
        "prejuizo_medio_trade": p2["prejuizo_medio_trade"],
    })
    secao_pagina2 = report.gerar_secao_pagina2(p2)

    p3 = report.calcular_metricas_pagina3(diario)
    grafico_dist_b64 = report.gerar_grafico_distribuicao(p3)
    secao_pagina3 = report.gerar_secao_pagina3(p3)

    html = report.gerar_html(metricas, grafico_b64, grafico_dist_b64, secao_pagina2, secao_pagina3)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)
    print("Salvo em:", OUT_PATH)
