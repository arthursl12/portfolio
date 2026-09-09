"""Lâmina ao vivo -- página Streamlit.

Presentation layer only (AGENTS.md §16/§17): nenhuma fórmula financeira
nova aqui, só chamadas a tradefolio.report_data/daily e aos construtores
de figura de report.py. As únicas páginas mostradas (1 e 3) são de nível
diário -- deliberadamente sem a página 2 (nível trade) nesta primeira
versão: filtrar `ordens` pela mesma janela de data quebraria a
reconstrução de trades (tradefolio.trades.reconstruir_trades precisa do
histórico completo de posição desde o início; cortar no meio de um trade
aberto corromperia o rastreamento de posição líquida). Métricas diárias
não têm esse problema -- cada dia é agregado independentemente.
"""
from pathlib import Path

import streamlit as st

from report import fmt, montar_figura_curva_drawdown, montar_figura_distribuicao
from tradefolio.alignment import preencher_calendario_b3
from tradefolio.daily import CONTRATOS_REFERENCIA_PADRAO, agregar_diario, escalar_por_contratos
from tradefolio.loaders import carregar_ordens
from tradefolio.report_data import JANELAS_DISPONIVEIS, calcular_pagina1, calcular_pagina3, filtrar_por_janela

DADOS_EXEMPLO_DIR = Path(__file__).parent / "dados_exemplo"

# Campos de tradefolio.report_data.calcular_pagina1 que são valores
# absolutos em R$/contrato -- escalam linearmente com o número de
# contratos simulado. Os demais (%, razões, contagens, datas) são
# invariantes ao número de contratos (verificado algebricamente antes de
# implementar tradefolio.daily.escalar_por_contratos) e não entram aqui.
CAMPOS_ABSOLUTOS_PAGINA1 = (
    "lucro_liquido_por_contrato", "media_diaria", "mediana_diaria",
    "gain_medio", "loss_medio", "expectancia_diaria", "pior_dia",
    "melhor_dia", "max_drawdown", "ulcer_index_rs",
)


def escalar_metricas_absolutas(metricas: dict, n_contratos: float) -> dict:
    escaladas = dict(metricas)
    for campo in CAMPOS_ABSOLUTOS_PAGINA1:
        escaladas[campo] = escalar_por_contratos(metricas[campo], n_contratos)
    return escaladas


st.set_page_config(page_title="Lâmina ao vivo", layout="wide")
st.title("Lâmina ao vivo")

with st.sidebar:
    st.header("Dados")
    fonte = st.radio("Fonte do CSV", ["Robô de exemplo", "Enviar CSV"])

    arquivo_ordens = None
    if fonte == "Enviar CSV":
        arquivo_ordens = st.file_uploader("CSV de ordens (formato Smarttbot)", type="csv")
    else:
        exemplos = sorted(DADOS_EXEMPLO_DIR.glob("*.csv"))
        if exemplos:
            escolhido = st.selectbox("Robô", exemplos, format_func=lambda p: p.stem)
            arquivo_ordens = escolhido
        else:
            st.warning(f"Nenhum CSV de exemplo em {DADOS_EXEMPLO_DIR}/")

    st.header("Filtros")
    janela = st.selectbox("Janela", JANELAS_DISPONIVEIS, index=len(JANELAS_DISPONIVEIS) - 1)
    n_contratos = st.number_input(
        "Número de contratos", min_value=1, max_value=100,
        value=CONTRATOS_REFERENCIA_PADRAO, step=1,
    )

if arquivo_ordens is None:
    st.info("Envie um CSV ou escolha um robô de exemplo para ver a lâmina.")
    st.stop()

try:
    ordens = carregar_ordens(arquivo_ordens)
except ValueError as erro:
    st.error(f"CSV inválido: {erro}")
    st.stop()

diario = preencher_calendario_b3(agregar_diario(ordens))
diario_filtrado = filtrar_por_janela(diario, janela)

metricas, equity, drawdown = calcular_pagina1(diario_filtrado)
metricas = escalar_metricas_absolutas(metricas, n_contratos)
equity = escalar_por_contratos(equity, n_contratos)
drawdown = escalar_por_contratos(drawdown, n_contratos)

rotulo_contratos = f"R$/{n_contratos} contrato{'s' if n_contratos != 1 else ''}"
p_ini, p_fim = metricas["periodo"]

st.caption(
    f"Período: {p_ini.strftime('%d/%m/%Y')} a {p_fim.strftime('%d/%m/%Y')} "
    f"({metricas['pregoes']} pregões) · simulação a {n_contratos} contrato(s) "
    f"(referência do backtest: {CONTRATOS_REFERENCIA_PADRAO})"
)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Lucro líquido", fmt(metricas["lucro_liquido_por_contrato"], moeda=True))
col2.metric("Retorno líquido %", fmt(metricas["retorno_liquido_pct"]) + "%")
col3.metric("Maximum Drawdown", fmt(metricas["max_drawdown"], moeda=True))
col4.metric("Maximum Drawdown %", fmt(metricas["max_drawdown_pct"]) + "%")

col5, col6, col7, col8 = st.columns(4)
col5.metric("Sharpe", fmt(metricas["sharpe"]))
col6.metric("Sortino", fmt(metricas["sortino"]))
col7.metric("Calmar", fmt(metricas["calmar"]))
col8.metric("Recovery Factor", fmt(metricas["recovery_factor"]))

st.pyplot(montar_figura_curva_drawdown(equity, drawdown, rotulo_valor=rotulo_contratos))

with st.expander("Distribuição do resultado diário (por contrato, não escalado)"):
    p3 = calcular_pagina3(diario_filtrado)
    st.pyplot(montar_figura_distribuicao(p3))
    st.caption(
        "Página de distribuição continua por contrato (não multiplicada pelo número de "
        "contratos simulado) -- é uma visão de forma da série, não de R$ na sua posição."
    )
