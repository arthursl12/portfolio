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

import pandas as pd
import streamlit as st

from report import fmt, montar_figura_curva_drawdown, montar_figura_distribuicao
from tradefolio.alignment import preencher_calendario_b3
from tradefolio.custo_mensal import (
    FaixaCustoMensal,
    TabelaCustoMensal,
    aplicar_custo_mensal,
    resumo_custo_mensal,
)
from tradefolio.daily import agregar_diario, detectar_contratos_referencia, escalar_por_contratos
from tradefolio.drawdowns import drawdown_corrente, episodios_drawdown, tempo_recuperacao_mediano
from tradefolio.loaders import carregar_ordens
from tradefolio.metric_registry import REGISTRO
from tradefolio.report_data import (
    JANELAS_DISPONIVEIS,
    calcular_pagina1,
    calcular_pagina3,
    calcular_pagina4,
    calcular_pagina5,
    calcular_pagina6,
    calcular_robustez,
    filtrar_por_janela,
)
from tradefolio.validation import extrair_raiz_ativo

# Não implementado nesta versão (lâmina ideal.pdf) -- ver TASKS.md para o
# que cada um exigiria antes de ser implementado.
FORA_DE_ESCOPO = (
    "vapo/política de retirada, linha do tempo de mudanças de mão, "
    "selo de tipo de histórico, score geral, módulo de portfólio, "
    "schema JSON para IA"
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


def construir_tabela_custo_mensal(df_editado: pd.DataFrame) -> TabelaCustoMensal:
    """Converte a tabela editável (st.data_editor) numa
    tradefolio.custo_mensal.TabelaCustoMensal. Linhas totalmente vazias
    (o usuário ainda digitando uma nova linha) são ignoradas em vez de
    levantar erro; uma linha parcialmente preenchida propaga o erro de
    validação normalmente."""
    faixas = []
    for _, linha in df_editado.iterrows():
        if pd.isna(linha["min_contratos"]) and pd.isna(linha["custo_mensal"]):
            continue
        max_contratos = None if pd.isna(linha["max_contratos"]) else int(linha["max_contratos"])
        faixas.append(FaixaCustoMensal(
            min_contratos=int(linha["min_contratos"]),
            max_contratos=max_contratos,
            custo_mensal=float(linha["custo_mensal"]),
        ))
    if not faixas:
        faixas = [FaixaCustoMensal(1, None, 0.0)]
    return TabelaCustoMensal(faixas=tuple(faixas))


def ajuda(chave: str, default: str = "") -> str:
    """Texto de tooltip (`help=`) a partir do dicionário oficial de
    métricas (tradefolio.metric_registry) -- mesma fonte de verdade usada
    em report.py, em vez de duplicar a explicação em cada UI."""
    spec = REGISTRO.get(chave)
    return spec.interpretacao if spec else default


# Textos manuais para campos que não são uma métrica calculada (inputs do
# usuário, filtros) -- não têm entrada em metric_registry por design.
AJUDA_FONTE = "Escolher entre um CSV de exemplo já incluído ou enviar o seu próprio arquivo (formato Smarttbot)."
AJUDA_UPLOAD = "Arquivo de ordens exportado da Smarttbot -- ';' como delimitador, decimal BR ('1.234,56')."
AJUDA_ROBO = "CSV de exemplo já incluído no repositório (dados_exemplo/)."
AJUDA_JANELA = "Recorta a série diária para os últimos N a partir da ÚLTIMA data do CSV (não da data de hoje)."
AJUDA_N_CONTRATOS = "Simula o resultado como se o robô operasse com este número de contratos -- escala linear a partir do valor detectado no CSV (AGENTS.md §9)."
AJUDA_MINIMUM_MARGIN = "Margem exigida pela corretora para manter a posição configurada (posição total, não por contrato) -- nunca inventada; é preciso informar para calcular o limiar (Página 4)."
AJUDA_PERCENTIL_CAUDA = "Qual percentil do drawdown histórico compõe a reserva de cauda do limiar -- P99 é mais conservador (cauda mais extrema) que P95. Resolução do usuário: os dois ficam disponíveis, não um só fixo."
AJUDA_RESERVA_OPERACIONAL = "Percentual da margem mínima reservado como colchão operacional -- resolução do usuário: '% de minimum_margin', não um valor fixo em R$."
AJUDA_INCREMENT = "O limiar bruto é arredondado para cima neste incremento (ex. R$500 arredonda R$13.495 para R$13.500)."
AJUDA_CUSTO_MENSAL = "Custo mensal de plataforma/assinatura por faixa de número de contratos (não precisa ser linear) -- cobrado uma vez, no último pregão do mês. Pode ser 0, ou o mesmo valor para todas as faixas. Debitado sobre a referência real detectada, não sobre o número de contratos simulado (mesma limitação de escala linear já documentada para 'Número de contratos')."
AJUDA_TAMANHO_BLOCO = "Tamanho do bloco de pregões contíguos sorteado por vez (circular block bootstrap) -- blocos maiores preservam mais a autocorrelação local da série; bloco=1 equivale a um sorteio de dias independentes (tarefa 8.1)."
AJUDA_N_TRAJETORIAS = "Quantas trajetórias simuladas gerar. Mais trajetórias dão percentis mais estáveis, mas demoram mais (50.000 trajetórias x 252 dias roda em <1s neste robô)."
AJUDA_HORIZONTE = "Quantos pregões cada trajetória simulada tem -- 252 ≈ 1 ano de pregões."
AJUDA_SEED = "Semente do gerador aleatório. Deixe em branco para uma semente aleatória de verdade -- ela é sempre mostrada no resultado (nunca escondida), e reusá-la reproduz exatamente as mesmas trajetórias."
AJUDA_INCLUIR_SEM_OPERACAO = "Dias sem operação (NO_TRADE) são histórico legítimo e entram no sorteio como qualquer outro dia -- desmarque para excluí-los explicitamente."
AJUDA_REDUCAO_GANHOS = "Reduz todo dia positivo em X% antes de simular -- cenário de deterioração (lâmina ideal.pdf §10)."
AJUDA_AUMENTO_PERDAS = "Amplia todo dia negativo em X% antes de simular (torna as perdas maiores) -- o outro eixo da grade de deterioração."
AJUDA_AUMENTO_CUSTOS = "Aumenta o custo B3 (emolumento) em X% antes de simular -- reproduz os cenários 'custos +50%/+100%' do PDF-fonte."
AJUDA_SLIPPAGE = "Custo extra fixo por trade (R$), somado ao emolumento B3 -- simula slippage adicional."
AJUDA_REMOVER_MELHORES = "Zera os N melhores dias do histórico antes de simular -- testa quão dependente o robô é dos seus melhores eventos."
AJUDA_DUPLICAR_PIORES = "Dobra (no lugar, não insere uma data nova) o valor dos N piores dias antes de simular -- testa um cenário onde as piores perdas já observadas fossem duas vezes piores."


st.set_page_config(page_title="Lâmina ao vivo", layout="wide")
st.title("Lâmina ao vivo")

with st.sidebar:
    st.header("Dados")
    fonte = st.radio("Fonte do CSV", ["Robô de exemplo", "Enviar CSV"], help=AJUDA_FONTE)

    arquivo_ordens = None
    if fonte == "Enviar CSV":
        arquivo_ordens = st.file_uploader("CSV de ordens (formato Smarttbot)", type="csv", help=AJUDA_UPLOAD)
    else:
        exemplos = sorted(DADOS_EXEMPLO_DIR.glob("*.csv"))
        if exemplos:
            escolhido = st.selectbox("Robô", exemplos, format_func=lambda p: p.stem, help=AJUDA_ROBO)
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
    janela = st.selectbox(
        "Janela", JANELAS_DISPONIVEIS, index=len(JANELAS_DISPONIVEIS) - 1, help=AJUDA_JANELA,
    )
    chave_arquivo = getattr(arquivo_ordens, "name", str(arquivo_ordens))
    n_contratos = st.number_input(
        "Número de contratos", min_value=1, max_value=200,
        value=contratos_referencia, step=1,
        key=f"n_contratos::{chave_arquivo}", help=AJUDA_N_CONTRATOS,
    )

with st.sidebar:
    st.header("Limiar")
    st.caption("Necessário para a Página 4 (limiar/RLT) -- nunca inventado, sem valor padrão.")
    minimum_margin = st.number_input(
        "Margem mínima (R$, posição total)", min_value=0.0, value=None,
        step=500.0, key=f"minimum_margin::{chave_arquivo}", help=AJUDA_MINIMUM_MARGIN,
    )
    percentil_cauda = st.radio(
        "Percentil de cauda", [95, 99], horizontal=True,
        key=f"percentil_cauda::{chave_arquivo}", help=AJUDA_PERCENTIL_CAUDA,
    )
    fracao_reserva_operacional_pct = st.number_input(
        "Reserva operacional (% da margem)", min_value=0.0, max_value=100.0,
        value=10.0, step=1.0, key=f"reserva_operacional::{chave_arquivo}", help=AJUDA_RESERVA_OPERACIONAL,
    )
    increment = st.number_input(
        "Incremento de arredondamento (R$)", min_value=1.0, value=500.0,
        step=100.0, key=f"increment::{chave_arquivo}", help=AJUDA_INCREMENT,
    )

with st.sidebar:
    st.header("Custo mensal")
    st.caption(AJUDA_CUSTO_MENSAL)
    faixas_editadas = st.data_editor(
        pd.DataFrame({"min_contratos": [1], "max_contratos": [None], "custo_mensal": [0.0]}),
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "min_contratos": st.column_config.NumberColumn("Mín. contratos", min_value=1, step=1, required=True),
            "max_contratos": st.column_config.NumberColumn("Máx. contratos (vazio = sem limite)", min_value=1, step=1),
            "custo_mensal": st.column_config.NumberColumn(
                "Custo mensal (R$)", min_value=0.0, step=0.01, format="%.2f", required=True,
            ),
        },
        key=f"faixas_custo_mensal::{chave_arquivo}",
    )
    try:
        tabela_custo_mensal = construir_tabela_custo_mensal(faixas_editadas)
    except (ValueError, TypeError) as erro:
        st.error(f"Faixas de custo mensal inválidas: {erro}")
        st.stop()

