"""Quick demo: gera uma lâmina a partir de um CSV de exemplo, sem precisar
de dados próprios. Funciona com qualquer CSV em dados_exemplo/ ou
tests/fixtures/ -- detecta automaticamente o número de contratos de
referência do próprio arquivo (tradefolio.daily.detectar_contratos_referencia),
em vez de assumir 2 (o valor do backtest do robô Romanos).

Uso:
    .venv/bin/python demo.py
"""
import report
from tradefolio.alignment import preencher_calendario_b3
from tradefolio.daily import agregar_diario, detectar_contratos_referencia

CSV_EXEMPLO = "tests/fixtures/romanos_orders.csv"
OUT_PATH = "lamina_exemplo.html"

if __name__ == "__main__":
    ordens = report.carregar_ordens(CSV_EXEMPLO)
    contratos_referencia = detectar_contratos_referencia(ordens)
    diario = preencher_calendario_b3(agregar_diario(ordens, contratos_referencia=contratos_referencia))

    metricas, equity, drawdown = report.calcular_metricas_pagina1(diario, contratos_referencia=contratos_referencia)
    grafico_b64 = report.gerar_grafico_curva_drawdown(equity, drawdown)

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
    print(f"Salvo em: {OUT_PATH} (contratos de referência detectados: {contratos_referencia})")
