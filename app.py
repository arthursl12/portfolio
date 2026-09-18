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
import plotly.express as px
import streamlit as st

from report import fmt, montar_figura_curva_drawdown, montar_figura_distribuicao
from tradefolio.alignment import preencher_calendario_b3
from tradefolio.custo_mensal import (
    FaixaCustoMensal,
    TabelaCustoMensal,
    aplicar_custo_mensal,
    resumo_custo_mensal,
)
from tradefolio.daily import (
    agregar_diario,
    contratos_referencia_por_ativo,
    detectar_contratos_referencia,
    detectar_contratos_referencia_multi_ativo,
    escalar_por_contratos,
)
from tradefolio.daily_results import (
    CONTRATOS_REFERENCIA_RESULTADOS_DIARIOS,
    carregar_resultados_diarios,
    eh_formato_resultados_diarios,
    montar_diario_resultados,
)
from tradefolio.drawdowns import drawdown_corrente, episodios_drawdown, tempo_recuperacao_mediano
from tradefolio.loaders import carregar_ordens
from tradefolio.metric_registry import REGISTRO
from tradefolio.portfolio import (
    beneficio_diversificacao,
    buscar_combinacoes_portfolio,
    buscar_combinacoes_portfolio_com_filtros,
    clusters_de_risco,
    contribuicao_marginal,
    contribuicao_risco_por_robo,
    correlacao_dias_conjuntos,
    correlacao_movel,
    correlacao_perdas,
    correlacao_piores_dias,
    correlacao_portfolio,
    correlacao_volatilidade_alta,
    curva_limiares_mdd,
    fronteira_pareto,
    funil_selecao_portfolio,
    limiar_agregado_portfolio,
    metricas_agregadas,
    restringir_janela_comum,
    rlt_e_risco_portfolio,
    robustez_dos_finalistas,
    robustez_portfolio,
    scores_individuais_portfolio,
    selecionar_melhores_combinacoes,
    shortlist_portfolio,
    sincronizar_operou,
    sincronizar_portfolio,
    vizinhanca_local,
)
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
    "selo de tipo de histórico, score geral, schema JSON para IA"
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
AJUDA_MINIMUM_MARGIN_PORTFOLIO = "Margem exigida pela corretora POR CONTRATO deste robô -- diferente do modo Robô único (que pede a margem da posição TOTAL). Aqui é por contrato porque o número de contratos de cada robô pode ser ajustado dentro do portfólio (para testar dimensionamentos diferentes sem reinformar a margem); margem total desse robô = margem por contrato × contratos simulados."
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