with st.sidebar:
    st.header("Robustez (Monte Carlo)")
    tamanho_bloco = st.selectbox(
        "Tamanho do bloco (pregões)", [5, 10, 20, 40], index=2,
        key=f"tamanho_bloco::{chave_arquivo}", help=AJUDA_TAMANHO_BLOCO,
    )
    n_trajetorias = st.number_input(
        "Número de trajetórias", min_value=100, max_value=50000, value=2000, step=100,
        key=f"n_trajetorias::{chave_arquivo}", help=AJUDA_N_TRAJETORIAS,
    )
    horizonte = st.number_input(
        "Horizonte (pregões)", min_value=10, max_value=1000, value=252, step=1,
        key=f"horizonte::{chave_arquivo}", help=AJUDA_HORIZONTE,
    )
    seed_mc = st.number_input(
        "Seed (vazio = aleatória)", min_value=0, value=None, step=1,
        key=f"seed_mc::{chave_arquivo}", help=AJUDA_SEED,
    )
    incluir_dias_sem_operacao = st.checkbox(
        "Incluir dias sem operação na reamostragem", value=True,
        key=f"incluir_sem_op::{chave_arquivo}", help=AJUDA_INCLUIR_SEM_OPERACAO,
    )

    with st.expander("Cenário de deterioração (opcional)"):
        reducao_ganhos_pct = st.number_input(
            "Redução dos ganhos (%)", min_value=0.0, max_value=100.0, value=0.0, step=5.0,
            key=f"reducao_ganhos::{chave_arquivo}", help=AJUDA_REDUCAO_GANHOS,
        )
        aumento_perdas_pct = st.number_input(
            "Ampliação das perdas (%)", min_value=0.0, value=0.0, step=5.0,
            key=f"aumento_perdas::{chave_arquivo}", help=AJUDA_AUMENTO_PERDAS,
        )
        aumento_custos_pct = st.number_input(
            "Aumento dos custos B3 (%)", min_value=0.0, value=0.0, step=10.0,
            key=f"aumento_custos::{chave_arquivo}", help=AJUDA_AUMENTO_CUSTOS,
        )
        slippage_valor = st.number_input(
            "Slippage adicional (R$/trade)", min_value=0.0, value=0.0, step=1.0,
            key=f"slippage::{chave_arquivo}", help=AJUDA_SLIPPAGE,
        )
        remover_melhores_n = st.number_input(
            "Remover N melhores dias", min_value=0, value=0, step=1,
            key=f"remover_melhores::{chave_arquivo}", help=AJUDA_REMOVER_MELHORES,
        )
        duplicar_piores_n = st.number_input(
            "Duplicar N piores dias", min_value=0, value=0, step=1,
            key=f"duplicar_piores::{chave_arquivo}", help=AJUDA_DUPLICAR_PIORES,
        )

