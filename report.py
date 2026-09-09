import base64
import io

import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from tradefolio.alignment import preencher_calendario_b3
from tradefolio.daily import agregar_diario, detectar_contratos_referencia
from tradefolio.report_data import (
    montar_dataframe_diario,
    calcular_pagina1 as calcular_metricas_pagina1,
    calcular_pagina2 as calcular_metricas_pagina2,
    calcular_pagina3 as calcular_metricas_pagina3,
)
from tradefolio.loaders import carregar_ordens

CSV_PATH = "/mnt/user-data/uploads/orders_romanos.csv"


def fig_para_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def montar_figura_curva_drawdown(equity, drawdown, rotulo_valor="R$/contrato"):
    """Constrói a figura (não fecha, não codifica) -- reaproveitada tanto
    pelo relatório HTML estático (via gerar_grafico_curva_drawdown) quanto
    pela página Streamlit ao vivo (via st.pyplot)."""
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 5.5), sharex=True, height_ratios=[2.2, 1],
        gridspec_kw={"hspace": 0.08},
    )

    ax1.plot(equity.index, equity.values, color="#1f6feb", linewidth=1.3)
    ax1.fill_between(equity.index, equity.values, 0, color="#1f6feb", alpha=0.07)
    ax1.set_ylabel(f"Equity ({rotulo_valor})")
    ax1.grid(alpha=0.25)
    ax1.set_title(f"Curva de capital e drawdown — {rotulo_valor}", fontsize=12, loc="left")

    ax2.fill_between(drawdown.index, drawdown.values, 0, color="#d1242f", alpha=0.35)
    ax2.plot(drawdown.index, drawdown.values, color="#d1242f", linewidth=0.8)
    ax2.set_ylabel(f"Drawdown ({rotulo_valor})")
    ax2.grid(alpha=0.25)

    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b/%y"))
    fig.autofmt_xdate()

    return fig


def gerar_grafico_curva_drawdown(equity, drawdown) -> str:
    return fig_para_base64(montar_figura_curva_drawdown(equity, drawdown))


def fmt(v, casas=2, pct=False, moeda=False):
    if v is None or (isinstance(v, float) and (v != v)):
        return "—"
    if pct:
        return f"{v*100:.1f}%"
    if moeda:
        return f"R$ {v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{v:.{casas}f}"


def gerar_tabela_drawdowns(episodios, coluna_contagem: str = "pregoes_ate_fundo") -> str:
    linhas = []
    for _, e in episodios.iterrows():
        rec = e["data_recuperacao"].strftime("%d/%m/%Y") if e["recuperado"] else "não recuperado"
        linhas.append(
            f"<tr><td>{e['inicio_pico'].strftime('%d/%m/%Y')}</td>"
            f"<td>{e['data_fundo'].strftime('%d/%m/%Y')}</td>"
            f"<td class='valor'>{fmt(e['profundidade_rs'], moeda=True)}</td>"
            f"<td>{rec}</td>"
            f"<td class='valor'>{int(e[coluna_contagem])}</td>"
            f"<td class='valor'>{'—' if pd.isna(e['duracao_total_pregoes']) else int(e['duracao_total_pregoes'])}</td></tr>"
        )
    return "\n".join(linhas)


