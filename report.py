import argparse
import base64
import html
import io

import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from tradefolio.alignment import preencher_calendario_b3
from tradefolio.daily import agregar_diario, detectar_contratos_referencia
from tradefolio.drawdowns import episodios_drawdown
from tradefolio.metric_registry import REGISTRO
from tradefolio.validation import extrair_raiz_ativo
from tradefolio.report_data import (
    montar_dataframe_diario,
    calcular_pagina1 as calcular_metricas_pagina1,
    calcular_pagina2 as calcular_metricas_pagina2,
    calcular_pagina3 as calcular_metricas_pagina3,
    calcular_pagina4 as calcular_metricas_pagina4,
    calcular_pagina5 as calcular_metricas_pagina5,
    calcular_pagina6 as calcular_metricas_pagina6,
)
from tradefolio.loaders import carregar_ordens


def ajuda(chave: str, default: str = "") -> str:
    """Texto de tooltip a partir do dicionário oficial de métricas
    (tradefolio.metric_registry) -- reusa a mesma fonte de verdade da
    interpretação de cada métrica (épico 0.1) em vez de duplicar a
    explicação em cada UI. `default` cobre valores que não são uma
    métrica registrada (inputs do usuário, campos estruturais)."""
    spec = REGISTRO.get(chave)
    return spec.interpretacao if spec else default


def rotulo_com_ajuda(rotulo: str, chave: str, default: str = "") -> str:
    """`<td class="rotulo">` com tooltip nativo do navegador (atributo
    `title`, mostrado no hover) -- usado em toda tabela HTML estática."""
    texto = html.escape(ajuda(chave, default))
    return f'<td class="rotulo" title="{texto}">{rotulo}</td>'


def fig_para_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# Cores por faixa de duração de período submerso (lâmina ideal.pdf §3):
# <=20 pregões amarelo, 21-60 laranja, >60 vermelho.
_COR_SUBMERSO_CURTO = "#fef3c7"
_COR_SUBMERSO_MEDIO = "#fed7aa"
_COR_SUBMERSO_LONGO = "#fecaca"


def _cor_por_duracao(duracao_pregoes: float) -> str:
    if pd.isna(duracao_pregoes) or duracao_pregoes <= 20:
        return _COR_SUBMERSO_CURTO
    if duracao_pregoes <= 60:
        return _COR_SUBMERSO_MEDIO
    return _COR_SUBMERSO_LONGO


def montar_figura_curva_drawdown(equity, drawdown, rotulo_valor="R$/contrato", episodios=None):
    """Constrói a figura (não fecha, não codifica) -- reaproveitada tanto
    pelo relatório HTML estático (via gerar_grafico_curva_drawdown) quanto
    pela página Streamlit ao vivo (via st.pyplot).

    `episodios` (opcional, de tradefolio.drawdowns.calcular_episodios_drawdown
    ou episodios_drawdown) adiciona as anotações do §3 da lâmina ideal:
    sombreado dos períodos submersos por faixa de duração, marcação de
    high-water marks (novos máximos da equity) e do melhor/pior dia
    (derivado de equity.diff(), já que só a curva acumulada é recebida
    aqui, não a série diária bruta). `None` (padrão) preserva o
    comportamento anterior sem nenhuma anotação nova."""
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(10, 5.5), sharex=True, height_ratios=[2.2, 1],
        gridspec_kw={"hspace": 0.08},
    )

    if episodios is not None and len(episodios):
        for _, ep in episodios.iterrows():
            fim = ep["data_recuperacao"] if ep["recuperado"] else equity.index[-1]
            cor = _cor_por_duracao(ep["duracao_total_pregoes"])
            ax1.axvspan(ep["inicio_pico"], fim, color=cor, alpha=0.5, zorder=0)

        maximas_moveis = equity.cummax()
        novos_maximos = equity[equity == maximas_moveis]
        ax1.scatter(
            novos_maximos.index, novos_maximos.values, color="#1a7f37", s=10,
            zorder=3, label="Novo máximo (high-water mark)",
        )

        retornos_diarios = equity.diff()
        retornos_diarios.iloc[0] = equity.iloc[0]
        data_melhor, data_pior = retornos_diarios.idxmax(), retornos_diarios.idxmin()
        ax1.scatter([data_melhor], [equity.loc[data_melhor]], color="#1a7f37", marker="^", s=70, zorder=4, label="Melhor dia")
        ax1.scatter([data_pior], [equity.loc[data_pior]], color="#d1242f", marker="v", s=70, zorder=4, label="Pior dia")
        ax1.legend(fontsize=7, frameon=False, loc="upper left")

    ax1.plot(equity.index, equity.values, color="#1f6feb", linewidth=1.3, zorder=2)
    ax1.fill_between(equity.index, equity.values, 0, color="#1f6feb", alpha=0.07, zorder=1)
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
      <tr>{rotulo_com_ajuda('Maior sequência positiva (trades, 2 contratos)', 'maior_sequencia_positiva_trades')}<td class="valor">{fmt_seq(p2['maior_sequencia_positiva_trades'])}</td></tr>
      <tr>{rotulo_com_ajuda('Maior sequência negativa (trades, 2 contratos)', 'maior_sequencia_negativa_trades')}<td class="valor">{fmt_seq(p2['maior_sequencia_negativa_trades'])}</td></tr>
      <tr>{rotulo_com_ajuda('Maior sequência positiva (dias, por contrato)', 'maior_sequencia_positiva_dias')}<td class="valor">{fmt_seq(p2['maior_sequencia_positiva_dias'])}</td></tr>
      <tr>{rotulo_com_ajuda('Maior sequência negativa (dias, por contrato)', 'maior_sequencia_negativa_dias')}<td class="valor">{fmt_seq(p2['maior_sequencia_negativa_dias'])}</td></tr>
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