diario = preencher_calendario_b3(agregar_diario(ordens, contratos_referencia=contratos_referencia))
diario = aplicar_custo_mensal(diario, tabela_custo_mensal, contratos_referencia)
diario_filtrado = filtrar_por_janela(diario, janela)

metricas, equity, drawdown = calcular_pagina1(diario_filtrado, contratos_referencia=contratos_referencia)
metricas = escalar_metricas_absolutas(metricas, n_contratos)
equity = escalar_por_contratos(equity, n_contratos)
drawdown = escalar_por_contratos(drawdown, n_contratos)

rotulo_contratos = f"R$/{n_contratos} contrato{'s' if n_contratos != 1 else ''}"
p_ini, p_fim = metricas["periodo"]

custo_mensal_ativo = tabela_custo_mensal.custo_para(contratos_referencia)
custo_mensal_total_periodo = diario_filtrado["custo_mensal"].sum()
st.caption(
    f"Período: {p_ini.strftime('%d/%m/%Y')} a {p_fim.strftime('%d/%m/%Y')} "
    f"({metricas['pregoes']} pregões) · simulação a {n_contratos} contrato(s) "
    f"(referência detectada no CSV: {contratos_referencia}) · "
    f"custo mensal na faixa de {contratos_referencia} contrato(s): {fmt(custo_mensal_ativo, moeda=True)}/mês "
    f"({fmt(custo_mensal_total_periodo, moeda=True)} no período mostrado)"
)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Lucro líquido", fmt(metricas["lucro_liquido_por_contrato"], moeda=True), help=ajuda("lucro_liquido_por_contrato"))
col2.metric("Retorno líquido %", fmt(metricas["retorno_liquido_pct"]) + "%", help=ajuda("retorno_liquido_pct"))
col3.metric("Maximum Drawdown", fmt(metricas["max_drawdown"], moeda=True), help=ajuda("max_drawdown"))
col4.metric("Maximum Drawdown %", fmt(metricas["max_drawdown_pct"]) + "%", help=ajuda("max_drawdown_pct"))