def rodar_modo_portfolio():
    """Modo Portfólio (AGENTS.md épico 10) -- sincroniza 2+ robôs e mostra
    métricas agregadas, correlação, limiar agregado e benefício da
    diversificação (tradefolio.portfolio). Cada robô roda sua própria
    detecção de contratos_referencia (inclusive o fallback multi-ativo por
    perna) de forma independente. Custo mensal por robô é suportado (ver
    convenção abaixo), assim como robustez (Monte Carlo) do portfólio
    combinado (tradefolio.portfolio.robustez_portfolio); janela de filtro
    do modo Robô único e cenários de deterioração continuam fora daqui
    (fora do escopo desta primeira fatia do Épico 10, ver docstring de
    tradefolio.portfolio).

    Custo mensal (pedido de acompanhamento do usuário): cada robô tem sua
    própria tabela de faixas (mesmo editor do modo Robô único), debitada
    sobre N_CONTRATOS_ROBO (o tamanho SIMULADO no portfólio) -- diferente
    do modo Robô único, onde o custo é debitado sobre `contratos_referencia`
    (uma limitação documentada lá, porque o `diario` nunca é reescalado
    naquele modo). Aqui o `diario` JÁ é reescalado para `n_contratos_robo`
    antes do custo mensal ser aplicado, então cobrar pela faixa
    correspondente a `n_contratos_robo` é consistente com a simulação, não
    uma limitação.

    Convenção de escala (pedido explícito do usuário, para permitir
    testar diferentes números de contratos por robô dentro do portfólio
    sem reinformar a margem toda vez): a margem mínima aqui é POR
    CONTRATO, diferente do modo Robô único (posição total) -- a margem
    total de cada robô = margem/contrato × contratos simulados no
    portfólio. `diario['liquido']` de cada robô também é reescalado de
    `liquido_por_contrato × n_contratos` (mesma convenção linear de
    `tradefolio.daily.escalar_por_contratos`) ANTES de sincronizar --
    tanto o limiar individual (para "soma dos limiares individuais")
    quanto a sincronização do portfólio usam o robô já no tamanho
    simulado, para a comparação ser sobre a mesma base."""
    with st.sidebar:
        st.header("Robôs do portfólio")
        fonte = st.radio(
            "Fonte dos CSVs", ["Robôs de exemplo", "Enviar CSVs"],
            key="portfolio_fonte", help=AJUDA_FONTE,
        )
        if fonte == "Enviar CSVs":
            arquivos = st.file_uploader(
                "CSVs de ordens (formato Smarttbot)", type="csv", accept_multiple_files=True,
                key="portfolio_upload", help=AJUDA_UPLOAD,
            ) or []
        else:
            exemplos = sorted(DADOS_EXEMPLO_DIR.glob("*.csv"))
            arquivos = st.multiselect(
                "Robôs", exemplos, format_func=lambda p: p.stem,
                key="portfolio_exemplos", help=AJUDA_ROBO,
            )

    if len(arquivos) < 2:
        st.info("Escolha ao menos 2 robôs na barra lateral para montar um portfólio.")
        return

    with st.sidebar:
        st.header("Limiar (portfólio)")
        percentil_cauda = st.radio(
            "Percentil de cauda", [95, 99], horizontal=True,
            key="portfolio_percentil_cauda", help=AJUDA_PERCENTIL_CAUDA,
        )
        fracao_reserva_operacional_pct = st.number_input(
            "Reserva operacional (% da margem)", min_value=0.0, max_value=100.0,
            value=10.0, step=1.0, key="portfolio_reserva_operacional", help=AJUDA_RESERVA_OPERACIONAL,
        )
        increment = st.number_input(
            "Incremento de arredondamento (R$)", min_value=1.0, value=500.0,
            step=100.0, key="portfolio_increment", help=AJUDA_INCREMENT,
        )
        st.header("Robustez (Monte Carlo) do portfólio")
        tamanho_bloco_pf = st.selectbox(
            "Tamanho do bloco (pregões)", [5, 10, 20, 40], index=2,
            key="portfolio_tamanho_bloco", help=AJUDA_TAMANHO_BLOCO,
        )
        n_trajetorias_pf = st.number_input(
            "Número de trajetórias", min_value=100, max_value=50000, value=2000, step=100,
            key="portfolio_n_trajetorias", help=AJUDA_N_TRAJETORIAS,
        )
        horizonte_pf = st.number_input(
            "Horizonte (pregões)", min_value=10, max_value=1000, value=252, step=1,
            key="portfolio_horizonte", help=AJUDA_HORIZONTE,
        )
        seed_pf = st.number_input(
            "Seed (vazio = aleatória)", min_value=0, value=None, step=1,
            key="portfolio_seed_mc", help=AJUDA_SEED,
        )
        incluir_sem_operacao_pf = st.checkbox(
            "Incluir dias sem operação na reamostragem", value=True,
            key="portfolio_incluir_sem_op", help=AJUDA_INCLUIR_SEM_OPERACAO,
        )
        st.header("Contratos, margem e custo mensal por robô")
        st.caption(
            "Número de contratos simulado por robô DENTRO do portfólio (independente do "
            "detectado no CSV -- permite testar outros dimensionamentos), a margem por "
            "contrato de cada um e o custo mensal de plataforma de cada um."
        )

    st.header("Portfólio")

    diarios, minimum_margins, limiares_individuais, resumo_robos = {}, {}, {}, {}
    diarios_referencia, margens_por_contrato, candidatos_contratos = {}, {}, {}
    houve_erro = False

    for arquivo in arquivos:
        nome_arquivo = getattr(arquivo, "name", str(arquivo))
        nome_robo = Path(nome_arquivo).stem

        if eh_formato_resultados_diarios(arquivo):
            # Robô sem exportação order-level (ex. TradingX) -- só
            # resultado diário já agregado. contratos_referencia=1 fixo
            # (decisão do usuário, não detectada -- não há "Quantidade
            # executada" neste formato). bruto/custo/n_trades ficam NaN
            # no diario (genuinamente desconhecidos, ver
            # tradefolio.daily_results).
            try:
                resultados = carregar_resultados_diarios(arquivo)
                diario = montar_diario_resultados(resultados)
            except ValueError as erro:
                st.error(f"{nome_robo}: CSV de resultados diários inválido: {erro}")
                houve_erro = True
                continue
            contratos_referencia = CONTRATOS_REFERENCIA_RESULTADOS_DIARIOS
        else:
            try:
                ordens = carregar_ordens(arquivo)
            except ValueError as erro:
                st.error(f"{nome_robo}: CSV inválido: {erro}")
                houve_erro = True
                continue

            try:
                contratos_referencia = detectar_contratos_referencia(ordens)
            except ValueError:
                with st.sidebar:
                    st.warning(f"{nome_robo}: detecção sobre o histórico inteiro falhou -- tentando por ativo.")
                    dias_recentes = st.number_input(
                        f"{nome_robo}: janela p/ config. atual (dias)", min_value=7, max_value=730,
                        value=90, step=1, key=f"portfolio_dias_recentes::{nome_arquivo}",
                    )
                try:
                    contratos_referencia = detectar_contratos_referencia_multi_ativo(
                        ordens, dias_recentes=int(dias_recentes)
                    )
                except ValueError as erro:
                    st.error(f"{nome_robo}: não foi possível determinar contratos de referência: {erro}")
                    houve_erro = True
                    continue

            diario = preencher_calendario_b3(agregar_diario(ordens, contratos_referencia=contratos_referencia))

        diarios_referencia[nome_robo] = diario

        with st.sidebar:
            n_contratos_robo = st.number_input(
                f"{nome_robo}: número de contratos no portfólio", min_value=1, max_value=200,
                value=int(contratos_referencia), step=1,
                key=f"portfolio_n_contratos::{nome_arquivo}", help=AJUDA_N_CONTRATOS,
            )
            margem_por_contrato = st.number_input(
                f"{nome_robo}: margem mínima por contrato (R$)", min_value=0.0, value=None,
                step=100.0, key=f"portfolio_margin::{nome_arquivo}", help=AJUDA_MINIMUM_MARGIN_PORTFOLIO,
            )
            with st.expander(f"{nome_robo}: candidatos para otimização"):
                permitir_excluir_robo = st.checkbox(
                    "Permitir excluir este robô da busca (candidato 0)", value=True,
                    key=f"portfolio_permitir_excluir::{nome_arquivo}",
                    help="Tarefa 10.8 -- 0 contratos = robô fora do portfólio nesta combinação. "
                         "Desmarque para forçar que este robô sempre esteja incluído na busca.",
                )
                max_candidato_robo = st.number_input(
                    "Máximo de contratos candidato", min_value=1, max_value=200,
                    value=int(contratos_referencia) * 2, step=1,
                    key=f"portfolio_max_candidato::{nome_arquivo}",
                )
                passo_candidato_robo = st.number_input(
                    "Passo entre candidatos", min_value=1, max_value=int(max_candidato_robo),
                    value=1, step=1, key=f"portfolio_passo_candidato::{nome_arquivo}",
                )
            candidatos_robo = list(range(int(passo_candidato_robo), int(max_candidato_robo) + 1, int(passo_candidato_robo)))
            if permitir_excluir_robo:
                candidatos_robo = [0] + candidatos_robo
            candidatos_contratos[nome_robo] = candidatos_robo
            st.caption(f"{nome_robo}: custo mensal por faixa de contratos (R$)")
            faixas_editadas_robo = st.data_editor(
                pd.DataFrame({"min_contratos": [1], "max_contratos": [None], "custo_mensal": [0.0]}),
                num_rows="dynamic", hide_index=True,
                column_config={
                    "min_contratos": st.column_config.NumberColumn("Mín. contratos", min_value=1, step=1, required=True),
                    "max_contratos": st.column_config.NumberColumn("Máx. contratos (vazio = sem limite)", min_value=1, step=1),
                    "custo_mensal": st.column_config.NumberColumn("Custo mensal (R$)", min_value=0.0, step=0.01, format="%.2f", required=True),
                },
                key=f"portfolio_faixas_custo_mensal::{nome_arquivo}",
            )
            try:
                tabela_custo_mensal_robo = construir_tabela_custo_mensal(faixas_editadas_robo)
            except (ValueError, TypeError) as erro:
                st.error(f"{nome_robo}: faixas de custo mensal inválidas: {erro}")
                houve_erro = True
                continue

        # Reescala o robô inteiro (não só a margem) para o número de
        # contratos simulado no portfólio -- mesma convenção de
        # tradefolio.daily.escalar_por_contratos usada no modo Robô único,
        # aplicada aqui ao `liquido` (escala TOTAL) via liquido_por_contrato.
        diario_simulado = diario.copy()
        diario_simulado["liquido"] = diario["liquido_por_contrato"] * n_contratos_robo

        # Custo mensal debitado sobre N_CONTRATOS_ROBO (o tamanho SIMULADO
        # no portfólio), não sobre contratos_referencia (o detectado) --
        # diferente do modo Robô único (onde essa mesma escolha é uma
        # limitação documentada, porque lá o diario nunca é reescalado).
        # Aqui o diario JÁ foi reescalado para n_contratos_robo acima, então
        # cobrar pela faixa correspondente a n_contratos_robo é consistente,
        # não uma limitação.
        diario_simulado = aplicar_custo_mensal(diario_simulado, tabela_custo_mensal_robo, int(n_contratos_robo))
        diarios[nome_robo] = diario_simulado
        resumo_robos[nome_robo] = {
            "contratos_referencia": int(contratos_referencia),
            "n_contratos": int(n_contratos_robo),
            "custo_mensal_total": diario_simulado["custo_mensal"].sum(),
        }

        if margem_por_contrato is not None:
            margem_total = margem_por_contrato * n_contratos_robo
            minimum_margins[nome_robo] = margem_total
            margens_por_contrato[nome_robo] = margem_por_contrato
            resumo_robos[nome_robo]["margem_por_contrato"] = margem_por_contrato
            resumo_robos[nome_robo]["margem_total"] = margem_total
            p4_individual = calcular_pagina4(
                diario_simulado, minimum_margin=margem_total, percentil_cauda=percentil_cauda,
                fracao_reserva_operacional=fracao_reserva_operacional_pct / 100, increment=increment,
            )
            limiares_individuais[nome_robo] = p4_individual["limiar_ativo"]

    if houve_erro:
        st.warning("Corrija os erros acima para incluir todos os robôs no portfólio.")
    if len(diarios) < 2:
        st.warning("São necessários ao menos 2 robôs válidos para sincronizar um portfólio.")
        return

    tabela_composicao = pd.DataFrame({
        nome: {
            "Contratos de referência (detectado)": info["contratos_referencia"],
            "Contratos simulados no portfólio": info["n_contratos"],
            "Margem/contrato (R$)": fmt(info.get("margem_por_contrato"), moeda=True),
            "Margem total (R$)": fmt(info.get("margem_total"), moeda=True),
            "Custo mensal total no período (R$)": fmt(info.get("custo_mensal_total"), moeda=True),
        }
        for nome, info in resumo_robos.items()
    }).T
    st.subheader("Composição do portfólio")
    st.table(tabela_composicao)

    custo_mensal_total_combinado = sum(info.get("custo_mensal_total", 0.0) for info in resumo_robos.values())
    st.caption(
        f"Custo mensal total combinado no período mostrado: {fmt(custo_mensal_total_combinado, moeda=True)} "
        "-- já descontado do lucro de cada robô (embutido em `liquido` antes da sincronização), não é uma "
        "dedução adicional. Cobrado sobre os contratos SIMULADOS no portfólio, não sobre a referência "
        "detectada (diferente do modo Robô único -- aqui o diario já foi reescalado, ver docstring)."
    )

    escopo_temporal = st.radio(
        "Escopo temporal das métricas do portfólio",
        ["Janela comum (todos ativos)", "Todos os dias (união)"],
        key="portfolio_escopo_temporal",
        captions=[
            "Só o período em que TODOS os robôs já existiam -- evita misturar anos de um "
            "robô sozinho com o período em que todos operavam juntos. Recomendado.",
            "Do início do robô mais antigo ao fim do mais recente -- um robô que ainda não "
            "existia conta como 0 nesses dias (não é excluído, só não contribui).",
        ],
        help="Padrão pedido pelo usuário: lucro/MDD/ES/correlação/limiar/RLT/contribuição "
             "marginal/otimização usam a janela comum por padrão -- "
             "ver tradefolio.portfolio.restringir_janela_comum.",
    )
    usar_janela_comum = escopo_temporal == "Janela comum (todos ativos)"

    largo = sincronizar_portfolio(diarios)
    if usar_janela_comum:
        try:
            largo = restringir_janela_comum(largo)
        except ValueError as erro:
            st.error(str(erro))
            st.stop()
    agregadas = metricas_agregadas(largo)
    correlacao = correlacao_portfolio(largo)

    st.caption(
        f"{len(diarios)} robôs sincronizados: {', '.join(sorted(diarios))} -- "
        f"{largo.index.min().strftime('%d/%m/%Y')} a {largo.index.max().strftime('%d/%m/%Y')} "
        f"({len(largo)} pregões, escopo: {escopo_temporal.split(' (')[0].lower()}). Datas em que "
        "um robô ainda não existia contam como ausentes (NaN) na sincronização, não como zero -- "
        "só dias em que o robô já existia mas não operou contam como zero (mesma convenção NO_TRADE "
        "usada dentro de cada robô)."
    )

    colp1, colp2, colp3 = st.columns(3)
    colp1.metric("Lucro total (combinado)", fmt(agregadas["lucro_total"], moeda=True))
    colp2.metric("Maximum Drawdown (combinado)", fmt(agregadas["mdd"], moeda=True))
    colp3.metric("Expected Shortfall 95% (combinado)", fmt(agregadas["es_95"], moeda=True))

    operou = sincronizar_operou(diarios)

    with st.expander("Correlação entre robôs"):
        variante = st.radio(
            "Variante", [
                "Todos os dias", "Dias em que todos operaram", "Piores 20% dias (combinado)",
                "Dias de perda (combinado)", "Volatilidade alta (combinado)",
            ],
            key="portfolio_variante_correlacao",
            captions=[
                "Correlação sobre todo o escopo temporal escolhido acima -- pairwise complete "
                "(cada par usa só as datas em que ambos têm dado).",
                "Só datas em que TODOS os robôs de fato operaram (não apenas existiam) -- mais "
                "restritivo que o escopo temporal acima.",
                "Só os 20% piores dias da série COMBINADA do portfólio -- revela se a "
                "correlação sobe justamente quando o portfólio vai mal.",
                "Só dias em que a série COMBINADA teve resultado negativo.",
                "Só os dias de maior volatilidade (desvio-padrão móvel) da série combinada -- "
                "janela ajustável abaixo.",
            ],
            help="lâmina ideal.pdf §13 pede pelo menos 4 variantes -- 'piores dias'/'perda'/"
                 "'volatilidade alta' usam a série COMBINADA do portfólio para definir "
                 "'dia ruim', não uma recombinação por par (ver docstring de tradefolio.portfolio).",
        )
        if variante == "Todos os dias":
            matriz = correlacao
        elif variante == "Dias em que todos operaram":
            matriz = correlacao_dias_conjuntos(largo, operou)
        elif variante == "Piores 20% dias (combinado)":
            matriz = correlacao_piores_dias(largo, fracao=0.20)
        elif variante == "Dias de perda (combinado)":
            matriz = correlacao_perdas(largo)
        else:
            janela_vol = st.number_input(
                "Janela de volatilidade (pregões)", min_value=5, max_value=252, value=21, step=1,
                key="portfolio_janela_vol",
            )
            matriz = correlacao_volatilidade_alta(largo, janela=int(janela_vol), fracao=0.20)
        st.caption(
            "Correlação de Pearson par-a-par (pairwise complete observations -- cada par usa só "
            "as datas em que ambos os robôs têm dado dentro do subconjunto da variante escolhida)."
        )
        st.dataframe(matriz)

        st.subheader("Correlação móvel")
        janela_movel = st.number_input(
            "Janela (pregões)", min_value=5, max_value=252, value=63, step=1,
            key="portfolio_janela_movel",
            help="Correlação par-a-par recalculada dia a dia sobre esta janela deslizante -- "
                 "os primeiros dias de cada par ficam vazios até a janela completar.",
        )
        movel = correlacao_movel(largo, janela_pregoes=int(janela_movel))
        st.line_chart(movel)

        st.subheader("Clusters de risco")
        st.caption(
            "Backlog de prompts/otimizacao.pdf §4 (\"agrupe EAs que representam o mesmo risco\") "
            "-- decisão confirmada com o usuário: grafo de limiar + componentes conexos sobre a "
            "correlação geral (\"Todos os dias\" acima), sem depender de scipy/sklearn. Correlação "
            "NEGATIVA nunca agrupa (é diversificação, não redundância) -- só correlação positiva "
            "acima do limiar. Clusters de 1 robô = \"cluster independente\"."
        )
        limiar_correlacao_cluster = st.number_input(
            "Limiar de correlação para agrupar", min_value=-1.0, max_value=1.0, value=0.5, step=0.05,
            key="portfolio_limiar_correlacao_cluster",
        )
        clusters_risco = clusters_de_risco(largo, limiar_correlacao=limiar_correlacao_cluster)
        st.session_state["portfolio_clusters_risco"] = clusters_risco
        st.table(pd.DataFrame([
            {"Cluster": i + 1, "Robôs": ", ".join(cluster), "Tamanho": len(cluster)}
            for i, cluster in enumerate(clusters_risco)
        ]))

    if len(minimum_margins) == len(diarios):
        limiar_agregado = limiar_agregado_portfolio(
            largo, minimum_margins, percentil_cauda=percentil_cauda,
            fracao_reserva_operacional=fracao_reserva_operacional_pct / 100, increment=increment,
        )
        limiar_agregado_ativo = limiar_agregado.get("limiar_recomendado", limiar_agregado["limiar_bruto"])
        soma_individuais = sum(limiares_individuais.values())
        beneficio = beneficio_diversificacao(soma_individuais, limiar_agregado_ativo)

        with st.expander("Limiar agregado e benefício da diversificação", expanded=True):
            st.caption(
                "Limiar calculado sobre a margem SOMADA e o drawdown da série COMBINADA (não é a "
                "soma dos limiares individuais -- o PDF-fonte avisa explicitamente para não somar)."
            )
            tabela_limiar = {
                "Margem mínima (soma)": limiar_agregado["minimum_margin"],
                "Reserva de cauda (drawdown combinado)": limiar_agregado["tail_drawdown_reserve"],
                "Prêmio por histórico curto": limiar_agregado["uncertainty_premium"],
                "Reserva operacional": limiar_agregado["operational_reserve"],
                "Limiar bruto": limiar_agregado["limiar_bruto"],
            }
            if "limiar_recomendado" in limiar_agregado:
                tabela_limiar["Limiar recomendado (arredondado)"] = limiar_agregado["limiar_recomendado"]
            st.table({"Valor (R$)": {k: fmt(v, moeda=True) for k, v in tabela_limiar.items()}})

            colb1, colb2, colb3 = st.columns(3)
            colb1.metric("Soma dos limiares individuais", fmt(soma_individuais, moeda=True))
            colb2.metric("Limiar agregado do portfólio", fmt(limiar_agregado_ativo, moeda=True))
            colb3.metric(
                "Benefício da diversificação",
                f"{fmt(beneficio['beneficio_rs'], moeda=True)} ({fmt(beneficio['beneficio_pct'] * 100)}%)",
            )

            rlt = rlt_e_risco_portfolio(largo, limiar=limiar_agregado_ativo)
            st.subheader("Retorno sobre o limiar (RLT) do portfólio")
            colr1, colr2 = st.columns(2)
            colr1.metric("RLT acumulado", fmt(rlt["rlt_acumulado"] * 100) + "%")
            colr2.metric("RLT anualizado", fmt(rlt["rlt_anualizado"] * 100) + "%")
            st.caption(
                f"RLT mensal médio/mediano: {fmt(rlt['rlt_mensal_medio']*100)}% / {fmt(rlt['rlt_mensal_mediano']*100)}% · "
                f"RLT móvel 3/6/12 meses: {fmt(rlt['rlt_movel_3']*100)}% / {fmt(rlt['rlt_movel_6']*100)}% / {fmt(rlt['rlt_movel_12']*100)}%"
            )

            st.subheader("Risco normalizado pelo limiar (portfólio)")
            colrr1, colrr2, colrr3, colrr4 = st.columns(4)
            colrr1.metric("MDD / limiar", fmt(rlt["mdd_sobre_limiar"] * 100) + "%")
            colrr2.metric("ES95 / limiar", fmt(rlt["es95_sobre_limiar"] * 100) + "%")
            colrr3.metric("Pior dia / limiar", fmt(rlt["pior_dia_sobre_limiar"] * 100) + "%")
            colrr4.metric("Pior mês / limiar", fmt(rlt["pior_mes_sobre_limiar"] * 100) + "%")
            st.caption(f"Time Under Water máximo (combinado): {agregadas['tuw_max']} pregões.")

        with st.expander("Contribuição marginal por robô", expanded=True):
            st.caption(
                "Para cada robô: recomputa o portfólio COM e SEM ele (o portfólio dos demais) e "
                "mostra a diferença -- lâmina ideal.pdf §13 'Valor marginal do robô'. Lucro é sempre "
                "aditivo (a diferença é sempre o lucro daquele robô sozinho); MDD/ES95/limiar NÃO são "
                "-- a diferença aqui já reflete o efeito da diversificação, não apenas o tamanho do robô."
            )
            contribuicoes = contribuicao_marginal(
                diarios, minimum_margins, percentil_cauda=percentil_cauda,
                fracao_reserva_operacional=fracao_reserva_operacional_pct / 100, increment=increment,
                usar_janela_comum=usar_janela_comum,
            )
            tabela_contribuicao = pd.DataFrame({
                nome: {
                    "Δ Lucro": fmt(c["diferenca_lucro"], moeda=True),
                    "Δ MDD": fmt(c["diferenca_mdd"], moeda=True),
                    "Δ ES95": fmt(c["diferenca_es95"], moeda=True),
                    "Δ Limiar (capital necessário)": fmt(c["diferenca_limiar"], moeda=True),
                }
                for nome, c in contribuicoes.items()
            }).T
            st.table(tabela_contribuicao)

        with st.expander("Contribuição de risco por robô (dentro da carteira atual)"):
            st.caption(
                "Backlog de prompts/otimizacao.pdf -- distinto da contribuição marginal acima "
                "(COM vs. SEM o robô): aqui é uma decomposição de QUEM CAUSOU O QUÊ dentro da "
                "carteira já montada, em três lentes mantidas SEPARADAS (o documento é explícito: "
                "\"não some os três em uma nota arbitrária\"). Cada tabela soma exatamente 100% "
                "entre os robôs -- é o que confirma que nenhuma decomposição está vazando."
            )
            contribuicoes_risco = contribuicao_risco_por_robo(
                diarios, percentil_cauda=percentil_cauda, usar_janela_comum=usar_janela_comum,
            )
            por_robo_risco = contribuicoes_risco["por_robo"]

            st.markdown(
                "**Volatilidade (covariância -- alocação de Euler).** Reabre, só para esta "
                "decomposição analítica, a convenção de variância que a Fronteira de Pareto "
                "(acima) rejeita para ESCOLHER contratos -- decisão discutida com o usuário."
            )
            st.table(pd.DataFrame({
                nome: {
                    "Contribuição (R$)": fmt(c["contribuicao_volatilidade"], moeda=True),
                    "Participação": fmt(c["participacao_volatilidade_pct"]) + "%",
                }
                for nome, c in por_robo_risco.items()
            }).T)

            st.markdown(
                f"**Expected Shortfall (ES{percentil_cauda}).** Resultado médio de cada robô nos "
                f"{contribuicoes_risco['n_dias_cauda_es']} dias que definem o ES{percentil_cauda} "
                f"do portfólio ({fmt(contribuicoes_risco['es_referencia'], moeda=True)})."
            )
            st.table(pd.DataFrame({
                nome: {
                    "Contribuição (R$)": fmt(c["contribuicao_es"], moeda=True),
                    "Participação": fmt(c["participacao_es_pct"]) + "%",
                }
                for nome, c in por_robo_risco.items()
            }).T)

            episodio = contribuicoes_risco["episodio_drawdown_referencia"]
            st.markdown(
                "**Drawdown (pior episódio histórico -- o mesmo que define o MDD acima).** "
                f"{episodio['inicio_pico'].date()} a {episodio['data_fundo'].date()} "
                f"({fmt(episodio['profundidade_rs'], moeda=True)}). \"Lidera a perda\" = fração "
                "dos dias do episódio em que o robô teve o pior resultado do dia."
            )
            st.table(pd.DataFrame({
                nome: {
                    "Contribuição (R$)": fmt(c["contribuicao_drawdown"], moeda=True),
                    "Participação": fmt(c["participacao_drawdown_pct"]) + "%",
                    "Lidera a perda": fmt(c["frequencia_lidera_perda_drawdown"] * 100) + "%",
                }
                for nome, c in por_robo_risco.items()
            }).T)

        with st.expander("Scores individuais separados (retorno / risco / diversificação)"):
            st.caption(
                "Backlog de prompts/otimizacao.pdf §3 -- \"não some imediatamente os três em uma "
                "nota arbitrária\". Decisão confirmada com o usuário: em vez de reduzir cada eixo a "
                "UM número (exigiria inventar uma fórmula de normalização/peso que ninguém pediu), "
                "as três tabelas abaixo mostram as métricas BRUTAS de cada eixo, lado a lado -- "
                "nenhuma agregação nova."
            )
            fracao_melhores_dias = st.number_input(
                "Fração dos melhores dias a excluir (\"resultado sem os melhores dias\")",
                min_value=0.01, max_value=0.50, value=0.05, step=0.01, key="portfolio_scores_fracao_melhores",
            )
            scores = scores_individuais_portfolio(
                diarios, percentil_cauda=percentil_cauda, fracao_melhores_dias=fracao_melhores_dias,
                usar_janela_comum=usar_janela_comum,
            )
            clusters_para_redundancia = st.session_state.get("portfolio_clusters_risco") or []
            redundante = {
                nome: len(next((c for c in clusters_para_redundancia if nome in c), [nome])) > 1
                for nome in scores
            }

            st.markdown("**Retorno**")
            st.table(pd.DataFrame({
                nome: {
                    "Lucro líquido": fmt(s["retorno"]["lucro_liquido"], moeda=True),
                    "Expectativa diária": fmt(s["retorno"]["expectativa_diaria"], moeda=True),
                    "Desvio padrão diário": fmt(s["retorno"]["desvio_padrao_diario"], moeda=True),
                    f"Resultado sem os {fmt(fracao_melhores_dias*100)}% melhores dias": fmt(s["retorno"]["resultado_sem_melhores_dias"], moeda=True),
                }
                for nome, s in scores.items()
            }).T)

            st.markdown("**Risco**")
            st.table(pd.DataFrame({
                nome: {
                    "MDD": fmt(s["risco"]["mdd"], moeda=True),
                    f"ES{percentil_cauda}": fmt(s["risco"]["es"], moeda=True),
                    "Pior dia": fmt(s["risco"]["pior_dia"], moeda=True),
                    "Duração máx. de drawdown (pregões)": s["risco"]["duracao_drawdown_max"],
                    "Maior sequência de perdas": s["risco"]["maior_sequencia_perdas"],
                }
                for nome, s in scores.items()
            }).T)

            st.markdown("**Diversificação**")
            st.caption(
                "\"EA possui função econômica própria ou duplica outro robô?\" -- reusa os clusters "
                "de risco já detectados acima (correlação geral, limiar ajustável): robô sozinho no "
                "seu cluster = função própria; robô num cluster com outros = candidato a redundante "
                "(marcado abaixo se o expander de correlação já foi aberto nesta sessão)."
            )
            st.table(pd.DataFrame({
                nome: {
                    "Correlação média": fmt(s["diversificacao"]["correlacao_media"], 4),
                    "Correlação nos dias negativos": fmt(s["diversificacao"]["correlacao_dias_negativos"], 4),
                    "Coincidência nos piores dias": fmt(s["diversificacao"]["coincidencia_piores_dias"], 4),
                    "Contribuição ao drawdown do portfólio": fmt(s["diversificacao"]["contribuicao_drawdown_portfolio_pct"]) + "%",
                    "Retorno quando os outros perdem": fmt(s["diversificacao"]["retorno_quando_outros_perdem"], moeda=True),
                    "Possível redundância (mesmo cluster)": "Sim" if redundante.get(nome) else "Não",
                }
                for nome, s in scores.items()
            }).T)

        with st.expander("Otimização de portfólio (busca discreta)"):
            st.caption(
                "Tarefa 10.8 -- busca discreta (não otimização contínua, pedido explícito do "
                "PDF-fonte) sobre combinações de número de contratos por robô. 0 contratos é um "
                "candidato válido -- excluir um robô inteiramente do portfólio também é testado "
                "quando \"permitir excluir\" está marcado (barra lateral, por robô). Custo mensal "
                "não entra nesta busca (simplificação documentada -- ver docstring de "
                "tradefolio.portfolio.buscar_combinacoes_portfolio)."
            )

            n_total_candidatos = 1
            for lista in candidatos_contratos.values():
                n_total_candidatos *= len(lista)
            st.caption(f"{n_total_candidatos} combinações a testar (ajuste os candidatos por robô na barra lateral).")

            # Busca (cara) e seleção por objetivo (barata) são passos
            # separados -- pedido de acompanhamento do usuário: rodar a
            # busca inteira de novo a cada troca de objetivo faria a UI
            # parecer travada sem necessidade, já que a única coisa que
            # muda é a ordenação/filtro de uma tabela já calculada.
            chave_busca_atual = (
                tuple(sorted((n, tuple(c)) for n, c in candidatos_contratos.items())),
                tuple(sorted(margens_por_contrato.items())),
                percentil_cauda, fracao_reserva_operacional_pct, increment, usar_janela_comum,
            )
            busca_desatualizada = st.session_state.get("portfolio_chave_busca") != chave_busca_atual

            if st.button("Buscar combinações", icon=":material/search:"):
                with st.spinner(f"Calculando {n_total_candidatos} combinações..."):
                    try:
                        resultados_busca = buscar_combinacoes_portfolio(
                            diarios_referencia, margens_por_contrato, candidatos_contratos,
                            percentil_cauda=percentil_cauda,
                            fracao_reserva_operacional=fracao_reserva_operacional_pct / 100,
                            increment=increment, usar_janela_comum=usar_janela_comum,
                        )
                    except ValueError as erro:
                        st.error(str(erro))
                    else:
                        st.session_state["portfolio_resultados_busca"] = resultados_busca
                        st.session_state["portfolio_chave_busca"] = chave_busca_atual
                        busca_desatualizada = False

            resultados_busca = st.session_state.get("portfolio_resultados_busca")
            if resultados_busca is None:
                st.info(
                    "Clique em \"Buscar combinações\" para calcular -- pode levar alguns segundos "
                    "dependendo do número de combinações. Depois disso, trocar o objetivo abaixo "
                    "só reordena a tabela já calculada, sem recalcular nada."
                )
            else:
                if busca_desatualizada:
                    st.warning(
                        "Os candidatos, margens ou escopo temporal mudaram desde a última busca -- "
                        "a tabela abaixo ainda reflete a busca anterior. Clique em \"Buscar "
                        "combinações\" de novo para atualizar."
                    )

                objetivo_rotulo = st.radio(
                    "Objetivo (reordena a tabela já calculada -- não recalcula a busca)",
                    ["Maximizar RLT", "Minimizar risco (|MDD| / limiar)", "Maximizar lucro (com limite de MDD)"],
                    key="portfolio_objetivo_otimizacao",
                )
                objetivo_map = {
                    "Maximizar RLT": "maximizar_rlt",
                    "Minimizar risco (|MDD| / limiar)": "minimizar_mdd_sobre_limiar",
                    "Maximizar lucro (com limite de MDD)": "maximizar_lucro_com_limite_mdd",
                }
                objetivo_otimizacao = objetivo_map[objetivo_rotulo]

                limite_mdd = None
                if objetivo_otimizacao == "maximizar_lucro_com_limite_mdd":
                    limite_mdd = st.number_input(
                        "Limite de MDD (R$, negativo -- ex. -5000)", max_value=0.0, value=None,
                        step=500.0, key="portfolio_limite_mdd",
                        help="Só combinações já calculadas cujo MDD não seja pior que este valor "
                             "entram na tabela -- obrigatório para este objetivo, nunca inventado.",
                    )

                pode_selecionar = objetivo_otimizacao != "maximizar_lucro_com_limite_mdd" or limite_mdd is not None
                if not pode_selecionar:
                    st.info("Informe o limite de MDD acima para ver a tabela ordenada.")
                else:
                    try:
                        resultado_otimizacao = selecionar_melhores_combinacoes(
                            resultados_busca, objetivo=objetivo_otimizacao, limite_mdd=limite_mdd,
                        )
                    except ValueError as erro:
                        st.error(str(erro))
                    else:
                        st.caption(
                            f"{resultado_otimizacao['n_combinacoes_testadas']} de "
                            f"{len(resultados_busca)} combinações calculadas satisfazem este "
                            "objetivo -- quanto mais tentativas, maior o risco de a melhor "
                            "combinação ser sorte de amostra, não edge real (o PDF-fonte pede para "
                            "nunca reportar só o melhor resultado; por isso as top 10 aparecem)."
                        )
                        tabela_otimizacao = pd.DataFrame([
                            {
                                **{f"Contratos {nome}": v for nome, v in r["alocacao"].items()},
                                "Lucro": fmt(r["lucro_total"], moeda=True),
                                "MDD": fmt(r["mdd"], moeda=True),
                                "ES95": fmt(r["es_95"], moeda=True),
                                "Limiar": fmt(r["limiar_ativo"], moeda=True),
                                "Score": fmt(r["score"], 4),
                            }
                            for r in resultado_otimizacao["melhores"]
                        ])
                        st.table(tabela_otimizacao)

                st.subheader("Fronteira de Pareto (discreta)")
                st.caption(
                    "Combinações já calculadas que NENHUMA outra combinação supera nos dois eixos "
                    "ao mesmo tempo -- não recalcula nada, só reprocessa a busca acima. Markowitz "
                    "(fronteira contínua, variância como risco) não encaixa aqui: contratos são "
                    "discretos e este app já usa MDD/ES/limiar como risco, não variância -- ver "
                    "docstring de tradefolio.portfolio.fronteira_pareto para a discussão completa."
                )
                eixos_pareto = {
                    "Lucro vs MDD": ("lucro_total", "mdd"),
                    "Lucro vs ES95": ("lucro_total", "es_95"),
                    "RLT vs MDD/limiar": ("rlt_acumulado", "mdd_sobre_limiar"),
                }
                par_escolhido = st.radio(
                    "Eixos", list(eixos_pareto.keys()), key="portfolio_eixos_pareto", horizontal=True,
                )
                eixo_retorno, eixo_risco = eixos_pareto[par_escolhido]

                st.caption(
                    "Epsilon-Pareto (backlog): combinações dentro dessa tolerância uma da outra "
                    "nos dois eixos contam como \"economicamente iguais\" e colapsam num só "
                    "representante -- 0% em ambos preserva a fronteira estrita (só dedup de "
                    "empates exatos). Valores iniciais (1%/2%) são o exemplo do documento-fonte, "
                    "não um padrão fixo -- ajustáveis ao vivo."
                )
                coltol1, coltol2 = st.columns(2)
                tolerancia_retorno_pct = coltol1.number_input(
                    "Tolerância no retorno (%)", min_value=0.0, value=1.0, step=0.5,
                    key="portfolio_pareto_tolerancia_retorno",
                )
                tolerancia_risco_pct = coltol2.number_input(
                    "Tolerância no risco (%)", min_value=0.0, value=2.0, step=0.5,
                    key="portfolio_pareto_tolerancia_risco",
                )

                fronteira = fronteira_pareto(
                    resultados_busca, eixo_retorno, eixo_risco,
                    tolerancia_retorno_pct=tolerancia_retorno_pct, tolerancia_risco_pct=tolerancia_risco_pct,
                )
                ids_fronteira = {id(r) for r in fronteira}
                rotulo_retorno, rotulo_risco = par_escolhido.split(" vs ")
                grafico_pareto = pd.DataFrame([
                    {
                        rotulo_risco: r[eixo_risco],
                        rotulo_retorno: r[eixo_retorno],
                        "Na fronteira": "Sim" if id(r) in ids_fronteira else "Não",
                    }
                    for r in resultados_busca
                ])
                # st.scatter_chart (Altair/Vega-Lite, SVG) renders one DOM node
                # per ponto -- com milhares de combinações isso travava o scroll
                # da página (pedido de acompanhamento do usuário). plotly com
                # render_mode="webgl" desenha em canvas/GPU em vez de SVG, sem
                # precisar reduzir os pontos mostrados.
                fig_pareto = px.scatter(
                    grafico_pareto, x=rotulo_risco, y=rotulo_retorno,
                    color="Na fronteira", render_mode="webgl",
                )
                st.plotly_chart(fig_pareto, width="stretch")

                tabela_pareto = pd.DataFrame([
                    {
                        **{f"Contratos {nome}": v for nome, v in r["alocacao"].items()},
                        rotulo_retorno: fmt(r[eixo_retorno], 4 if "rlt" in eixo_retorno else 2),
                        rotulo_risco: fmt(r[eixo_risco], 4 if "limiar" in eixo_risco else 2),
                        "Combinações agrupadas (epsilon)": len(r.get("_agrupados", [])),
                    }
                    for r in fronteira
                ])
                st.table(tabela_pareto)
                st.caption(
                    f"{len(fronteira)} de {len(resultados_busca)} combinações calculadas estão na "
                    "fronteira -- as demais têm pelo menos uma outra combinação igual ou melhor nos "
                    "dois eixos ao mesmo tempo (ou foram agrupadas por tolerância epsilon a um "
                    "representante acima -- ver abaixo quais)."
                )
                total_agrupadas = sum(len(r.get("_agrupados", [])) for r in fronteira)
                if total_agrupadas:
                    with st.expander(f"Ver as {total_agrupadas} combinações agrupadas por tolerância (não aparecem na tabela acima)"):
                        tabela_agrupadas = pd.DataFrame([
                            {
                                "Representante": ", ".join(f"{nome}={v}" for nome, v in r["alocacao"].items()),
                                **{f"Contratos {nome}": v for nome, v in agrupado["alocacao"].items()},
                                rotulo_retorno: fmt(agrupado[eixo_retorno], 4 if "rlt" in eixo_retorno else 2),
                                rotulo_risco: fmt(agrupado[eixo_risco], 4 if "limiar" in eixo_risco else 2),
                            }
                            for r in fronteira
                            for agrupado in r.get("_agrupados", [])
                        ])
                        st.table(tabela_agrupadas)

                st.subheader("Curva de limiares (MDD máximo -> melhor RLT)")
                st.caption(
                    "Backlog de prompts/otimizacao.pdf §7: em vez de um único MDD máximo, gera a "
                    "curva inteira -- para cada limite, a carteira já calculada de maior RLT entre "
                    "as que não violam esse limite. Distinto do objetivo \"Maximizar lucro (com "
                    "limite de MDD)\" acima, que otimiza LUCRO sob a mesma restrição -- aqui o "
                    "critério é RLT, não lucro bruto."
                )
                limites_texto = st.text_input(
                    "Limites de MDD (R$, negativos, separados por vírgula)",
                    value="-2500,-5000,-7500,-10000", key="portfolio_curva_limites_mdd",
                )
                try:
                    limites_mdd = [float(x.strip()) for x in limites_texto.split(",") if x.strip()]
                except ValueError:
                    st.error("Não consegui interpretar os limites -- use números separados por vírgula.")
                else:
                    curva = curva_limiares_mdd(resultados_busca, limites_mdd)
                    tabela_curva = pd.DataFrame([
                        {
                            "Limite de MDD": fmt(ponto["limite_mdd"], moeda=True),
                            "Combinações válidas": ponto["n_combinacoes_validas"],
                            **(
                                {
                                    **{f"Contratos {nome}": v for nome, v in ponto["melhor"]["alocacao"].items()},
                                    "RLT": fmt(ponto["melhor"]["rlt_acumulado"], 4),
                                    "Lucro": fmt(ponto["melhor"]["lucro_total"], moeda=True),
                                    "MDD": fmt(ponto["melhor"]["mdd"], moeda=True),
                                }
                                if ponto["melhor"] is not None
                                else {"RLT": "-- (nenhuma combinação satisfaz este limite)"}
                            ),
                        }
                        for ponto in curva
                    ])
                    st.table(tabela_curva)

        with st.expander("Otimização de portfólio (busca com filtros de sobrevivência) [novo -- compare com a busca acima]"):
            st.caption(
                "Backlog de prompts/otimizacao.pdf -- pedido explícito do usuário: seção NOVA e "
                "paralela à busca acima (não substitui/recalcula nada nela), pensada para "
                "comparação lado a lado. `buscar_combinacoes_portfolio_com_filtros` reusa o MESMO "
                "cálculo por combinação; só muda quantas combinações chegam até ele, em 3 camadas "
                "baratas ANTES do cálculo caro: (1) dedupe de composição/escala -- [2,2] é a MESMA "
                "composição que [1,1] em outra escala, mantém só a de menor escala; (2) mínimo de "
                "robôs ativos e margem máxima agregada (baratos, só olham a alocação); (3) pior dia "
                "histórico máximo (não é um cenário estressado/Monte Carlo -- isso é backlog "
                "separado, para uma fase de finalistas). Com tudo desligado, reproduz exatamente a "
                "busca acima."
            )

            colf1, colf2 = st.columns(2)
            deduplicar_composicao = colf1.checkbox(
                "Deduplicar composição/escala", value=True, key="portfolio_filtros_dedupe",
                help="Descarta combinações que são apenas uma versão escalada de outra já testada "
                     "(ex. [2,2] vs [1,1]) -- mantém só a de menor escala.",
            )
            min_robos_ativos = colf2.number_input(
                "Mínimo de robôs ativos", min_value=0, max_value=len(candidatos_contratos),
                value=0, step=1, key="portfolio_filtros_min_ativos",
            )
            colf3, colf4 = st.columns(2)
            margem_maxima_filtro = colf3.number_input(
                "Margem agregada máxima (R$, vazio = sem limite)", min_value=0.0, value=None,
                step=1000.0, key="portfolio_filtros_margem_maxima",
            )
            perda_diaria_maxima_filtro = colf4.number_input(
                "Pior dia histórico aceitável (R$, negativo, vazio = sem limite)",
                max_value=0.0, value=None, step=500.0, key="portfolio_filtros_perda_diaria",
            )

            clusters_risco_filtro = st.session_state.get("portfolio_clusters_risco")
            colf5, colf6 = st.columns(2)
            usar_limite_cluster = colf5.checkbox(
                "Limitar contratos por cluster de risco", value=False,
                key="portfolio_filtros_usar_cluster",
                help="Usa os clusters já detectados no expander \"Correlação entre robôs\" acima "
                     "(grafo de limiar + componentes conexos sobre a correlação geral).",
            )
            max_contratos_por_cluster_filtro = colf6.number_input(
                "Máximo de contratos por cluster", min_value=1, value=10, step=1,
                key="portfolio_filtros_max_cluster", disabled=not usar_limite_cluster,
            )
            if usar_limite_cluster and clusters_risco_filtro:
                st.caption(
                    "Clusters em uso: " + " | ".join(", ".join(c) for c in clusters_risco_filtro)
                )
            clusters_para_busca = clusters_risco_filtro if usar_limite_cluster else None
            max_cluster_para_busca = max_contratos_por_cluster_filtro if usar_limite_cluster else None

            chave_busca_filtros_atual = (
                tuple(sorted((n, tuple(c)) for n, c in candidatos_contratos.items())),
                tuple(sorted(margens_por_contrato.items())),
                percentil_cauda, fracao_reserva_operacional_pct, increment, usar_janela_comum,
                deduplicar_composicao, min_robos_ativos, margem_maxima_filtro, perda_diaria_maxima_filtro,
                usar_limite_cluster, max_contratos_por_cluster_filtro,
                tuple(tuple(c) for c in (clusters_risco_filtro or [])),
            )
            busca_filtros_desatualizada = (
                st.session_state.get("portfolio_chave_busca_filtros") != chave_busca_filtros_atual
            )

            if st.button("Buscar combinações (com filtros)", icon=":material/filter_alt:"):
                with st.spinner("Calculando..."):
                    try:
                        resultado_busca_filtros = buscar_combinacoes_portfolio_com_filtros(
                            diarios_referencia, margens_por_contrato, candidatos_contratos,
                            percentil_cauda=percentil_cauda,
                            fracao_reserva_operacional=fracao_reserva_operacional_pct / 100,
                            increment=increment, usar_janela_comum=usar_janela_comum,
                            deduplicar_composicao=deduplicar_composicao,
                            min_robos_ativos=int(min_robos_ativos), margem_maxima=margem_maxima_filtro,
                            perda_diaria_maxima=perda_diaria_maxima_filtro,
                            clusters=clusters_para_busca, max_contratos_por_cluster=max_cluster_para_busca,
                        )
                    except ValueError as erro:
                        st.error(str(erro))
                    else:
                        st.session_state["portfolio_resultado_busca_filtros"] = resultado_busca_filtros
                        st.session_state["portfolio_chave_busca_filtros"] = chave_busca_filtros_atual
                        busca_filtros_desatualizada = False

            resultado_busca_filtros = st.session_state.get("portfolio_resultado_busca_filtros")
            if resultado_busca_filtros is None:
                st.info("Clique em \"Buscar combinações (com filtros)\" para calcular.")
            else:
                if busca_filtros_desatualizada:
                    st.warning(
                        "Os candidatos, margens, escopo temporal ou filtros mudaram desde a última "
                        "busca -- os resultados abaixo ainda refletem a busca anterior."
                    )

                colr1, colr2, colr3, colr4, colr5, colr6 = st.columns(6)
                colr1.metric("Combinações totais", resultado_busca_filtros["n_combinacoes_totais"])
                colr2.metric("Puladas (dedupe)", resultado_busca_filtros["n_puladas_composicao_duplicada"])
                colr3.metric("Puladas (sobrevivência)", resultado_busca_filtros["n_puladas_sobrevivencia"])
                colr4.metric("Puladas (cluster)", resultado_busca_filtros["n_puladas_cluster"])
                colr5.metric("Puladas (pior dia)", resultado_busca_filtros["n_puladas_perda_diaria"])
                colr6.metric("Avaliadas", resultado_busca_filtros["n_avaliadas"])

                resultados_busca_f = resultado_busca_filtros["resultados"]
                objetivo_rotulo_f = st.radio(
                    "Objetivo (reordena a tabela já calculada -- não recalcula a busca)",
                    ["Maximizar RLT", "Minimizar risco (|MDD| / limiar)", "Maximizar lucro (com limite de MDD)"],
                    key="portfolio_objetivo_otimizacao_filtros",
                )
                objetivo_map_f = {
                    "Maximizar RLT": "maximizar_rlt",
                    "Minimizar risco (|MDD| / limiar)": "minimizar_mdd_sobre_limiar",
                    "Maximizar lucro (com limite de MDD)": "maximizar_lucro_com_limite_mdd",
                }
                objetivo_otimizacao_f = objetivo_map_f[objetivo_rotulo_f]

                limite_mdd_f = None
                if objetivo_otimizacao_f == "maximizar_lucro_com_limite_mdd":
                    limite_mdd_f = st.number_input(
                        "Limite de MDD (R$, negativo -- ex. -5000)", max_value=0.0, value=None,
                        step=500.0, key="portfolio_limite_mdd_filtros",
                    )

                pode_selecionar_f = (
                    objetivo_otimizacao_f != "maximizar_lucro_com_limite_mdd" or limite_mdd_f is not None
                )
                if not pode_selecionar_f:
                    st.info("Informe o limite de MDD acima para ver a tabela ordenada.")
                elif not resultados_busca_f:
                    st.info("Nenhuma combinação sobreviveu aos filtros.")
                else:
                    try:
                        resultado_otimizacao_f = selecionar_melhores_combinacoes(
                            resultados_busca_f, objetivo=objetivo_otimizacao_f, limite_mdd=limite_mdd_f,
                        )
                    except ValueError as erro:
                        st.error(str(erro))
                    else:
                        tabela_otimizacao_f = pd.DataFrame([
                            {
                                **{f"Contratos {nome}": v for nome, v in r["alocacao"].items()},
                                "Lucro": fmt(r["lucro_total"], moeda=True),
                                "MDD": fmt(r["mdd"], moeda=True),
                                "ES95": fmt(r["es_95"], moeda=True),
                                "Limiar": fmt(r["limiar_ativo"], moeda=True),
                                "Score": fmt(r["score"], 4),
                            }
                            for r in resultado_otimizacao_f["melhores"]
                        ])
                        st.table(tabela_otimizacao_f)

                    st.subheader("Fronteira de Pareto (discreta, sobre a busca filtrada)")
                    eixos_pareto_f = {
                        "Lucro vs MDD": ("lucro_total", "mdd"),
                        "Lucro vs ES95": ("lucro_total", "es_95"),
                        "RLT vs MDD/limiar": ("rlt_acumulado", "mdd_sobre_limiar"),
                    }
                    par_escolhido_f = st.radio(
                        "Eixos", list(eixos_pareto_f.keys()), key="portfolio_eixos_pareto_filtros", horizontal=True,
                    )
                    eixo_retorno_f, eixo_risco_f = eixos_pareto_f[par_escolhido_f]

                    coltol1_f, coltol2_f = st.columns(2)
                    tolerancia_retorno_pct_f = coltol1_f.number_input(
                        "Tolerância no retorno (%)", min_value=0.0, value=1.0, step=0.5,
                        key="portfolio_pareto_tolerancia_retorno_filtros",
                    )
                    tolerancia_risco_pct_f = coltol2_f.number_input(
                        "Tolerância no risco (%)", min_value=0.0, value=2.0, step=0.5,
                        key="portfolio_pareto_tolerancia_risco_filtros",
                    )

                    fronteira_f = fronteira_pareto(
                        resultados_busca_f, eixo_retorno_f, eixo_risco_f,
                        tolerancia_retorno_pct=tolerancia_retorno_pct_f, tolerancia_risco_pct=tolerancia_risco_pct_f,
                    )
                    ids_fronteira_f = {id(r) for r in fronteira_f}
                    rotulo_retorno_f, rotulo_risco_f = par_escolhido_f.split(" vs ")
                    grafico_pareto_f = pd.DataFrame([
                        {
                            rotulo_risco_f: r[eixo_risco_f],
                            rotulo_retorno_f: r[eixo_retorno_f],
                            "Na fronteira": "Sim" if id(r) in ids_fronteira_f else "Não",
                        }
                        for r in resultados_busca_f
                    ])
                    fig_pareto_f = px.scatter(
                        grafico_pareto_f, x=rotulo_risco_f, y=rotulo_retorno_f,
                        color="Na fronteira", render_mode="webgl",
                    )
                    st.plotly_chart(fig_pareto_f, width="stretch")

                    tabela_pareto_f = pd.DataFrame([
                        {
                            **{f"Contratos {nome}": v for nome, v in r["alocacao"].items()},
                            rotulo_retorno_f: fmt(r[eixo_retorno_f], 4 if "rlt" in eixo_retorno_f else 2),
                            rotulo_risco_f: fmt(r[eixo_risco_f], 4 if "limiar" in eixo_risco_f else 2),
                            "Combinações agrupadas (epsilon)": len(r.get("_agrupados", [])),
                        }
                        for r in fronteira_f
                    ])
                    st.table(tabela_pareto_f)
                    st.caption(
                        f"{len(fronteira_f)} de {len(resultados_busca_f)} combinações avaliadas estão "
                        "na fronteira (ou foram agrupadas por tolerância epsilon -- ver abaixo quais)."
                    )
                    total_agrupadas_f = sum(len(r.get("_agrupados", [])) for r in fronteira_f)
                    if total_agrupadas_f:
                        with st.expander(f"Ver as {total_agrupadas_f} combinações agrupadas por tolerância (não aparecem na tabela acima)"):
                            tabela_agrupadas_f = pd.DataFrame([
                                {
                                    "Representante": ", ".join(f"{nome}={v}" for nome, v in r["alocacao"].items()),
                                    **{f"Contratos {nome}": v for nome, v in agrupado["alocacao"].items()},
                                    rotulo_retorno_f: fmt(agrupado[eixo_retorno_f], 4 if "rlt" in eixo_retorno_f else 2),
                                    rotulo_risco_f: fmt(agrupado[eixo_risco_f], 4 if "limiar" in eixo_risco_f else 2),
                                }
                                for r in fronteira_f
                                for agrupado in r.get("_agrupados", [])
                            ])
                            st.table(tabela_agrupadas_f)

        with st.expander("Robustez local (vizinhança ±1 contrato)"):
            st.caption(
                "Backlog de prompts/otimizacao.pdf §9 -- para uma carteira-base, testa vizinhas a "
                "±1 contrato por robô e transferências de 1 contrato entre pares de robôs. "
                "\"Se a carteira é excelente mas todas as vizinhas são ruins, ela provavelmente "
                "explora uma coincidência histórica. Se a carteira e as vizinhas são boas, é um "
                "platô robusto\" -- esta seção não decide isso por você, só mostra os números lado "
                "a lado."
            )
            cols_base = st.columns(len(diarios_referencia))
            alocacao_base_vizinhanca = {}
            for col, nome in zip(cols_base, diarios_referencia.keys()):
                alocacao_base_vizinhanca[nome] = col.number_input(
                    f"{nome}: contratos (base)", min_value=0,
                    value=resumo_robos.get(nome, {}).get("n_contratos", 1),
                    step=1, key=f"portfolio_vizinhanca_base::{nome}",
                )
            incluir_transferencias = st.checkbox(
                "Incluir transferências entre robôs (-1 num, +1 noutro)", value=True,
                key="portfolio_vizinhanca_transferencias",
            )

            if st.button("Testar vizinhança", icon=":material/hub:"):
                try:
                    resultado_vizinhanca = vizinhanca_local(
                        alocacao_base_vizinhanca, diarios_referencia, margens_por_contrato,
                        percentil_cauda=percentil_cauda,
                        fracao_reserva_operacional=fracao_reserva_operacional_pct / 100,
                        increment=increment, usar_janela_comum=usar_janela_comum,
                        incluir_transferencias=incluir_transferencias,
                    )
                except ValueError as erro:
                    st.error(str(erro))
                else:
                    st.session_state["portfolio_resultado_vizinhanca"] = resultado_vizinhanca

            resultado_vizinhanca = st.session_state.get("portfolio_resultado_vizinhanca")
            if resultado_vizinhanca is None:
                st.info("Clique em \"Testar vizinhança\" para calcular a base e suas vizinhas.")
            else:
                base = resultado_vizinhanca["base"]
                linhas = [{
                    "Tipo": "BASE",
                    **{f"Contratos {nome}": v for nome, v in base["alocacao"].items()},
                    "RLT": fmt(base["rlt_acumulado"], 4),
                    "Δ RLT vs. base": "--",
                    "Lucro": fmt(base["lucro_total"], moeda=True),
                    "MDD": fmt(base["mdd"], moeda=True),
                }]
                for v in resultado_vizinhanca["vizinhas"]:
                    linhas.append({
                        "Tipo": v["tipo"],
                        **{f"Contratos {nome}": val for nome, val in v["alocacao"].items()},
                        "RLT": fmt(v["rlt_acumulado"], 4),
                        "Δ RLT vs. base": fmt(v["rlt_acumulado"] - base["rlt_acumulado"], 4),
                        "Lucro": fmt(v["lucro_total"], moeda=True),
                        "MDD": fmt(v["mdd"], moeda=True),
                    })
                st.table(pd.DataFrame(linhas))
                st.caption(
                    f"{len(resultado_vizinhanca['vizinhas'])} vizinhas avaliadas (algumas podem ter "
                    "sido omitidas por não terem janela comum ou ficarem degeneradas -- 0 contratos "
                    "em todos os robôs)."
                )

        with st.expander("Funil de seleção (4 camadas)"):
            st.caption(
                "Backlog de prompts/otimizacao.pdf §6 -- \"não escolheria entre 'máximo RLT' e "
                "'mínimo MDD'. Usaria uma sequência\": (1) sobrevivência -- reusa os mesmos filtros "
                "configurados acima em \"busca com filtros de sobrevivência\"; (2) eficiência -- "
                "ranqueia por RLT/|MDD| e mantém os N melhores; (3) robustez -- roda a vizinhança "
                "±1 (já existente) em cada um, elimina quem a MÉDIA das vizinhas afunda mais que a "
                "tolerância abaixo da base (sem walk-forward ainda, é a única evidência de robustez "
                "disponível); (4) simplicidade -- desempate por menos contratos totais. Cada camada "
                "mostra os avaliados E os sobreviventes, nunca esconde o que foi descartado."
            )
            colfu1, colfu2 = st.columns(2)
            top_n_eficiencia = colfu1.number_input(
                "Quantos avançam da camada 2 (eficiência) para a 3 (robustez)",
                min_value=1, max_value=100, value=20, step=1, key="portfolio_funil_top_n",
                help="Cada um roda uma vizinhança ±1 completa na camada 3 -- valores altos ficam mais lentos.",
            )
            tolerancia_robustez_pct = colfu2.number_input(
                "Tolerância de robustez (%) -- média das vizinhas não pode afundar mais que isto",
                min_value=0.0, value=20.0, step=5.0, key="portfolio_funil_tolerancia",
            )
            incluir_transferencias_robustez = st.checkbox(
                "Incluir transferências na checagem de robustez", value=True,
                key="portfolio_funil_transferencias",
            )

            if st.button("Rodar funil", icon=":material/filter_list:"):
                with st.spinner("Calculando (camada 3 roda uma vizinhança por candidato)..."):
                    try:
                        resultado_funil = funil_selecao_portfolio(
                            diarios_referencia, margens_por_contrato, candidatos_contratos,
                            percentil_cauda=percentil_cauda,
                            fracao_reserva_operacional=fracao_reserva_operacional_pct / 100,
                            increment=increment, usar_janela_comum=usar_janela_comum,
                            deduplicar_composicao=deduplicar_composicao,
                            min_robos_ativos=int(min_robos_ativos), margem_maxima=margem_maxima_filtro,
                            perda_diaria_maxima=perda_diaria_maxima_filtro,
                            clusters=clusters_para_busca, max_contratos_por_cluster=max_cluster_para_busca,
                            top_n_eficiencia=int(top_n_eficiencia),
                            tolerancia_robustez_pct=tolerancia_robustez_pct,
                            incluir_transferencias_robustez=incluir_transferencias_robustez,
                        )
                    except ValueError as erro:
                        st.error(str(erro))
                    else:
                        st.session_state["portfolio_resultado_funil"] = resultado_funil

            resultado_funil = st.session_state.get("portfolio_resultado_funil")
            if resultado_funil is None:
                st.info("Clique em \"Rodar funil\" para calcular.")
            else:
                camada1 = resultado_funil["camada1_sobrevivencia"]
                camada2 = resultado_funil["camada2_eficiencia"]
                camada3 = resultado_funil["camada3_robustez"]
                camada4 = resultado_funil["camada4_simplicidade"]

                colfr1, colfr2, colfr3, colfr4 = st.columns(4)
                colfr1.metric("Camada 1: sobrevivência", camada1["n_avaliadas"])
                colfr2.metric("Camada 2: eficiência", len(camada2))
                colfr3.metric("Camada 3: robustez", len(camada3["sobreviventes"]))
                colfr4.metric("Camada 4: final", len(camada4))

                st.markdown("**Camada 4 -- resultado final (ordenado por eficiência, desempate por menos contratos)**")
                if not camada4:
                    st.warning("Nenhuma combinação sobreviveu a todas as camadas -- afrouxe os filtros/tolerância acima.")
                else:
                    st.table(pd.DataFrame([
                        {
                            **{f"Contratos {nome}": v for nome, v in r["alocacao"].items()},
                            "Total contratos": r["total_contratos"],
                            "RLT": fmt(r["rlt_acumulado"], 4),
                            "MDD": fmt(r["mdd"], moeda=True),
                            "Eficiência (RLT/|MDD|)": fmt(r["eficiencia_rlt_mdd"], 6),
                            "Média RLT vizinhas": fmt(r["media_rlt_vizinhas"], 4) if r["media_rlt_vizinhas"] is not None else "--",
                        }
                        for r in camada4
                    ]))

                with st.expander(f"Ver os {len(camada3['avaliados'])} avaliados na camada 3 (robustez) -- inclui os eliminados"):
                    st.table(pd.DataFrame([
                        {
                            **{f"Contratos {nome}": v for nome, v in r["alocacao"].items()},
                            "RLT (base)": fmt(r["rlt_acumulado"], 4),
                            "Média RLT vizinhas": fmt(r["media_rlt_vizinhas"], 4) if r["media_rlt_vizinhas"] is not None else "--",
                            "Robusto": "Sim" if r["robusto"] else "Não",
                        }
                        for r in camada3["avaliados"]
                    ]))

                if camada4:
                    st.markdown("**Monte Carlo nos finalistas (fase 2 -- só nos sobreviventes acima)**")
                    st.caption(
                        "Backlog de prompts/otimizacao.pdf §10 -- \"o Monte Carlo entra DEPOIS da "
                        "triagem, não para rodar profundamente em todas as combinações\". Roda só "
                        "nos poucos sobreviventes da camada 4, não na grade inteira."
                    )
                    colmc_f1, colmc_f2, colmc_f3 = st.columns(3)
                    esquema_mc_finalistas = colmc_f1.selectbox(
                        "Esquema", ["Bootstrap por blocos", "Embaralhamento simples"],
                        key="portfolio_funil_mc_esquema",
                    )
                    n_trajetorias_finalistas = colmc_f2.number_input(
                        "Trajetórias por finalista", min_value=100, max_value=20000, value=1000, step=100,
                        key="portfolio_funil_mc_n_trajetorias",
                    )
                    seed_finalistas = colmc_f3.number_input(
                        "Seed (vazio = aleatória)", min_value=0, value=None, step=1,
                        key="portfolio_funil_mc_seed",
                    )
                    choques_finalistas = st.multiselect(
                        "Choques (esquema C parcial)",
                        ["pior_dia_repetido", "perda_simultanea"],
                        key="portfolio_funil_mc_choques",
                        help="\"slippage dobrado\" e \"correlação elevada artificialmente\" ficam de "
                             "fora -- mesmo raciocínio que excluiu a degradação de edge (esquema D).",
                    )

                    if st.button("Rodar Monte Carlo nos finalistas", icon=":material/science:"):
                        with st.spinner(f"Rodando Monte Carlo em {len(camada4)} finalistas..."):
                            resultado_mc_finalistas = robustez_dos_finalistas(
                                diarios_referencia, margens_por_contrato, camada4,
                                esquema="bloco" if esquema_mc_finalistas == "Bootstrap por blocos" else "embaralhamento",
                                tamanho_bloco=tamanho_bloco_pf, n_trajetorias=int(n_trajetorias_finalistas),
                                horizonte=int(horizonte_pf), seed=int(seed_finalistas) if seed_finalistas is not None else None,
                                incluir_dias_sem_operacao=incluir_sem_operacao_pf, usar_janela_comum=usar_janela_comum,
                                choques=choques_finalistas,
                            )
                        st.session_state["portfolio_resultado_mc_finalistas"] = resultado_mc_finalistas

                    resultado_mc_finalistas = st.session_state.get("portfolio_resultado_mc_finalistas")
                    if resultado_mc_finalistas:
                        st.table(pd.DataFrame([
                            {
                                **{f"Contratos {nome}": v for nome, v in r["alocacao"].items()},
                                "Lucro P50": fmt(r["lucro_p50"], moeda=True),
                                "MDD P95": fmt(r["mdd_p95"], moeda=True),
                                "CDaR 95": fmt(r["cdar_95"], moeda=True),
                                "P(recup. 60p)": fmt(r["probabilidade_recuperacao_60"] * 100) + "%",
                                "P(prejuízo)": fmt(r["probabilidade_prejuizo"] * 100) + "%",
                            }
                            for r in resultado_mc_finalistas
                        ]))

        with st.expander("Shortlist final (perfis nomeados)"):
            st.caption(
                "Backlog de prompts/otimizacao.pdf §18 -- \"permitir ao usuário ver se a "
                "otimização complexa realmente supera referências simples\". Em vez de uma única "
                "tabela ordenada, um conjunto pequeno e nomeado: Minimum Risk, Growth, Balanced "
                "(joelho da Fronteira de Pareto), Handcrafted Risk (peso igual por CLUSTER, não "
                "por robô -- evita que vários robôs correlacionados dominem só por serem vários), "
                "mais os benchmarks fixos Carteira atual / Contratos iguais / Risco inverso. "
                "\"Most Robust\" deliberadamente não incluído -- depende de walk-forward, que ainda "
                "não existe neste projeto."
            )
            resultados_para_shortlist = st.session_state.get("portfolio_resultados_busca")
            if resultados_para_shortlist is None:
                st.info(
                    "Rode a \"Otimização de portfólio (busca discreta)\" acima primeiro -- a "
                    "shortlist reusa esses resultados, não recalcula nada."
                )
            else:
                total_atual = sum(resumo_robos.get(nome, {}).get("n_contratos", 0) for nome in diarios_referencia)
                colsl1, colsl2, colsl3 = st.columns(3)
                total_contratos_benchmark = colsl1.number_input(
                    "Total de contratos (benchmarks)", min_value=1, value=max(total_atual, 1), step=1,
                    key="portfolio_shortlist_total",
                )
                retorno_minimo_sl = colsl2.number_input(
                    "Retorno mínimo (Minimum Risk, vazio = sem filtro)", value=None, step=1000.0,
                    key="portfolio_shortlist_retorno_minimo",
                )
                risco_maximo_sl = colsl3.number_input(
                    "Risco máximo (Growth, R$ negativo, vazio = sem filtro)", max_value=0.0, value=None,
                    step=500.0, key="portfolio_shortlist_risco_maximo",
                )
                clusters_para_shortlist = st.session_state.get("portfolio_clusters_risco")
                alocacao_atual_sl = {
                    nome: resumo_robos.get(nome, {}).get("n_contratos", 0) for nome in diarios_referencia
                }

                shortlist = shortlist_portfolio(
                    resultados_para_shortlist, diarios_referencia, margens_por_contrato,
                    total_contratos_benchmark=int(total_contratos_benchmark),
                    alocacao_atual=alocacao_atual_sl, clusters=clusters_para_shortlist,
                    retorno_minimo=retorno_minimo_sl, risco_maximo=risco_maximo_sl,
                    percentil_cauda=percentil_cauda, fracao_reserva_operacional=fracao_reserva_operacional_pct / 100,
                    increment=increment, usar_janela_comum=usar_janela_comum,
                )

                rotulos_perfis = {
                    "carteira_atual": "Carteira atual",
                    "minimum_risk": "Minimum Risk",
                    "balanced": "Balanced",
                    "growth": "Growth",
                    "handcrafted_risk": "Handcrafted Risk",
                    "contratos_iguais": "Contratos iguais",
                    "risco_inverso": "Risco inverso",
                }
                linhas_shortlist = []
                for chave, rotulo in rotulos_perfis.items():
                    r = shortlist.get(chave)
                    if r is None:
                        continue
                    linhas_shortlist.append({
                        "Perfil": rotulo,
                        **{f"Contratos {nome}": v for nome, v in r["alocacao"].items()},
                        "Lucro": fmt(r["lucro_total"], moeda=True),
                        "MDD": fmt(r["mdd"], moeda=True),
                        "RLT": fmt(r["rlt_acumulado"], 4),
                    })
                st.table(pd.DataFrame(linhas_shortlist).set_index("Perfil"))
                st.caption(
                    "Handcrafted Risk só aparece se o expander \"Correlação entre robôs\" já "
                    "detectou clusters acima."
                )

        with st.expander("Robustez (Monte Carlo) do portfólio"):
            st.caption(
                "Reamostragem sincronizada pela data (tarefas e épicos.pdf tarefa 8.1: \"todos "
                "os robôs permanecem sincronizados\") -- cada bloco sorteado usa as MESMAS datas "
                "para todos os robôs, preservando a correlação real entre eles, em vez de "
                "reamostrar cada um independentemente. Nenhuma fórmula nova -- mesma máquina do "
                "modo Robô único (tradefolio.monte_carlo), só alimentada com o portfólio inteiro. "
                "Cenários de deterioração não incluídos aqui (precisariam de colunas por robô sem "
                "significado agregado coerente, ver docstring de tradefolio.portfolio.robustez_portfolio)."
            )
            resumo_robustez_pf = robustez_portfolio(
                largo, tamanho_bloco=tamanho_bloco_pf, n_trajetorias=int(n_trajetorias_pf),
                horizonte=int(horizonte_pf), seed=int(seed_pf) if seed_pf is not None else None,
                incluir_dias_sem_operacao=incluir_sem_operacao_pf,
                minimum_margin=sum(minimum_margins.values()), limiar=limiar_agregado_ativo,
            )
            st.caption(
                f"{resumo_robustez_pf['n_trajetorias']} trajetórias × {resumo_robustez_pf['horizonte']} "
                f"pregões, bloco={resumo_robustez_pf['tamanho_bloco']}, seed={resumo_robustez_pf['seed']} "
                "(reuse essa seed para reproduzir exatamente este resultado)."
            )

            colmc1, colmc2, colmc3, colmc4, colmc5 = st.columns(5)
            colmc1.metric("Lucro P5", fmt(resumo_robustez_pf["lucro_p5"], moeda=True))
            colmc2.metric("Lucro P25", fmt(resumo_robustez_pf["lucro_p25"], moeda=True))
            colmc3.metric("Lucro P50 (mediano)", fmt(resumo_robustez_pf["lucro_p50"], moeda=True))
            colmc4.metric("Lucro P75", fmt(resumo_robustez_pf["lucro_p75"], moeda=True))
            colmc5.metric("Lucro P95", fmt(resumo_robustez_pf["lucro_p95"], moeda=True))

            colmd1, colmd2, colmd3, colmd4 = st.columns(4)
            colmd1.metric("MDD P50", fmt(resumo_robustez_pf["mdd_p50"], moeda=True))
            colmd2.metric("MDD P90", fmt(resumo_robustez_pf["mdd_p90"], moeda=True))
            colmd3.metric("MDD P95", fmt(resumo_robustez_pf["mdd_p95"], moeda=True))
            colmd4.metric("MDD P99", fmt(resumo_robustez_pf["mdd_p99"], moeda=True))

            colp1, colp2, colp3 = st.columns(3)
            colp1.metric("Probabilidade de prejuízo", fmt(resumo_robustez_pf["probabilidade_prejuizo"] * 100) + "%")
            colp2.metric("Probabilidade de tocar a margem", fmt(resumo_robustez_pf["probabilidade_toca_margem"] * 100) + "%")
            colp3.metric("Prob. terminar abaixo do limiar", fmt(resumo_robustez_pf["probabilidade_termina_abaixo_do_limiar"] * 100) + "%")
    else:
        st.info(
            "Informe a margem mínima de cada robô na barra lateral para calcular o limiar agregado, "
            "o benefício da diversificação, a contribuição marginal de cada robô, rodar a otimização "
            "e a robustez (Monte Carlo) do portfólio."
        )

    st.caption(
        "Fora de escopo nesta versão do modo Portfólio: VLT agregado (precisa de uma política de "
        "vapo escolhida para o portfólio), janela de filtro, cenários de deterioração agregados, "
        "otimização de portfólio considerando VLT/pior cenário deteriorado. Ver TASKS.md (Épico 10) "
        "para o que cada um exigiria."
    )