def gerar_secao_pagina2(p2: dict) -> str:
    tabela = gerar_tabela_drawdowns(p2["episodios_drawdown"], "pregoes_ate_fundo")
    tabela_tuw = gerar_tabela_drawdowns(p2["piores_tuw"], "pregoes_ate_fundo")

    def fmt_seq(s, moeda_2c=True):
        if s["comprimento"] == 0:
            return "—"
        periodo = f"{s['inicio'].strftime('%d/%m/%Y')} a {s['fim'].strftime('%d/%m/%Y')}"
        return f"{s['comprimento']} ({fmt(s['valor_total'], moeda=True)}) &middot; {periodo}"

    return f"""
    <h2>Página 2 — Drawdown e sequências</h2>
    <table>
      <tr><td class="rotulo">Maior sequência positiva (trades, 2 contratos)</td><td class="valor">{fmt_seq(p2['maior_sequencia_positiva_trades'])}</td></tr>
      <tr><td class="rotulo">Maior sequência negativa (trades, 2 contratos)</td><td class="valor">{fmt_seq(p2['maior_sequencia_negativa_trades'])}</td></tr>
      <tr><td class="rotulo">Maior sequência positiva (dias, por contrato)</td><td class="valor">{fmt_seq(p2['maior_sequencia_positiva_dias'])}</td></tr>
      <tr><td class="rotulo">Maior sequência negativa (dias, por contrato)</td><td class="valor">{fmt_seq(p2['maior_sequencia_negativa_dias'])}</td></tr>
    </table>

    <h3 style="margin-top:22px; font-size:14px;">Top 10 episódios de drawdown (por contrato)</h3>
    <table>
      <tr>
        <th>Início (pico)</th><th>Fundo</th><th>Profundidade</th>
        <th>Recuperação</th><th>Pregões até fundo</th><th>Duração total</th>
      </tr>
      {tabela}
    </table>

    <h3 style="margin-top:22px; font-size:14px;">Top 10 piores Time Under Water (por contrato)</h3>
    <table>
      <tr>
        <th>Início (pico)</th><th>Fundo</th><th>Profundidade</th>
        <th>Recuperação</th><th>Pregões até fundo</th><th>Duração total</th>
      </tr>
      {tabela_tuw}
    </table>
    """


def montar_figura_distribuicao(p3: dict):
    """Constrói a figura (não fecha, não codifica) -- reaproveitada tanto
    pelo relatório HTML estático quanto pela página Streamlit ao vivo."""
    serie = p3["serie"]
    fig, (ax1, ax2) = plt.subplots(
        1, 2, figsize=(10, 3.6), gridspec_kw={"width_ratios": [2.3, 1]},
    )

    ax1.hist(serie, bins=40, color="#1f6feb", alpha=0.75)
    ax1.axvline(p3["media"], color="#d1242f", linestyle="--", linewidth=1.2, label=f"Média ({p3['media']:.0f})")
    ax1.axvline(p3["mediana"], color="#1a7f37", linestyle="--", linewidth=1.2, label=f"Mediana ({p3['mediana']:.0f})")
    ax1.set_title("Distribuição do resultado diário (R$/contrato)", fontsize=11, loc="left")
    ax1.legend(fontsize=8, frameon=False)
    ax1.grid(alpha=0.2)

    ax2.boxplot(serie, vert=True, widths=0.5, patch_artist=True,
                boxprops=dict(facecolor="#dbeafe", color="#1f6feb"),
                medianprops=dict(color="#d1242f"))
    ax2.set_title("Boxplot", fontsize=11)
    ax2.set_xticks([])
    ax2.grid(alpha=0.2)

    fig.tight_layout()
    return fig


def gerar_grafico_distribuicao(p3: dict) -> str:
    return fig_para_base64(montar_figura_distribuicao(p3))


def gerar_secao_pagina3(p3: dict) -> str:
    pct = p3["percentis"]
    piores = "".join(f"<li>{d.strftime('%d/%m/%Y')}: {fmt(v, moeda=True)}</li>" for d, v in p3["piores_5"].items())
    melhores = "".join(f"<li>{d.strftime('%d/%m/%Y')}: {fmt(v, moeda=True)}</li>" for d, v in p3["melhores_5"].items())
    return f"""
    <h2>Página 3 — Distribuição e cauda</h2>
    <table>
      <tr><td class="rotulo">Média diária</td><td class="valor">{fmt(p3['media'], moeda=True)}</td></tr>
      <tr><td class="rotulo">Mediana diária</td><td class="valor">{fmt(p3['mediana'], moeda=True)}</td></tr>
      <tr><td class="rotulo">Desvio-padrão diário</td><td class="valor">{fmt(p3['desvio_padrao'], moeda=True)}</td></tr>
      <tr><td class="rotulo">Skewness</td><td class="valor">{fmt(p3['skewness'], 3)}</td></tr>
      <tr><td class="rotulo">Kurtosis (excesso)</td><td class="valor">{fmt(p3['kurtosis'], 3)}</td></tr>
      <tr><td class="rotulo">Percentil 5% / 95%</td><td class="valor">{fmt(pct[5], moeda=True)} / {fmt(pct[95], moeda=True)}</td></tr>
      <tr><td class="rotulo">Percentil 1% / 99%</td><td class="valor">{fmt(pct[1], moeda=True)} / {fmt(pct[99], moeda=True)}</td></tr>
      <tr><td class="rotulo">VaR histórico 95% / 99%</td><td class="valor">{fmt(p3['var_95'], moeda=True)} / {fmt(p3['var_99'], moeda=True)}</td></tr>
      <tr><td class="rotulo">Expected Shortfall 95% / 99%</td><td class="valor">{fmt(p3['es_95'], moeda=True)} / {fmt(p3['es_99'], moeda=True)}</td></tr>
      <tr><td class="rotulo">Média dos 5 piores dias</td><td class="valor">{fmt(p3['piores_5_media'], moeda=True)}</td></tr>
      <tr><td class="rotulo">Média dos 5 melhores dias</td><td class="valor">{fmt(p3['melhores_5_media'], moeda=True)}</td></tr>
    </table>
    <p class="nota">5 piores pregões: {piores}</p>
    <p class="nota">5 melhores pregões: {melhores}</p>
    <p class="nota">Distribuição calculada sobre todos os pregões (inclui os {(p3['serie']==0).sum()} dias sem operação, que empilham massa em zero — isso afeta percentil 50, skewness e kurtosis).</p>
    """