col5, col6, col7, col8 = st.columns(4)
col5.metric("Sharpe", fmt(metricas["sharpe"]), help=ajuda("sharpe"))
col6.metric("Sortino", fmt(metricas["sortino"]), help=ajuda("sortino"))
col7.metric("Calmar", fmt(metricas["calmar"]), help=ajuda("calmar"))
col8.metric("Recovery Factor", fmt(metricas["recovery_factor"]), help=ajuda("recovery_factor"))

col9, col10 = st.columns(2)
col9.metric(
    "Drawdown corrente", fmt(drawdown_corrente(drawdown), moeda=True),
    help="Drawdown no último pregão da série -- distinto do Maximum Drawdown histórico (drawdowns.drawdown_corrente).",
)
col10.metric(
    "Tempo de recuperação mediano", f"{fmt(tempo_recuperacao_mediano(equity), 0)} pregões",
    help="Mediana de pregões até recuperar um novo máximo, só entre episódios de drawdown que de fato recuperaram (drawdowns.tempo_recuperacao_mediano).",
)

episodios = episodios_drawdown(equity, top_n=len(equity))
st.pyplot(montar_figura_curva_drawdown(equity, drawdown, rotulo_valor=rotulo_contratos, episodios=episodios))

with st.expander("Distribuição do resultado diário (por contrato, não escalado)"):
    p3 = calcular_pagina3(diario_filtrado)
    st.pyplot(montar_figura_distribuicao(p3))
    st.caption(
        "Página de distribuição continua por contrato (não multiplicada pelo número de "
        "contratos simulado) -- é uma visão de forma da série, não de R$ na sua posição."
    )