def gerar_secao_pagina4(p4: dict) -> str:
    """Limiar (decomposição P95/P99), RLT e risco normalizado pelo limiar
    (lâmina ideal.pdf §4/5/7)."""
    ativo = p4["percentil_cauda_ativo"]

    _AJUDA_DECOMPOSICAO = {
        "minimum_margin": "Margem mínima informada pelo usuário (user_input) -- mesma para os dois percentis.",
        "tail_drawdown_reserve": "Percentil de cauda do drawdown (total, ver limiar_p95/limiar_p99) já ajustado pelo prêmio de histórico curto.",
        "uncertainty_premium": ajuda("limiar_p95") + " Este componente isola o quanto o multiplicador de histórico curto acrescenta sobre a reserva de cauda bruta.",
        "operational_reserve": "Percentual configurável (reserva operacional) da margem mínima -- resolução do usuário: '% de minimum_margin', não valor fixo.",
        "limiar_bruto": "Soma dos componentes acima, antes de arredondar.",
        "limiar_recomendado": "Limiar bruto arredondado para cima no incremento configurado.",
    }

    def linha_decomposicao(rotulo, chave):
        v95, v99 = p4["limiar_p95"][chave], p4["limiar_p99"][chave]
        marca95 = " ★" if ativo == 95 else ""
        marca99 = " ★" if ativo == 99 else ""
        titulo = html.escape(_AJUDA_DECOMPOSICAO.get(chave, ""))
        return (
            f"<tr><td class='rotulo' title=\"{titulo}\">{rotulo}</td>"
            f"<td class='valor'>{fmt(v95, moeda=True)}{marca95}</td>"
            f"<td class='valor'>{fmt(v99, moeda=True)}{marca99}</td></tr>"
        )

    limiar_recomendado_html = ""
    if "limiar_recomendado" in p4["limiar_p95"]:
        limiar_recomendado_html = linha_decomposicao("Limiar recomendado (arredondado)", "limiar_recomendado")

    return f"""
    <h2>Página 4 — Limiar e RLT (retorno sobre o limiar)</h2>
    <p class="nota">★ marca o percentil ativo (usado no restante desta página). Histórico: {fmt(p4['meses_historico'], 1)} meses.</p>
    <table>
      <tr><th></th><th>P95</th><th>P99</th></tr>
      {linha_decomposicao('Margem mínima', 'minimum_margin')}
      {linha_decomposicao('Reserva de cauda (drawdown)', 'tail_drawdown_reserve')}
      {linha_decomposicao('Prêmio por histórico curto', 'uncertainty_premium')}
      {linha_decomposicao('Reserva operacional', 'operational_reserve')}
      <tr><td class="rotulo" title="{html.escape(_AJUDA_DECOMPOSICAO['limiar_bruto'])}"><strong>Limiar bruto</strong></td><td class="valor"><strong>{fmt(p4['limiar_p95']['limiar_bruto'], moeda=True)}</strong></td><td class="valor"><strong>{fmt(p4['limiar_p99']['limiar_bruto'], moeda=True)}</strong></td></tr>
      {limiar_recomendado_html}
    </table>
    <p class="nota" title="{html.escape(ajuda('limiar_ativo'))}">Limiar ativo: {fmt(p4['limiar_ativo'], moeda=True)} (posição total, não por contrato).</p>

    <h3 style="margin-top:22px; font-size:14px;">Retorno sobre o limiar (RLT)</h3>
    <table>
      <tr>{rotulo_com_ajuda('RLT acumulado', 'rlt_acumulado')}<td class="valor">{fmt(p4['rlt_acumulado']*100)}%</td></tr>
      <tr>{rotulo_com_ajuda('RLT anualizado', 'rlt_anualizado')}<td class="valor">{fmt(p4['rlt_anualizado']*100)}%</td></tr>
      <tr><td class="rotulo" title="{html.escape(ajuda('rlt_mensal_medio'))} {html.escape(ajuda('rlt_mensal_mediano'))}">RLT mensal médio / mediano</td><td class="valor">{fmt(p4['rlt_mensal_medio']*100)}% / {fmt(p4['rlt_mensal_mediano']*100)}%</td></tr>
      <tr><td class="rotulo" title="{html.escape(ajuda('rlt_movel_3'))}">RLT móvel 3 / 6 / 12 meses</td><td class="valor">{fmt(p4['rlt_movel_3']*100)}% / {fmt(p4['rlt_movel_6']*100)}% / {fmt(p4['rlt_movel_12']*100)}%</td></tr>
    </table>

    <h3 style="margin-top:22px; font-size:14px;">Risco normalizado pelo limiar</h3>
    <table>
      <tr><td class="rotulo" title="{html.escape(ajuda('mdd_total'))} {html.escape(ajuda('mdd_sobre_limiar'))}">MDD</td><td class="valor">{fmt(p4['mdd_total'], moeda=True)} &middot; {fmt(p4['mdd_sobre_limiar']*100)}% do limiar</td></tr>
      <tr><td class="rotulo" title="{html.escape(ajuda('pior_dia_total'))} {html.escape(ajuda('pior_dia_sobre_limiar'))}">Pior dia</td><td class="valor">{fmt(p4['pior_dia_total'], moeda=True)} &middot; {fmt(p4['pior_dia_sobre_limiar']*100)}% do limiar</td></tr>
      <tr><td class="rotulo" title="{html.escape(ajuda('es95_total'))} {html.escape(ajuda('es95_sobre_limiar'))}">Expected Shortfall 95%</td><td class="valor">{fmt(p4['es95_total'], moeda=True)} &middot; {fmt(p4['es95_sobre_limiar']*100)}% do limiar</td></tr>
      <tr><td class="rotulo" title="{html.escape(ajuda('ulcer_total'))} {html.escape(ajuda('ulcer_sobre_limiar'))}">Ulcer Index</td><td class="valor">{fmt(p4['ulcer_total'], moeda=True)} &middot; {fmt(p4['ulcer_sobre_limiar']*100)}% do limiar</td></tr>
      <tr><td class="rotulo" title="{html.escape(ajuda('pior_mes_total'))} {html.escape(ajuda('pior_mes_sobre_limiar'))}">Pior mês</td><td class="valor">{fmt(p4['pior_mes_total'], moeda=True)} &middot; {fmt(p4['pior_mes_sobre_limiar']*100)}% do limiar</td></tr>
    </table>
    <p class="nota">Escala TOTAL da posição (não por contrato) -- minimum_margin é da posição toda. RLT/MDD-L/etc. dependem dos parâmetros de limiar escolhidos (percentil, reserva operacional); não compare entre robôs calculados com parâmetros diferentes.</p>
    """