st.set_page_config(page_title="Lâmina ao vivo", layout="wide")
st.title("Lâmina ao vivo")

modo = st.sidebar.radio(
    "Modo", ["Robô único", "Portfólio"], key="modo_app",
    help="Portfólio (AGENTS.md épico 10) sincroniza 2+ robôs e mostra métricas agregadas -- "
         "não substitui a análise detalhada de um robô único.",
)
if modo == "Portfólio":
    rodar_modo_portfolio()
    st.stop()

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

chave_arquivo = getattr(arquivo_ordens, "name", str(arquivo_ordens))
eh_resultados_diarios = eh_formato_resultados_diarios(arquivo_ordens)

ordens = None
deteccao_por_ativo = None

if eh_resultados_diarios:
    # Robô sem exportação order-level (ex. TradingX) -- só resultado
    # diário já agregado. contratos_referencia=1 fixo (decisão do
    # usuário, não detectada -- ver tradefolio.daily_results). Página de
    # trade (nunca mostrada em app.py, só em report.py) e comparação
    # entre ativos não se aplicam a este formato (série única, sem
    # detalhe de ordem).
    try:
        resultados_diarios = carregar_resultados_diarios(arquivo_ordens)
    except ValueError as erro:
        st.error(f"CSV de resultados diários inválido: {erro}")
        st.stop()
    contratos_referencia = CONTRATOS_REFERENCIA_RESULTADOS_DIARIOS