with st.expander("Custo mensal"):
    resumo_custo = resumo_custo_mensal(diario_filtrado)

    colcm1, colcm2, colcm3 = st.columns(3)
    colcm1.metric(
        "Custo mensal total no período", fmt(resumo_custo["custo_mensal_total"], moeda=True),
        help="Soma de tudo o que foi debitado como custo mensal (custo_mensal.resumo_custo_mensal) no período mostrado.",
    )
    colcm2.metric(
        "Lucro líquido sem custo mensal", fmt(resumo_custo["lucro_liquido_sem_custo_mensal"], moeda=True),
        help="O que o lucro líquido teria sido nesse período se não houvesse custo mensal -- escala TOTAL da posição, não por contrato.",
    )
    colcm3.metric(
        "Lucro líquido com custo mensal", fmt(resumo_custo["lucro_liquido_com_custo_mensal"], moeda=True),
        help="O lucro líquido real, já descontado o custo mensal -- mesma base de lucro_liquido_por_contrato*contratos, escala TOTAL.",
    )

    fracao_erosao = resumo_custo["fracao_erosao_do_lucro"]
    valor_erosao = "—" if pd.isna(fracao_erosao) else fmt(fracao_erosao * 100) + "%"
    custo_medio_mes = resumo_custo["custo_mensal_medio_por_mes_cobrado"]
    valor_custo_medio = "—" if pd.isna(custo_medio_mes) else fmt(custo_medio_mes, moeda=True)

    colcm4, colcm5 = st.columns(2)
    colcm4.metric(
        "Quanto o custo corroeu o lucro", valor_erosao,
        help="custo_mensal_total / lucro_liquido_sem_custo_mensal -- que fração do lucro que você teria tido sem essa despesa foi consumida por ela. '—' quando o robô já seria deficitário mesmo sem o custo mensal (a fração não teria uma leitura percentual sã).",
    )
    colcm5.metric(
        "Custo médio por mês cobrado", valor_custo_medio,
        help=f"Média do custo mensal nos {resumo_custo['meses_cobrados']} mês(es) em que ele foi cobrado (> 0) dentro do período mostrado.",
    )

    st.caption(
        "Nenhum limite de 'saudável' é definido aqui -- não há uma convenção "
        "para isso em nenhum dos PDFs-fonte nem foi combinado um valor. O "
        "número acima é mostrado cru; avalie conforme o contexto do robô "
        "(ex. quanto capital ele aloca, qual o lucro médio esperado)."
    )