_SEVERIDADE_CSS = {"critical": "#d1242f", "high": "#bc4c00", "medium": "#9a6700"}


def gerar_secao_pagina5(p5: dict) -> str:
    """Qualidade da curva: concentração, lucro removendo eventos,
    permanência abaixo de zero, alertas automáticos (lâmina ideal.pdf §9)."""
    alertas_html = "<p class='nota'>Nenhum alerta disparado.</p>"
    if p5["alertas"]:
        itens = "".join(
            f"<li style='color:{_SEVERIDADE_CSS.get(a['severity'], '#57606a')}'>"
            f"<strong>[{a['severity'].upper()}]</strong> {a['message']}</li>"
            for a in p5["alertas"]
        )
        alertas_html = f"<ul>{itens}</ul>"

    ultima_neg = p5["ultima_data_negativa"]
    ultima_neg_str = ultima_neg.strftime("%d/%m/%Y") if ultima_neg is not None else "nunca ficou negativa"

    return f"""
    <h2>Página 5 — Qualidade da curva</h2>
    <table>
      <tr><td class="rotulo" title="{html.escape(ajuda('top1_dia'))} {html.escape(ajuda('top5_dias'))} {html.escape(ajuda('top10_dias'))}">Top 1 / 5 / 10 dias (participação no lucro)</td><td class="valor">{fmt(p5['top1_dia']*100)}% / {fmt(p5['top5_dias']*100)}% / {fmt(p5['top10_dias']*100)}%</td></tr>
      <tr><td class="rotulo" title="{html.escape(ajuda('melhor_mes_share'))} {html.escape(ajuda('top3_meses_share'))}">Melhor mês / Top 3 meses (participação no lucro)</td><td class="valor">{fmt(p5['melhor_mes_share']*100)}% / {fmt(p5['top3_meses_share']*100)}%</td></tr>
      <tr><td class="rotulo" title="{html.escape(ajuda('lucro_sem_melhor_dia'))} {html.escape(ajuda('lucro_sem_top5_dias'))}">Lucro sem o melhor dia / sem os 5 melhores dias</td><td class="valor">{fmt(p5['lucro_sem_melhor_dia'], moeda=True)} / {fmt(p5['lucro_sem_top5_dias'], moeda=True)}</td></tr>
      <tr><td class="rotulo" title="{html.escape(ajuda('lucro_sem_melhor_mes'))} {html.escape(ajuda('lucro_sem_top3_meses'))}">Lucro sem o melhor mês / sem os 3 melhores meses</td><td class="valor">{fmt(p5['lucro_sem_melhor_mes'], moeda=True)} / {fmt(p5['lucro_sem_top3_meses'], moeda=True)}</td></tr>
      <tr>{rotulo_com_ajuda('Lucro antes dos últimos 60 dias', 'lucro_antes_dos_ultimos_60_dias')}<td class="valor">{fmt(p5['lucro_antes_dos_ultimos_60_dias'], moeda=True)}</td></tr>
      <tr>{rotulo_com_ajuda('% de pregões com equity negativa', 'pct_dias_abaixo_de_zero')}<td class="valor">{fmt(p5['pct_dias_abaixo_de_zero']*100)}%</td></tr>
      <tr>{rotulo_com_ajuda('Última data com equity negativa', 'ultima_data_negativa')}<td class="valor">{ultima_neg_str}</td></tr>
      <tr>{rotulo_com_ajuda('Pregões desde a consolidação positiva', 'pregoes_desde_consolidacao_positiva')}<td class="valor">{p5['pregoes_desde_consolidacao_positiva']}</td></tr>
    </table>
    <h3 style="margin-top:22px; font-size:14px;">Alertas automáticos</h3>
    {alertas_html}
    """