def gerar_html(metricas: dict, grafico_b64: str, grafico_dist_b64: str = "", secao_pagina2: str = "", secao_pagina3: str = "", robo: str = "Romanos") -> str:
    p_ini, p_fim = metricas["periodo"]
    linhas = [
        ("Período", f"{p_ini.strftime('%d/%m/%Y')} a {p_fim.strftime('%d/%m/%Y')}"),
        ("Pregões", f"{metricas['pregoes']}"),
        ("Operações (trades reconstruídos)", f"{metricas['n_trades_reconstruidos']}"),
        ("Win rate (por trade)", fmt(metricas["win_rate_trades"], pct=True)),
        ("Lucro líquido (2 contratos)", fmt(metricas["lucro_liquido_2c"], moeda=True)),
        ("Lucro líquido por contrato", fmt(metricas["lucro_liquido_por_contrato"], moeda=True)),
        ("Resultado médio diário (por contrato)", fmt(metricas["media_diaria"], moeda=True)),
        ("Resultado mediano diário (por contrato)", fmt(metricas["mediana_diaria"], moeda=True)),
        ("% dias positivos", fmt(metricas["pct_dias_positivos"], pct=True)),
        ("% dias negativos", fmt(metricas["pct_dias_negativos"], pct=True)),
        ("% dias neutros (sem trade)", fmt(metricas["pct_dias_neutros"], pct=True)),
        ("Gain médio — dia (por contrato)", fmt(metricas["gain_medio"], moeda=True)),
        ("Loss médio — dia (por contrato)", fmt(metricas["loss_medio"], moeda=True)),
        ("Lucro médio — trade (2 contratos, líquido)", fmt(metricas["lucro_medio_trade"], moeda=True)),
        ("Prejuízo médio — trade (2 contratos, líquido)", fmt(metricas["prejuizo_medio_trade"], moeda=True)),
        ("Payoff (gain médio / |loss médio|)", fmt(metricas["payoff"])),
        ("Expectância diária (por contrato)", fmt(metricas["expectancia_diaria"], moeda=True)),
        ("Profit Factor (por trade, líquido)", fmt(metricas["profit_factor_trades"])),
        ("Pior dia (por contrato)", fmt(metricas["pior_dia"], moeda=True)),
        ("Melhor dia (por contrato)", fmt(metricas["melhor_dia"], moeda=True)),
        ("Retorno bruto %", fmt(metricas["retorno_bruto_pct"]) + "%"),
        ("Retorno líquido %", fmt(metricas["retorno_liquido_pct"]) + "%"),
        ("Maximum Drawdown (por contrato)", fmt(metricas["max_drawdown"], moeda=True)),
        ("Maximum Drawdown %**", fmt(metricas["max_drawdown_pct"]) + "%"),
        ("Time Under Water máximo", f"{metricas['time_under_water_max_pregoes']} pregões"),
        ("Ulcer Index %**", fmt(metricas["ulcer_index_pct"]) + "%"),
        ("Sharpe (anualizado)", fmt(metricas["sharpe"])),
        ("Sortino (anualizado)", fmt(metricas["sortino"])),
        ("Calmar", fmt(metricas["calmar"])),
        ("Recovery Factor", fmt(metricas["recovery_factor"])),
    ]

    linhas_html = "\n".join(
        f'<tr><td class="rotulo">{r}</td><td class="valor">{v}</td></tr>' for r, v in linhas
    )

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<title>Lâmina — {robo} — Página 1</title>
<style>
  body {{
    font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif;
    background: #f6f8fa;
    color: #1f2328;
    margin: 0;
    padding: 32px;
  }}
  .container {{
    max-width: 760px;
    margin: 0 auto;
    background: #fff;
    border: 1px solid #d0d7de;
    border-radius: 10px;
    padding: 28px 32px;
  }}
  h1 {{ font-size: 20px; margin-bottom: 2px; }}
  .subtitulo {{ color: #57606a; font-size: 13px; margin-bottom: 24px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
  td, th {{ padding: 7px 6px; border-bottom: 1px solid #eaeef2; }}
  th {{ text-align: left; font-size: 12px; color: #57606a; font-weight: 600; }}
  .rotulo {{ color: #444; }}
  .valor {{ text-align: right; font-variant-numeric: tabular-nums; font-weight: 600; }}
  h2 {{ font-size: 16px; margin-top: 32px; border-top: 1px solid #eaeef2; padding-top: 20px; }}
  img {{ width: 100%; border-radius: 6px; margin: 20px 0 8px 0; }}
  .nota {{ font-size: 11px; color: #8b949e; margin-top: 4px; }}
</style>
</head>
<body>
  <div class="container">
    <h1>Lâmina — Robô {robo}</h1>
    <div class="subtitulo">Simulador pessimista &middot; Página 1 — Resumo &middot; valores normalizados por contrato (padrão de backtest: 2 contratos)</div>

    <img src="data:image/png;base64,{grafico_b64}" alt="Curva de capital e drawdown">

    <table>
      {linhas_html}
    </table>

    {secao_pagina2}

    <img src="data:image/png;base64,{grafico_dist_b64}" alt="Distribuição do resultado diário">
    {secao_pagina3}

    <p class="nota">
      Ulcer Index e Maximum Drawdown % calculados com patrimônio = R$1.000/contrato (margem sugerida pelo autor) + resultado acumulado, drawdown% relativo ao pico móvel — mesma lógica da Smarttbot.<br>
      Trade reconstruído a partir da posição líquida (agrupa fills parciais); há 1 trade a menos que o reportado pela plataforma (~R$424, provavelmente anterior ao início do CSV) — assumido como aceitável.
    </p>
  </div>
</body>
</html>"""


if __name__ == "__main__":
    ordens = carregar_ordens(CSV_PATH)
    contratos_referencia = detectar_contratos_referencia(ordens)
    diario = preencher_calendario_b3(agregar_diario(ordens, contratos_referencia=contratos_referencia))

    metricas, equity, drawdown = calcular_metricas_pagina1(diario, contratos_referencia=contratos_referencia)
    grafico_b64 = gerar_grafico_curva_drawdown(equity, drawdown)

    p2 = calcular_metricas_pagina2(diario, ordens)
    metricas["n_trades_reconstruidos"] = p2["n_trades"]
    metricas["win_rate_trades"] = p2["win_rate_trades"]
    metricas["profit_factor_trades"] = p2["profit_factor_trades"]
    metricas["lucro_medio_trade"] = p2["lucro_medio_trade"]
    metricas["prejuizo_medio_trade"] = p2["prejuizo_medio_trade"]
    secao_pagina2 = gerar_secao_pagina2(p2)

    p3 = calcular_metricas_pagina3(diario)
    grafico_dist_b64 = gerar_grafico_distribuicao(p3)
    secao_pagina3 = gerar_secao_pagina3(p3)

    html = gerar_html(metricas, grafico_b64, grafico_dist_b64, secao_pagina2, secao_pagina3)

    out_path = "/mnt/user-data/outputs/lamina_romanos_pagina1.html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("Salvo em:", out_path)