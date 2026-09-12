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
from tradefolio.daily import agregar_diario, detectar_contratos_referencia, escalar_por_contratos
from tradefolio.drawdowns import drawdown_corrente, episodios_drawdown, tempo_recuperacao_mediano
from tradefolio.loaders import carregar_ordens
from tradefolio.report_data import (
    JANELAS_DISPONIVEIS,
    calcular_pagina1,
    calcular_pagina3,
    calcular_pagina4,
    calcular_pagina5,
    calcular_pagina6,
    filtrar_por_janela,
)
from tradefolio.validation import extrair_raiz_ativo

# Não implementado nesta versão (lâmina ideal.pdf) -- ver TASKS.md para o
# que cada um exigiria antes de ser implementado.
FORA_DE_ESCOPO = (
    "vapo/política de retirada, Monte Carlo/bootstrap, grade de deterioração, "
    "linha do tempo de mudanças de mão, selo de tipo de histórico, score geral, "
    "módulo de portfólio, schema JSON para IA"
)

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

if arquivo_ordens is None:
    st.info("Envie um CSV ou escolha um robô de exemplo para ver a lâmina.")
    st.stop()

try:
    ordens = carregar_ordens(arquivo_ordens)
except ValueError as erro:
    st.error(f"CSV inválido: {erro}")
    st.stop()

try:
    contratos_referencia = detectar_contratos_referencia(ordens)
except ValueError as erro:
    # ex.: um robô com tamanho de posição dinâmico (sem valor dominante de
    # 'Quantidade executada') -- não é seguro assumir uma referência.
    st.error(f"Não foi possível determinar o número de contratos de referência: {erro}")
    st.stop()

with st.sidebar:
    st.header("Filtros")
    janela = st.selectbox("Janela", JANELAS_DISPONIVEIS, index=len(JANELAS_DISPONIVEIS) - 1)
    chave_arquivo = getattr(arquivo_ordens, "name", str(arquivo_ordens))
    n_contratos = st.number_input(
        "Número de contratos", min_value=1, max_value=200,
        value=contratos_referencia, step=1,
        key=f"n_contratos::{chave_arquivo}",
    )

with st.sidebar:
    st.header("Limiar")
    st.caption("Necessário para a Página 4 (limiar/RLT) -- nunca inventado, sem valor padrão.")
    minimum_margin = st.number_input(
        "Margem mínima (R$, posição total)", min_value=0.0, value=None,
        step=500.0, key=f"minimum_margin::{chave_arquivo}",
    )
    percentil_cauda = st.radio(
        "Percentil de cauda", [95, 99], horizontal=True, key=f"percentil_cauda::{chave_arquivo}",
    )
    fracao_reserva_operacional_pct = st.number_input(
        "Reserva operacional (% da margem)", min_value=0.0, max_value=100.0,
        value=10.0, step=1.0, key=f"reserva_operacional::{chave_arquivo}",
    )
    increment = st.number_input(
        "Incremento de arredondamento (R$)", min_value=1.0, value=500.0,
        step=100.0, key=f"increment::{chave_arquivo}",
    )

diario = preencher_calendario_b3(agregar_diario(ordens, contratos_referencia=contratos_referencia))
diario_filtrado = filtrar_por_janela(diario, janela)

metricas, equity, drawdown = calcular_pagina1(diario_filtrado, contratos_referencia=contratos_referencia)
metricas = escalar_metricas_absolutas(metricas, n_contratos)
equity = escalar_por_contratos(equity, n_contratos)
drawdown = escalar_por_contratos(drawdown, n_contratos)

rotulo_contratos = f"R$/{n_contratos} contrato{'s' if n_contratos != 1 else ''}"
p_ini, p_fim = metricas["periodo"]