limiar_ativo_valor = None
with st.expander("Limiar e RLT (retorno sobre o limiar)"):
    if minimum_margin is None:
        st.info("Informe a margem mínima na barra lateral para calcular o limiar.")
    else:
        p4 = calcular_pagina4(
            diario_filtrado, minimum_margin=minimum_margin, percentil_cauda=percentil_cauda,
            fracao_reserva_operacional=fracao_reserva_operacional_pct / 100, increment=increment,
        )
        limiar_ativo_valor = p4["limiar_ativo"]
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
        colr1.metric("RLT acumulado", fmt(p4["rlt_acumulado"] * 100) + "%", help=ajuda("rlt_acumulado"))
        colr2.metric("RLT anualizado", fmt(p4["rlt_anualizado"] * 100) + "%", help=ajuda("rlt_anualizado"))
        colr3.metric("RLT mensal médio", fmt(p4["rlt_mensal_medio"] * 100) + "%", help=ajuda("rlt_mensal_medio"))
        colr4.metric("RLT móvel 12m", fmt(p4["rlt_movel_12"] * 100) + "%", help=ajuda("rlt_movel_12"))

        colm1, colm2, colm3, colm4 = st.columns(4)
        colm1.metric("MDD / limiar", fmt(p4["mdd_sobre_limiar"] * 100) + "%", help=ajuda("mdd_sobre_limiar"))
        colm2.metric("ES95 / limiar", fmt(p4["es95_sobre_limiar"] * 100) + "%", help=ajuda("es95_sobre_limiar"))
        colm3.metric("Ulcer / limiar", fmt(p4["ulcer_sobre_limiar"] * 100) + "%", help=ajuda("ulcer_sobre_limiar"))
        colm4.metric("Pior mês / limiar", fmt(p4["pior_mes_sobre_limiar"] * 100) + "%", help=ajuda("pior_mes_sobre_limiar"))

with st.expander("Qualidade da curva"):
    p5 = calcular_pagina5(diario_filtrado)
    st.caption("Escala TOTAL da posição (não por contrato).")

    colc1, colc2, colc3 = st.columns(3)
    colc1.metric("Top 1 dia", fmt(p5["top1_dia"] * 100) + "%", help=ajuda("top1_dia"))
    colc2.metric("Top 5 dias", fmt(p5["top5_dias"] * 100) + "%", help=ajuda("top5_dias"))
    colc3.metric("Top 10 dias", fmt(p5["top10_dias"] * 100) + "%", help=ajuda("top10_dias"))

    colc4, colc5 = st.columns(2)
    colc4.metric("Melhor mês (participação)", fmt(p5["melhor_mes_share"] * 100) + "%", help=ajuda("melhor_mes_share"))
    colc5.metric("Top 3 meses (participação)", fmt(p5["top3_meses_share"] * 100) + "%", help=ajuda("top3_meses_share"))

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