else:
    try:
        ordens = carregar_ordens(arquivo_ordens)
    except ValueError as erro:
        st.error(f"CSV inválido: {erro}")
        st.stop()

    try:
        contratos_referencia = detectar_contratos_referencia(ordens)
    except ValueError:
        # Robô multi-ativo com proporção fixa entre pernas (ex. Robô Raiz: 3
        # WIN + 2 WDO por unidade) -- misturar as pernas numa única
        # distribuição não detecta nada. Tenta por perna sobre uma janela
        # recente (a proporção pode ter mudado historicamente e só a atual
        # importa) antes de desistir.
        with st.sidebar:
            st.warning(
                "Não foi possível detectar um único número de contratos sobre "
                "o histórico inteiro -- tentando por ativo sobre uma janela recente."
            )
            dias_recentes_deteccao = st.number_input(
                "Janela para detectar a configuração atual (dias)", min_value=7, max_value=730,
                value=90, step=1, key=f"dias_recentes_deteccao::{chave_arquivo}",
                help="Restringe a detecção da proporção entre ativos (ex. 3 WIN + 2 WDO) aos últimos N dias -- a proporção pode ter mudado no passado, e só a atual importa aqui.",
            )
        try:
            contratos_referencia = detectar_contratos_referencia_multi_ativo(
                ordens, dias_recentes=int(dias_recentes_deteccao)
            )
            deteccao_por_ativo = contratos_referencia_por_ativo(ordens, dias_recentes=int(dias_recentes_deteccao))
        except ValueError as erro:
            st.error(
                f"Não foi possível determinar a configuração de contratos, nem por ativo "
                f"sobre os últimos {int(dias_recentes_deteccao)} dias: {erro}"
            )
            st.stop()