st.caption(
    f"Período: {p_ini.strftime('%d/%m/%Y')} a {p_fim.strftime('%d/%m/%Y')} "
    f"({metricas['pregoes']} pregões) · simulação a {n_contratos} contrato(s) "
    f"(referência detectada no CSV: {contratos_referencia})"
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

col9, col10 = st.columns(2)
col9.metric("Drawdown corrente", fmt(drawdown_corrente(drawdown), moeda=True))
col10.metric("Tempo de recuperação mediano", f"{fmt(tempo_recuperacao_mediano(equity), 0)} pregões")

episodios = episodios_drawdown(equity, top_n=len(equity))
st.pyplot(montar_figura_curva_drawdown(equity, drawdown, rotulo_valor=rotulo_contratos, episodios=episodios))

with st.expander("Distribuição do resultado diário (por contrato, não escalado)"):
    p3 = calcular_pagina3(diario_filtrado)
    st.pyplot(montar_figura_distribuicao(p3))
    st.caption(
        "Página de distribuição continua por contrato (não multiplicada pelo número de "
        "contratos simulado) -- é uma visão de forma da série, não de R$ na sua posição."
    )

with st.expander("Limiar e RLT (retorno sobre o limiar)"):
    if minimum_margin is None:
        st.info("Informe a margem mínima na barra lateral para calcular o limiar.")
    else:
        p4 = calcular_pagina4(
            diario_filtrado, minimum_margin=minimum_margin, percentil_cauda=percentil_cauda,
            fracao_reserva_operacional=fracao_reserva_operacional_pct / 100, increment=increment,
        )
        st.caption(
            f"Escala TOTAL da posição (não por contrato) -- {fmt(p4['meses_historico'], 1)} meses de "
            f"histórico na janela selecionada. Percentil ativo: P{p4['percentil_cauda_ativo']}."
        )

        limiar_ativo_dict = p4[f"limiar_p{percentil_cauda}"]
        tabela_limiar = {
            "Margem mínima": limiar_ativo_dict["minimum_margin"],
            "Reserva de cauda (drawdown)": limiar_ativo_dict["tail_drawdown_reserve"],
            "Prêmio por histórico curto": limiar_ativo_dict["uncertainty_premium"],
            "Reserva operacional": limiar_ativo_dict["operational_reserve"],
            "Limiar bruto": limiar_ativo_dict["limiar_bruto"],
        }
        if "limiar_recomendado" in limiar_ativo_dict:
            tabela_limiar["Limiar recomendado (arredondado)"] = limiar_ativo_dict["limiar_recomendado"]
        st.table({"Valor (R$)": {k: fmt(v, moeda=True) for k, v in tabela_limiar.items()}})

        colr1, colr2, colr3, colr4 = st.columns(4)
        colr1.metric("RLT acumulado", fmt(p4["rlt_acumulado"] * 100) + "%")
        colr2.metric("RLT anualizado", fmt(p4["rlt_anualizado"] * 100) + "%")
        colr3.metric("RLT mensal médio", fmt(p4["rlt_mensal_medio"] * 100) + "%")
        colr4.metric("RLT móvel 12m", fmt(p4["rlt_movel_12"] * 100) + "%")

        colm1, colm2, colm3, colm4 = st.columns(4)
        colm1.metric("MDD / limiar", fmt(p4["mdd_sobre_limiar"] * 100) + "%")
        colm2.metric("ES95 / limiar", fmt(p4["es95_sobre_limiar"] * 100) + "%")
        colm3.metric("Ulcer / limiar", fmt(p4["ulcer_sobre_limiar"] * 100) + "%")
        colm4.metric("Pior mês / limiar", fmt(p4["pior_mes_sobre_limiar"] * 100) + "%")

with st.expander("Qualidade da curva"):
    p5 = calcular_pagina5(diario_filtrado)
    st.caption("Escala TOTAL da posição (não por contrato).")

    colc1, colc2, colc3 = st.columns(3)
    colc1.metric("Top 1 dia", fmt(p5["top1_dia"] * 100) + "%")
    colc2.metric("Top 5 dias", fmt(p5["top5_dias"] * 100) + "%")
    colc3.metric("Top 10 dias", fmt(p5["top10_dias"] * 100) + "%")

    colc4, colc5 = st.columns(2)
    colc4.metric("Melhor mês (participação)", fmt(p5["melhor_mes_share"] * 100) + "%")
    colc5.metric("Top 3 meses (participação)", fmt(p5["top3_meses_share"] * 100) + "%")

    st.caption(
        f"Lucro sem o melhor dia: {fmt(p5['lucro_sem_melhor_dia'], moeda=True)} · "
        f"sem os 5 melhores dias: {fmt(p5['lucro_sem_top5_dias'], moeda=True)} · "
        f"sem o melhor mês: {fmt(p5['lucro_sem_melhor_mes'], moeda=True)} · "
        f"antes dos últimos 60 dias: {fmt(p5['lucro_antes_dos_ultimos_60_dias'], moeda=True)}"
    )

    if p5["alertas"]:
        for alerta in p5["alertas"]:
            aviso = f"[{alerta['severity'].upper()}] {alerta['message']}"
            (st.error if alerta["severity"] == "critical" else st.warning)(aviso)
    else:
        st.success("Nenhum alerta de qualidade da curva disparado.")

if ordens["Ativo"].map(extrair_raiz_ativo).nunique() > 1:
    with st.expander("Comparação entre ativos"):
        p6 = calcular_pagina6(ordens)
        st.caption("Calculado sobre todo o histórico do CSV (não respeita o filtro de janela).")
        for ativo in p6["ativos"]:
            colativo1, colativo2 = st.columns(2)
            colativo1.metric(f"Lucro líquido — {ativo}", fmt(p6["lucro_por_ativo"][ativo], moeda=True))
            colativo2.metric(f"Maximum Drawdown — {ativo}", fmt(p6["mdd_por_ativo"][ativo], moeda=True))
        st.write("Correlação diária:")
        st.dataframe(p6["correlacao_ativos"])

st.caption(f"Fora de escopo nesta versão: {FORA_DE_ESCOPO}. Ver TASKS.md para o que cada um exigiria.")