def gerar_secao_pagina6(p6: dict) -> str:
    """Comparação entre ativos internos (lâmina ideal.pdf §12) -- só deve
    ser chamada para robôs com mais de um ativo_raiz."""
    linhas_ativos = "".join(
        f"<tr><td class='rotulo'>{a}</td>"
        f"<td class='valor'>{fmt(p6['lucro_por_ativo'][a], moeda=True)}</td>"
        f"<td class='valor'>{fmt(p6['mdd_por_ativo'][a], moeda=True)}</td></tr>"
        for a in p6["ativos"]
    )
    corr = p6["correlacao_ativos"]
    cabecalho_corr = "".join(f"<th>{a}</th>" for a in corr.columns)
    linhas_corr = "".join(
        f"<tr><td class='rotulo'>{a}</td>" + "".join(f"<td class='valor'>{fmt(corr.loc[a, b], 3)}</td>" for b in corr.columns) + "</tr>"
        for a in corr.index
    )

    return f"""
    <h2>Página 6 — Comparação entre ativos</h2>
    <table>
      <tr><th>Ativo</th><th title="{html.escape(ajuda('lucro_por_ativo'))}">Lucro líquido</th><th title="{html.escape(ajuda('mdd_por_ativo'))}">Maximum Drawdown</th></tr>
      {linhas_ativos}
    </table>
    <h3 style="margin-top:22px; font-size:14px;" title="Correlação de Pearson entre as séries diárias de cada ativo, todos os dias (inclusive os que um deles não operou, contados como 0).">Correlação diária (todos os dias)</h3>
    <table>
      <tr><th></th>{cabecalho_corr}</tr>
      {linhas_corr}
    </table>
    <p class="nota">Escala bruta (não por contrato) -- ver limitações em tradefolio.metric_registry (ativo sem referência de contrato estável não é normalizado). Correlação considera todos os dias, inclusive os que um dos ativos não operou (0); variantes por regime (dias ruins, alta volatilidade) não implementadas.</p>
    """