with st.sidebar:
    st.header("Filtros")
    janela = st.selectbox(
        "Janela", JANELAS_DISPONIVEIS, index=len(JANELAS_DISPONIVEIS) - 1, help=AJUDA_JANELA,
    )
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

    reducao_ganhos_pct = aumento_perdas_pct = aumento_custos_pct = 0.0
    slippage_valor = 0.0
    remover_melhores_n = duplicar_piores_n = 0
    if eh_resultados_diarios:
        st.caption(
            "Cenário de deterioração não disponível para este robô -- precisa de custo B3/"
            "contagem de trades por dia, que este formato (resultado diário já agregado, "
            "sem detalhe de ordem) não tem."
        )
    else:
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

if eh_resultados_diarios:
    diario = montar_diario_resultados(resultados_diarios)
else:
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
if deteccao_por_ativo is not None:
    composicao = " + ".join(f"{qtd} {ativo}" for ativo, qtd in sorted(deteccao_por_ativo.items()))
    st.caption(
        f"Robô multi-ativo com proporção fixa entre pernas -- \"1 contrato\" aqui = "
        f"{composicao} (detectado sobre os últimos {int(dias_recentes_deteccao)} dias; "
        f"total {contratos_referencia}). Não dá para simular WIN e WDO independentemente -- "
        f"\"Número de contratos\" escala o pacote inteiro proporcionalmente."
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

if not eh_resultados_diarios and ordens["Ativo"].map(extrair_raiz_ativo).nunique() > 1:
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