with st.expander("Robustez (Monte Carlo)"):
    resumo_robustez = calcular_robustez(
        diario_filtrado, tamanho_bloco=tamanho_bloco, n_trajetorias=int(n_trajetorias),
        horizonte=int(horizonte), seed=int(seed_mc) if seed_mc is not None else None,
        incluir_dias_sem_operacao=incluir_dias_sem_operacao,
        aumento_custos=aumento_custos_pct / 100, slippage_por_trade=slippage_valor,
        reducao_ganhos=reducao_ganhos_pct / 100, aumento_perdas=aumento_perdas_pct / 100,
        remover_melhores_dias_n=int(remover_melhores_n), duplicar_piores_dias_n=int(duplicar_piores_n),
        minimum_margin=minimum_margin, limiar=limiar_ativo_valor,
    )
    st.caption(
        f"Escala TOTAL da posição -- {resumo_robustez['n_trajetorias']} trajetórias × "
        f"{resumo_robustez['horizonte']} pregões, bloco={resumo_robustez['tamanho_bloco']}, "
        f"seed={resumo_robustez['seed']} (reuse essa seed para reproduzir exatamente este resultado)."
    )

    colmc1, colmc2, colmc3, colmc4, colmc5 = st.columns(5)
    colmc1.metric("Lucro P5", fmt(resumo_robustez["lucro_p5"], moeda=True), help="5% das trajetórias simuladas tiveram lucro pior que este.")
    colmc2.metric("Lucro P25", fmt(resumo_robustez["lucro_p25"], moeda=True))
    colmc3.metric("Lucro P50 (mediano)", fmt(resumo_robustez["lucro_p50"], moeda=True))
    colmc4.metric("Lucro P75", fmt(resumo_robustez["lucro_p75"], moeda=True))
    colmc5.metric("Lucro P95", fmt(resumo_robustez["lucro_p95"], moeda=True), help="Só 5% das trajetórias simuladas tiveram lucro melhor que este.")

    colmd1, colmd2, colmd3, colmd4 = st.columns(4)
    colmd1.metric("MDD P50", fmt(resumo_robustez["mdd_p50"], moeda=True))
    colmd2.metric("MDD P90", fmt(resumo_robustez["mdd_p90"], moeda=True))
    colmd3.metric("MDD P95", fmt(resumo_robustez["mdd_p95"], moeda=True), help="90% de confiança de o drawdown simulado não ultrapassar este valor.")
    colmd4.metric("MDD P99", fmt(resumo_robustez["mdd_p99"], moeda=True), help="99% de confiança de o drawdown simulado não ultrapassar este valor.")

    colp1, colp2, colp3 = st.columns(3)
    colp1.metric("Probabilidade de prejuízo", fmt(resumo_robustez["probabilidade_prejuizo"] * 100) + "%")
    if "probabilidade_toca_margem" in resumo_robustez:
        colp2.metric("Probabilidade de tocar a margem", fmt(resumo_robustez["probabilidade_toca_margem"] * 100) + "%")
    else:
        colp2.metric("Probabilidade de tocar a margem", "—", help="Informe a margem mínima na barra lateral para calcular.")
    if "probabilidade_termina_abaixo_do_limiar" in resumo_robustez:
        colp3.metric("Prob. terminar abaixo do limiar", fmt(resumo_robustez["probabilidade_termina_abaixo_do_limiar"] * 100) + "%")
    else:
        colp3.metric("Prob. terminar abaixo do limiar", "—", help="Informe a margem mínima na barra lateral para calcular o limiar.")

    cenario_ativo = any([
        reducao_ganhos_pct, aumento_perdas_pct, aumento_custos_pct,
        slippage_valor, remover_melhores_n, duplicar_piores_n,
    ])
    if cenario_ativo:
        st.warning(
            f"Cenário de deterioração ativo: redução de ganhos {reducao_ganhos_pct:.0f}% · "
            f"ampliação de perdas {aumento_perdas_pct:.0f}% · aumento de custos {aumento_custos_pct:.0f}% · "
            f"slippage R$ {slippage_valor:.2f}/trade · {int(remover_melhores_n)} melhores dias removidos · "
            f"{int(duplicar_piores_n)} piores dias duplicados."
        )
    st.caption(
        "Reamostragem sobre a janela selecionada (circular block bootstrap) -- não é uma projeção "
        "garantida, é uma leitura de quão sensível o resultado histórico é à ordem em que os dias "
        "aconteceram."
    )

if ordens["Ativo"].map(extrair_raiz_ativo).nunique() > 1:
    with st.expander("Comparação entre ativos"):
        p6 = calcular_pagina6(ordens)
        st.caption("Calculado sobre todo o histórico do CSV (não respeita o filtro de janela).")
        for ativo in p6["ativos"]:
            colativo1, colativo2 = st.columns(2)
            colativo1.metric(f"Lucro líquido — {ativo}", fmt(p6["lucro_por_ativo"][ativo], moeda=True), help=ajuda("lucro_por_ativo"))
            colativo2.metric(f"Maximum Drawdown — {ativo}", fmt(p6["mdd_por_ativo"][ativo], moeda=True), help=ajuda("mdd_por_ativo"))
        st.write("Correlação diária:")
        st.dataframe(p6["correlacao_ativos"])

st.caption(f"Fora de escopo nesta versão: {FORA_DE_ESCOPO}. Ver TASKS.md para o que cada um exigiria.")