def gerar_secao_pagina3(p3: dict) -> str:
    pct = p3["percentis"]
    piores = "".join(f"<li>{d.strftime('%d/%m/%Y')}: {fmt(v, moeda=True)}</li>" for d, v in p3["piores_5"].items())
    melhores = "".join(f"<li>{d.strftime('%d/%m/%Y')}: {fmt(v, moeda=True)}</li>" for d, v in p3["melhores_5"].items())
    return f"""
    <h2>Página 3 — Distribuição e cauda</h2>
    <table>
      <tr>{rotulo_com_ajuda('Média diária', 'media')}<td class="valor">{fmt(p3['media'], moeda=True)}</td></tr>
      <tr>{rotulo_com_ajuda('Mediana diária', 'mediana')}<td class="valor">{fmt(p3['mediana'], moeda=True)}</td></tr>
      <tr>{rotulo_com_ajuda('Desvio-padrão diário', 'desvio_padrao')}<td class="valor">{fmt(p3['desvio_padrao'], moeda=True)}</td></tr>
      <tr>{rotulo_com_ajuda('Skewness', 'skewness')}<td class="valor">{fmt(p3['skewness'], 3)}</td></tr>
      <tr>{rotulo_com_ajuda('Kurtosis (excesso)', 'kurtosis')}<td class="valor">{fmt(p3['kurtosis'], 3)}</td></tr>
      <tr>{rotulo_com_ajuda('Percentil 5% / 95%', 'percentis')}<td class="valor">{fmt(pct[5], moeda=True)} / {fmt(pct[95], moeda=True)}</td></tr>
      <tr>{rotulo_com_ajuda('Percentil 1% / 99%', 'percentis')}<td class="valor">{fmt(pct[1], moeda=True)} / {fmt(pct[99], moeda=True)}</td></tr>
      <tr><td class="rotulo" title="{html.escape(ajuda('var_95'))} {html.escape(ajuda('var_99'))}">VaR histórico 95% / 99%</td><td class="valor">{fmt(p3['var_95'], moeda=True)} / {fmt(p3['var_99'], moeda=True)}</td></tr>
      <tr><td class="rotulo" title="{html.escape(ajuda('es_95'))} {html.escape(ajuda('es_99'))}">Expected Shortfall 95% / 99%</td><td class="valor">{fmt(p3['es_95'], moeda=True)} / {fmt(p3['es_99'], moeda=True)}</td></tr>
      <tr>{rotulo_com_ajuda('Média dos 5 piores dias', 'piores_5_media')}<td class="valor">{fmt(p3['piores_5_media'], moeda=True)}</td></tr>
      <tr>{rotulo_com_ajuda('Média dos 5 melhores dias', 'melhores_5_media')}<td class="valor">{fmt(p3['melhores_5_media'], moeda=True)}</td></tr>
    </table>
    <p class="nota">5 piores pregões: {piores}</p>
    <p class="nota">5 melhores pregões: {melhores}</p>
    <p class="nota">Distribuição calculada sobre todos os pregões (inclui os {(p3['serie']==0).sum()} dias sem operação, que empilham massa em zero — isso afeta percentil 50, skewness e kurtosis).</p>
    """


_FORA_DE_ESCOPO = (
    "Não implementado nesta versão (lâmina ideal.pdf): vapo/política de retirada, "
    "Monte Carlo/bootstrap, grade de deterioração, linha do tempo de mudanças de mão, "
    "selo de tipo de histórico, score geral, módulo de portfólio, schema JSON para IA. "
    "Ver TASKS.md para o que cada um exigiria antes de ser implementado."
)


def gerar_html(
    metricas: dict, grafico_b64: str, grafico_dist_b64: str = "",
    secao_pagina2: str = "", secao_pagina3: str = "",
    secao_pagina4: str = "", secao_pagina5: str = "", secao_pagina6: str = "",
    robo: str = "Romanos",
) -> str:
    p_ini, p_fim = metricas["periodo"]
    linhas = [
        ("Período", f"{p_ini.strftime('%d/%m/%Y')} a {p_fim.strftime('%d/%m/%Y')}", "periodo"),
        ("Pregões", f"{metricas['pregoes']}", "pregoes"),
        ("Operações (trades reconstruídos)", f"{metricas['n_trades_reconstruidos']}", "n_trades"),
        ("Win rate (por trade)", fmt(metricas["win_rate_trades"], pct=True), "win_rate_trades"),
        ("Lucro líquido (2 contratos)", fmt(metricas["lucro_liquido_2c"], moeda=True), "lucro_liquido_2c"),
        ("Lucro líquido por contrato", fmt(metricas["lucro_liquido_por_contrato"], moeda=True), "lucro_liquido_por_contrato"),
        ("Resultado médio diário (por contrato)", fmt(metricas["media_diaria"], moeda=True), "media_diaria"),
        ("Resultado mediano diário (por contrato)", fmt(metricas["mediana_diaria"], moeda=True), "mediana_diaria"),
        ("% dias positivos", fmt(metricas["pct_dias_positivos"], pct=True), "pct_dias_positivos"),
        ("% dias negativos", fmt(metricas["pct_dias_negativos"], pct=True), "pct_dias_negativos"),
        ("% dias neutros (sem trade)", fmt(metricas["pct_dias_neutros"], pct=True), "pct_dias_neutros"),
        ("Gain médio — dia (por contrato)", fmt(metricas["gain_medio"], moeda=True), "gain_medio"),
        ("Loss médio — dia (por contrato)", fmt(metricas["loss_medio"], moeda=True), "loss_medio"),
        ("Lucro médio — trade (2 contratos, líquido)", fmt(metricas["lucro_medio_trade"], moeda=True), "lucro_medio_trade"),
        ("Prejuízo médio — trade (2 contratos, líquido)", fmt(metricas["prejuizo_medio_trade"], moeda=True), "prejuizo_medio_trade"),
        ("Payoff (gain médio / |loss médio|)", fmt(metricas["payoff"]), "payoff"),
        ("Expectância diária (por contrato)", fmt(metricas["expectancia_diaria"], moeda=True), "expectancia_diaria"),
        ("Profit Factor (por trade, líquido)", fmt(metricas["profit_factor_trades"]), "profit_factor_trades"),
        ("Pior dia (por contrato)", fmt(metricas["pior_dia"], moeda=True), "pior_dia"),
        ("Melhor dia (por contrato)", fmt(metricas["melhor_dia"], moeda=True), "melhor_dia"),
        ("Retorno bruto %", fmt(metricas["retorno_bruto_pct"]) + "%", "retorno_bruto_pct"),
        ("Retorno líquido %", fmt(metricas["retorno_liquido_pct"]) + "%", "retorno_liquido_pct"),
        ("Maximum Drawdown (por contrato)", fmt(metricas["max_drawdown"], moeda=True), "max_drawdown"),
        ("Maximum Drawdown %**", fmt(metricas["max_drawdown_pct"]) + "%", "max_drawdown_pct"),
        ("Time Under Water máximo", f"{metricas['time_under_water_max_pregoes']} pregões", "time_under_water_max_pregoes"),
        ("Ulcer Index %**", fmt(metricas["ulcer_index_pct"]) + "%", "ulcer_index_pct"),
        ("Sharpe (anualizado)", fmt(metricas["sharpe"]), "sharpe"),
        ("Sortino (anualizado)", fmt(metricas["sortino"]), "sortino"),
        ("Calmar", fmt(metricas["calmar"]), "calmar"),
        ("Recovery Factor", fmt(metricas["recovery_factor"]), "recovery_factor"),
    ]

    linhas_html = "\n".join(
        f'<tr>{rotulo_com_ajuda(r, chave)}<td class="valor">{v}</td></tr>' for r, v, chave in linhas
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

    {secao_pagina4}
    {secao_pagina5}
    {secao_pagina6}

    <p class="nota">
      Ulcer Index e Maximum Drawdown % calculados com patrimônio = R$1.000/contrato (margem sugerida pelo autor) + resultado acumulado, drawdown% relativo ao pico móvel — mesma lógica da Smarttbot.<br>
      Trade reconstruído a partir da posição líquida (agrupa fills parciais); há 1 trade a menos que o reportado pela plataforma (~R$424, provavelmente anterior ao início do CSV) — assumido como aceitável.
    </p>
    <p class="nota">{_FORA_DE_ESCOPO}</p>
  </div>
</body>
</html>"""


def _parse_argumentos():
    parser = argparse.ArgumentParser(
        description="Gera a lâmina HTML estática a partir de um CSV de ordens Smarttbot."
    )
    parser.add_argument("csv_path", help="Caminho do CSV de ordens")
    parser.add_argument("output_path", help="Caminho do HTML a gerar")
    parser.add_argument(
        "--minimum-margin", type=float, required=True,
        help="Margem mínima da posição total (R$) -- obrigatório, nunca inventado (AGENTS.md §8)",
    )
    parser.add_argument("--percentil-cauda", type=int, choices=(95, 99), default=95)
    parser.add_argument("--fracao-reserva-operacional", type=float, default=0.0)
    parser.add_argument("--increment", type=float, default=500.0)
    parser.add_argument("--robo", default=None, help="Nome do robô no título (padrão: nome do arquivo)")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_argumentos()
    robo = args.robo or args.csv_path.rsplit("/", 1)[-1].rsplit(".", 1)[0]

    ordens = carregar_ordens(args.csv_path)
    contratos_referencia = detectar_contratos_referencia(ordens)
    diario = preencher_calendario_b3(agregar_diario(ordens, contratos_referencia=contratos_referencia))

    metricas, equity, drawdown = calcular_metricas_pagina1(diario, contratos_referencia=contratos_referencia)
    episodios = episodios_drawdown(equity, top_n=len(equity))
    grafico_b64 = fig_para_base64(montar_figura_curva_drawdown(equity, drawdown, episodios=episodios))

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

    p4 = calcular_metricas_pagina4(
        diario, minimum_margin=args.minimum_margin, percentil_cauda=args.percentil_cauda,
        fracao_reserva_operacional=args.fracao_reserva_operacional, increment=args.increment,
    )
    secao_pagina4 = gerar_secao_pagina4(p4)

    p5 = calcular_metricas_pagina5(diario)
    secao_pagina5 = gerar_secao_pagina5(p5)

    secao_pagina6 = ""
    if ordens["Ativo"].map(extrair_raiz_ativo).nunique() > 1:
        p6 = calcular_metricas_pagina6(ordens)
        secao_pagina6 = gerar_secao_pagina6(p6)

    html = gerar_html(
        metricas, grafico_b64, grafico_dist_b64, secao_pagina2, secao_pagina3,
        secao_pagina4, secao_pagina5, secao_pagina6, robo=robo,
    )

    with open(args.output_path, "w", encoding="utf-8") as f:
        f.write(html)
    print("Salvo em:", args.output_path)