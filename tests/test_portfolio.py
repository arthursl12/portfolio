"""
RED: tradefolio.portfolio ainda não existe (AGENTS.md épico 10).

Maior gap arquitetural do projeto até agora: tudo em tradefolio.* opera
sobre UM `ordens`/`diario` por vez. Este módulo generaliza o padrão já
usado em `daily.pivotar_liquido_por_ativo` (por ativo dentro de um robô)
para "por robô dentro de um portfólio".

Decisões de design tomadas (documentadas, não escondidas -- AGENTS.md §8):
- `sincronizar_portfolio` recebe um dict {nome: diario} já pronto (cada
  `diario` já construído com o `contratos_referencia` certo daquele
  robô, inclusive multi-ativo com proporção fixa) -- não recalcula nada,
  só sincroniza. Um `pd.DataFrame({nome: diario["liquido"] ...})` já faz
  exatamente o alinhamento certo: `pandas` une os índices e preenche com
  NaN onde um robô simplesmente não tem dado -- e não com 0, que já
  significa NO_TRADE dentro do range de vida de um robô. Isso distingue
  "robô não operou" (0, já embutido no diario de cada robô) de "robô
  ainda não existia" (NaN aqui) sem nenhuma lógica nova -- só não
  esconder o NaN com fillna(0).
- `serie_combinada` soma com `skipna=True`: um robô que ainda não existia
  contribui 0 para o total do portfólio naquele dia (não contribui
  NaN para o portfólio inteiro) -- decisão explícita, documentada.
- `multiplicadores` (opcional) escala cada robô ANTES de sincronizar --
  cobre a tarefa 10.2 ("suportar quantidades e multiplicadores") sem
  precisar de uma segunda função.
- `correlacao_portfolio` é só `largo.corr()` -- o pandas já calcula
  correlação par-a-par usando só as datas em que AMBOS os robôs tinham
  dado (pairwise complete observations), o que já é o comportamento
  certo para "não existia ainda" (NaN), sem precisar excluir nada à mão.
- `limiar_agregado_portfolio` reusa `limiar.decompor_limiar` -- MESMA
  função do robô único, só alimentada com a margem SOMADA e o drawdown
  da série COMBINADA. O PDF-fonte avisa explicitamente para NÃO somar os
  limiares individuais -- aqui não se soma nada, decompor_limiar já
  calcula um limiar genuinamente novo a partir dos dados agregados.

Valores conferidos por script (dados_exemplo/orders_resgat.csv +
orders_gridhedge.csv + orders_romanos2.csv, margem R$5.000 cada) antes
deste teste: lucro combinado R$64.320,93, MDD combinado R$-4.452,50,
limiar agregado R$19.500 vs. soma dos limiares individuais R$25.500
(9.500+8.000+8.000) -- um benefício de diversificação real de R$6.000.
"""
import warnings

import pandas as pd
import pytest

from tradefolio.portfolio import (
    beneficio_diversificacao,
    contribuicao_marginal,
    contribuicao_risco_por_robo,
    correlacao_dias_conjuntos,
    correlacao_movel,
    correlacao_perdas,
    correlacao_piores_dias,
    correlacao_portfolio,
    correlacao_volatilidade_alta,
    buscar_combinacoes_portfolio,
    buscar_combinacoes_portfolio_com_filtros,
    clusters_de_risco,
    curva_limiares_mdd,
    fronteira_pareto,
    funil_selecao_portfolio,
    limiar_agregado_portfolio,
    metricas_agregadas,
    otimizar_portfolio,
    restringir_janela_comum,
    robustez_dos_finalistas,
    robustez_portfolio,
    scores_individuais_portfolio,
    selecionar_melhores_combinacoes,
    shortlist_portfolio,
    rlt_e_risco_portfolio,
    serie_combinada,
    sincronizar_operou,
    sincronizar_portfolio,
    vizinhanca_local,
)
from tradefolio.monte_carlo import circular_block_bootstrap, resumo_trajetorias
from tradefolio.report_data import montar_dataframe_diario


def _diarios_reais():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return {
            "resgat": montar_dataframe_diario("dados_exemplo/orders_resgat.csv"),
            "gridhedge": montar_dataframe_diario("dados_exemplo/orders_gridhedge.csv"),
            "romanos2": montar_dataframe_diario("dados_exemplo/orders_romanos2.csv"),
        }


def test_sincronizar_portfolio_preenche_nao_existia_com_nan_nao_zero():
    diarios = _diarios_reais()
    largo = sincronizar_portfolio(diarios)

    assert set(largo.columns) == {"resgat", "gridhedge", "romanos2"}
    # resgat comeca em 2024-03-13, os outros dois so em 2025-06 -- data
    # bem antes disso so tem resgat, os outros devem ser NaN (nao 0).
    linha = largo.loc["2024-06-03"]
    assert linha["resgat"] == pytest.approx(-385.0)
    assert pd.isna(linha["gridhedge"])
    assert pd.isna(linha["romanos2"])


def test_sincronizar_portfolio_aplica_multiplicadores():
    diarios = _diarios_reais()
    largo = sincronizar_portfolio(diarios, multiplicadores={"resgat": 2.0})
    linha = largo.loc["2024-06-03"]
    assert linha["resgat"] == pytest.approx(-385.0 * 2.0)


def test_serie_combinada_soma_com_skipna():
    diarios = _diarios_reais()
    largo = sincronizar_portfolio(diarios)
    combinada = serie_combinada(largo)

    soma_individual = sum(d["liquido"].sum() for d in diarios.values())
    assert combinada.sum() == pytest.approx(soma_individual)
    assert combinada.sum() == pytest.approx(64320.93, abs=1e-2)
    # antes de gridhedge/romanos2 existirem, a combinada = só resgat
    assert combinada.loc["2024-06-03"] == pytest.approx(-385.0)


# --- Janela comum (pedido de acompanhamento do usuário: métricas de
# portfólio devem, por padrão, considerar só o período em que TODOS os
# robôs já existiam -- não a união inteira, que mistura anos de resgat
# sozinho com o período em que os 3 já coexistiam) -----------------------


def test_restringir_janela_comum_corta_para_intersecao_de_existencia():
    diarios = _diarios_reais()
    largo = sincronizar_portfolio(diarios)
    comum = restringir_janela_comum(largo)

    assert comum.index.min() == pd.Timestamp("2025-06-11")
    assert comum.index.max() == pd.Timestamp("2026-09-08")
    assert len(comum) == 312
    assert not comum.isna().any().any()


def test_restringir_janela_comum_levanta_erro_se_vazia():
    diarios = _diarios_reais()
    # trunca resgat para terminar em 2024-12-31 -- bem antes de gridhedge
    # começar (2025-06-02) -- não sobra nenhuma data em que ambos existam.
    sem_overlap = diarios["resgat"].loc[:"2024-12-31"]
    largo = sincronizar_portfolio({"resgat": sem_overlap, "gridhedge": diarios["gridhedge"]})
    with pytest.raises(ValueError, match="[Cc]oexist"):
        restringir_janela_comum(largo)


def test_metricas_agregadas_real():
    diarios = _diarios_reais()
    largo = sincronizar_portfolio(diarios)
    resumo = metricas_agregadas(largo)

    assert resumo["lucro_total"] == pytest.approx(64320.93, abs=1e-2)
    assert resumo["mdd"] == pytest.approx(-4452.50, abs=1e-2)
    assert resumo["es_95"] == pytest.approx(-976.9075, abs=1e-2)


def test_correlacao_portfolio_pairwise():
    diarios = _diarios_reais()
    largo = sincronizar_portfolio(diarios)
    corr = correlacao_portfolio(largo)

    assert corr.loc["resgat", "resgat"] == pytest.approx(1.0)
    assert corr.loc["resgat", "gridhedge"] == pytest.approx(0.056122, abs=1e-5)
    assert corr.loc["gridhedge", "romanos2"] == pytest.approx(-0.018995, abs=1e-5)


def test_limiar_agregado_portfolio_menor_que_soma_dos_individuais():
    diarios = _diarios_reais()
    largo = sincronizar_portfolio(diarios)
    margens = {"resgat": 5000.0, "gridhedge": 5000.0, "romanos2": 5000.0}

    agregado = limiar_agregado_portfolio(
        largo, minimum_margins=margens, percentil_cauda=95,
        fracao_reserva_operacional=0.10, increment=500,
    )
    assert agregado["minimum_margin"] == pytest.approx(15000.0)
    assert agregado["limiar_recomendado"] == pytest.approx(19500.0)


def test_beneficio_diversificacao():
    resultado = beneficio_diversificacao(
        soma_limiares_individuais=25500.0, limiar_agregado=19500.0,
    )
    assert resultado["beneficio_rs"] == pytest.approx(6000.0)
    assert resultado["beneficio_pct"] == pytest.approx(6000.0 / 25500.0)


# --- Tarefa 10.4: correlações múltiplas ---------------------------------
#
# lâmina ideal.pdf §13 pede "pelo menos quatro versões" (total, dias
# conjuntos, piores 20%, volatilidade alta); tarefas e épicos.pdf acrescenta
# "correlação de perdas" e "correlação móvel". Decisão de design (não
# escondida): as variantes condicionais (piores dias/perdas/volatilidade
# alta) usam a série COMBINADA do portfólio (serie_combinada) como
# referência para definir "dia ruim"/"volatilidade alta" -- a mesma série
# já usada por metricas_agregadas/limiar_agregado_portfolio em todo o
# módulo, não uma recombinação por par. Valores conferidos por script
# (resgat+gridhedge+romanos2) antes destes testes.


def test_sincronizar_operou_preenche_nao_existia_com_false():
    diarios = _diarios_reais()
    operou = sincronizar_operou(diarios)
    assert set(operou.columns) == {"resgat", "gridhedge", "romanos2"}
    # resgat operou nesse dia; os outros dois ainda nem existiam.
    linha = operou.loc["2024-06-03"]
    assert bool(linha["resgat"]) in (True, False)
    assert pd.isna(linha["gridhedge"])
    assert pd.isna(linha["romanos2"])


def test_correlacao_dias_conjuntos():
    diarios = _diarios_reais()
    largo = sincronizar_portfolio(diarios)
    operou = sincronizar_operou(diarios)
    corr = correlacao_dias_conjuntos(largo, operou)

    assert corr.loc["resgat", "gridhedge"] == pytest.approx(0.068778, abs=1e-5)
    assert corr.loc["resgat", "romanos2"] == pytest.approx(0.101249, abs=1e-5)


def test_correlacao_piores_dias():
    diarios = _diarios_reais()
    largo = sincronizar_portfolio(diarios)
    corr = correlacao_piores_dias(largo, fracao=0.20)

    assert corr.loc["resgat", "gridhedge"] == pytest.approx(-0.410263, abs=1e-5)
    assert corr.loc["resgat", "romanos2"] == pytest.approx(-0.497713, abs=1e-5)


def test_correlacao_perdas():
    diarios = _diarios_reais()
    largo = sincronizar_portfolio(diarios)
    corr = correlacao_perdas(largo)

    assert corr.loc["resgat", "gridhedge"] == pytest.approx(-0.236743, abs=1e-5)
    assert corr.loc["gridhedge", "romanos2"] == pytest.approx(-0.375978, abs=1e-5)


def test_correlacao_volatilidade_alta():
    diarios = _diarios_reais()
    largo = sincronizar_portfolio(diarios)
    corr = correlacao_volatilidade_alta(largo, janela=21, fracao=0.20)

    assert corr.loc["resgat", "gridhedge"] == pytest.approx(0.012334, abs=1e-5)
    assert corr.loc["gridhedge", "romanos2"] == pytest.approx(0.169463, abs=1e-5)


def test_correlacao_movel_primeiros_valores_sao_nan():
    diarios = _diarios_reais()
    largo = sincronizar_portfolio(diarios)
    movel = correlacao_movel(largo, janela_pregoes=63)

    assert "resgat × gridhedge" in movel.columns
    assert movel["resgat × gridhedge"].iloc[:62].isna().all()
    assert movel["resgat × gridhedge"].iloc[-1] == pytest.approx(0.123492, abs=1e-5)


# --- Clusters de risco (backlog de prompts/otimizacao.pdf §4, fora dos
# épicos do PDF-fonte) -----------------------------------------------------
#
# "Agrupe EAs que representam o mesmo risco" -- o documento não
# prescreve um algoritmo. Decisão CONFIRMADA com o usuário (AGENTS.md
# §24, para não inventar um método de clustering como se fosse convenção
# do domínio): grafo de limiar + componentes conexos (dois robôs
# compartilham cluster sse a correlação entre eles >= `limiar_correlacao`;
# clusters = componentes conexos do grafo), sobre `correlacao_portfolio`
# (variante "todos os dias", a mesma já usada como padrão no resto do
# módulo) -- sem depender de scipy/sklearn (AGENTS.md §18, sem
# dependência nova sem justificativa; o número típico de robôs num
# portfólio aqui, 2-10, não pede nada mais sofisticado). Correlação
# NEGATIVA nunca agrupa (mesmo forte) -- correlação negativa é
# diversificação, o oposto do que "mesmo risco" significa aqui; só
# correlação POSITIVA acima do limiar indica redundância.
#
# Dados sintéticos (não os robôs reais -- a correlação entre
# resgat/gridhedge/romanos2 é baixa demais, ~0,06/0,06/-0,02, para
# exercitar o agrupamento de verdade): a/b perfeitamente correlacionados
# (corr=1.0), c/d perfeitamente correlacionados (corr=1.0), e
# independente; a/c são NEGATIVAMENTE correlacionados (-0.68) -- não
# devem agrupar mesmo sendo "fortes" em magnitude.

_LARGO_CLUSTERS_SINTETICO = pd.DataFrame({
    "a": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    "b": [2, 4, 6, 8, 10, 12, 14, 16, 18, 20],
    "c": [10, 8, 6, 9, 7, 5, 11, 4, 3, 2],
    "d": [20, 16, 12, 18, 14, 10, 22, 8, 6, 4],
    "e": [3, 7, 1, 9, 2, 8, 4, 6, 5, 0],
})


def test_clusters_de_risco_agrupa_por_correlacao_positiva():
    clusters = clusters_de_risco(_LARGO_CLUSTERS_SINTETICO, limiar_correlacao=0.5)
    assert sorted(sorted(c) for c in clusters) == [["a", "b"], ["c", "d"], ["e"]]


def test_clusters_de_risco_correlacao_negativa_nunca_agrupa():
    # a e c têm |corr| = 0.68 (mais forte em magnitude que muitos pares
    # positivos), mas são NEGATIVAMENTE correlacionados -- mesmo com um
    # limiar baixo o suficiente para incluir 0.68 em magnitude, a e c não
    # devem cair no mesmo cluster.
    clusters = clusters_de_risco(_LARGO_CLUSTERS_SINTETICO, limiar_correlacao=0.6)
    grupos = {frozenset(c) for c in clusters}
    assert frozenset({"a", "c"}) not in grupos
    assert frozenset({"a", "b"}) in grupos
    assert frozenset({"c", "d"}) in grupos


def test_clusters_de_risco_limiar_alto_todos_independentes():
    clusters = clusters_de_risco(_LARGO_CLUSTERS_SINTETICO, limiar_correlacao=1.01)
    assert sorted(sorted(c) for c in clusters) == [["a"], ["b"], ["c"], ["d"], ["e"]]


def test_clusters_de_risco_robos_reais_baixa_correlacao_ficam_independentes():
    diarios = _diarios_reais()
    largo = restringir_janela_comum(sincronizar_portfolio(diarios))
    clusters = clusters_de_risco(largo, limiar_correlacao=0.5)
    assert sorted(sorted(c) for c in clusters) == [["gridhedge"], ["resgat"], ["romanos2"]]


# --- Tarefa 10.3 (extensão): RLT e risco normalizado do portfólio -------


def test_metricas_agregadas_traz_tuw_pior_dia_pior_mes_e_lucro_mensal():
    diarios = _diarios_reais()
    largo = sincronizar_portfolio(diarios)
    resumo = metricas_agregadas(largo)

    assert resumo["tuw_max"] == 79
    assert resumo["pior_dia_total"] == pytest.approx(-1501.5)
    assert resumo["pior_mes_total"] == pytest.approx(-1425.0)
    assert resumo["lucro_mensal"].loc["2024-04-30"] == pytest.approx(10311.0)


def test_rlt_e_risco_portfolio():
    diarios = _diarios_reais()
    largo = sincronizar_portfolio(diarios)

    rlt = rlt_e_risco_portfolio(largo, limiar=19500.0)

    assert rlt["rlt_acumulado"] == pytest.approx(3.2985092307692305, abs=1e-6)
    assert rlt["rlt_anualizado"] == pytest.approx(1.3253910853008377, abs=1e-6)
    assert rlt["rlt_mensal_medio"] == pytest.approx(0.10640352357320101, abs=1e-6)
    assert rlt["rlt_mensal_mediano"] == pytest.approx(0.10923076923076923, abs=1e-6)
    assert rlt["rlt_movel_3"] == pytest.approx(0.3112820512820513, abs=1e-6)
    assert rlt["mdd_sobre_limiar"] == pytest.approx(-0.22833333333333333, abs=1e-6)
    assert rlt["pior_mes_sobre_limiar"] == pytest.approx(-0.07307692307692308, abs=1e-6)


# --- Tarefa 10.5: contribuição marginal por robô ------------------------
#
# lâmina ideal.pdf §13 ("Valor marginal do robô") e tarefas e épicos.pdf
# (tarefa 10.5): para cada robô, recomputar o portfólio COM e SEM ele e
# diferenciar lucro/MDD/ES/limiar. VLT deliberadamente fora (mesma lacuna
# documentada em rlt_e_risco_portfolio/TASKS.md -- precisa de uma
# política de vapo escolhida para o portfólio). Valores conferidos por
# script antes deste teste.

_MARGENS_10_5 = {"resgat": 5000.0, "gridhedge": 5000.0, "romanos2": 5000.0}
_PARAMS_10_5 = dict(percentil_cauda=95, fracao_reserva_operacional=0.10, increment=500)


def test_contribuicao_marginal_resgat():
    # Default agora restringe cada comparação (com/sem robô) à sua PRÓPRIA
    # janela comum (usar_janela_comum=True) -- pedido de acompanhamento do
    # usuário: métricas de portfólio devem usar só o período em que todos
    # os robôs envolvidos coexistiam, não a união. "sem resgat" usa a
    # janela comum de {gridhedge, romanos2} (maior que a janela comum dos
    # 3), não a janela comum original com resgat removido depois.
    diarios = _diarios_reais()
    contribuicoes = contribuicao_marginal(diarios, _MARGENS_10_5, **_PARAMS_10_5)

    resgat = contribuicoes["resgat"]
    assert resgat["lucro_com"] == pytest.approx(41619.93, abs=1e-2)
    assert resgat["lucro_sem"] == pytest.approx(28657.93, abs=1e-2)
    assert resgat["diferenca_lucro"] == pytest.approx(12962.0, abs=1e-2)
    assert resgat["diferenca_mdd"] == pytest.approx(-689.44, abs=1e-2)
    assert resgat["diferenca_es95"] == pytest.approx(-159.18437500000005, abs=1e-2)
    assert resgat["diferenca_limiar"] == pytest.approx(5500.0, abs=1e-6)


def test_contribuicao_marginal_gridhedge_e_romanos2():
    diarios = _diarios_reais()
    contribuicoes = contribuicao_marginal(diarios, _MARGENS_10_5, **_PARAMS_10_5)

    gridhedge = contribuicoes["gridhedge"]
    assert gridhedge["diferenca_lucro"] == pytest.approx(6870.43, abs=1e-2)
    assert gridhedge["diferenca_mdd"] == pytest.approx(-288.5, abs=1e-2)
    assert gridhedge["diferenca_es95"] == pytest.approx(-198.96937500000013, abs=1e-2)
    assert gridhedge["diferenca_limiar"] == pytest.approx(6000.0, abs=1e-6)

    romanos2 = contribuicoes["romanos2"]
    assert romanos2["diferenca_lucro"] == pytest.approx(21825.5, abs=1e-2)
    assert romanos2["diferenca_mdd"] == pytest.approx(-778.0, abs=1e-2)
    assert romanos2["diferenca_es95"] == pytest.approx(-171.2525, abs=1e-2)
    assert romanos2["diferenca_limiar"] == pytest.approx(6000.0, abs=1e-6)


def test_contribuicao_marginal_uniao_explicita_preserva_comportamento_antigo():
    # usar_janela_comum=False -- opt-out explícito, mesmo comportamento
    # (união com skipna) e mesmos valores já verificados antes desta
    # mudança de default.
    diarios = _diarios_reais()
    contribuicoes = contribuicao_marginal(
        diarios, _MARGENS_10_5, usar_janela_comum=False, **_PARAMS_10_5,
    )

    resgat = contribuicoes["resgat"]
    assert resgat["lucro_com"] == pytest.approx(64320.93, abs=1e-2)
    assert resgat["lucro_sem"] == pytest.approx(29346.93, abs=1e-2)
    assert resgat["diferenca_lucro"] == pytest.approx(34974.0, abs=1e-2)
    assert resgat["diferenca_limiar"] == pytest.approx(5000.0, abs=1e-6)


def test_contribuicao_marginal_exige_ao_menos_2_robos():
    diarios = {"resgat": _diarios_reais()["resgat"]}
    with pytest.raises(ValueError, match="2"):
        contribuicao_marginal(diarios, {"resgat": 5000.0})


# --- Contribuição de risco por robô (backlog de prompts/otimizacao.pdf,
# fora dos épicos do PDF-fonte) -------------------------------------------
#
# Distinto de contribuicao_marginal (COM vs. SEM o robô): aqui é uma
# decomposição DENTRO da carteira já escolhida -- "quem causou o quê" em
# três lentes mantidas SEPARADAS (o documento é explícito: "não some
# imediatamente os três em uma nota arbitrária"):
#   (1) contribuição à volatilidade via covariância (alocação de Euler:
#       Cov(robô, portfólio)/vol(portfólio) -- soma exatamente à
#       volatilidade total). Decisão confirmada com o usuário: reabre a
#       convenção de variância/covariância que a docstring de
#       fronteira_pareto rejeitou para ESCOLHER contratos discretos
#       (Markowitz não serve para a busca em si) -- aqui é só uma
#       decomposição analítica de uma carteira já fixada, não influencia
#       nenhuma busca nem reintroduz variância como critério de
#       otimização.
#   (2) contribuição ao Expected Shortfall -- média do resultado de cada
#       robô nos MESMOS dias que definem o ES95/ES99 do portfólio
#       (mesmo corte de `metrics.var_historico` usado por
#       `metrics.expected_shortfall`).
#   (3) contribuição ao drawdown -- decisão confirmada com o usuário: usa
#       APENAS o pior episódio histórico (o mesmo que já define o MDD em
#       `metricas_agregadas`), não uma média entre todos os episódios --
#       garante que as participações somem exatamente ao MDD já mostrado
#       em outros lugares, e evita inventar um esquema de ponderação
#       entre episódios de profundidade diferente. Inclui também
#       "frequência de liderar a perda": em quantos dias daquele episódio
#       (pico->fundo) aquele robô teve o pior resultado do dia entre os
#       robôs do portfólio.
# As três lentes somam exatamente 100% cada (e as frequências somam 1.0)
# -- confirma que nenhuma decomposição está vazando nem contando duas
# vezes. Valores conferidos por script antes destes testes.

_PARAMS_RISCO = dict(percentil_cauda=95)


def test_contribuicao_risco_por_robo_volatilidade():
    diarios = _diarios_reais()
    resultado = contribuicao_risco_por_robo(diarios, **_PARAMS_RISCO)

    assert resultado["volatilidade_portfolio"] == pytest.approx(682.2704779220393, abs=1e-6)
    por_robo = resultado["por_robo"]
    assert por_robo["resgat"]["contribuicao_volatilidade"] == pytest.approx(197.82151492430916, abs=1e-4)
    assert por_robo["resgat"]["participacao_volatilidade_pct"] == pytest.approx(28.99458811801521, abs=1e-4)
    assert por_robo["gridhedge"]["participacao_volatilidade_pct"] == pytest.approx(17.496510660392612, abs=1e-4)
    assert por_robo["romanos2"]["participacao_volatilidade_pct"] == pytest.approx(53.5089012215922, abs=1e-4)
    soma = sum(v["participacao_volatilidade_pct"] for v in por_robo.values())
    assert soma == pytest.approx(100.0, abs=1e-6)


def test_contribuicao_risco_por_robo_expected_shortfall():
    diarios = _diarios_reais()
    resultado = contribuicao_risco_por_robo(diarios, **_PARAMS_RISCO)

    assert resultado["es_referencia"] == pytest.approx(-1136.5943750000001, abs=1e-2)
    assert resultado["n_dias_cauda_es"] == 16
    por_robo = resultado["por_robo"]
    assert por_robo["resgat"]["contribuicao_es"] == pytest.approx(-427.125, abs=1e-2)
    assert por_robo["resgat"]["participacao_es_pct"] == pytest.approx(37.57936950902119, abs=1e-4)
    assert por_robo["gridhedge"]["participacao_es_pct"] == pytest.approx(35.33862949128179, abs=1e-4)
    assert por_robo["romanos2"]["participacao_es_pct"] == pytest.approx(27.08200099969701, abs=1e-4)
    soma = sum(v["participacao_es_pct"] for v in por_robo.values())
    assert soma == pytest.approx(100.0, abs=1e-6)


def test_contribuicao_risco_por_robo_drawdown():
    diarios = _diarios_reais()
    resultado = contribuicao_risco_por_robo(diarios, **_PARAMS_RISCO)

    episodio = resultado["episodio_drawdown_referencia"]
    assert episodio["inicio_pico"] == pd.Timestamp("2025-07-09")
    assert episodio["data_fundo"] == pd.Timestamp("2025-07-24")
    assert episodio["profundidade_rs"] == pytest.approx(-4452.5, abs=1e-2)
    # mesmo episódio que já define o MDD agregado (decisão confirmada com
    # o usuário -- ver comentário acima deste bloco de testes).
    largo = restringir_janela_comum(sincronizar_portfolio(diarios))
    assert episodio["profundidade_rs"] == pytest.approx(metricas_agregadas(largo)["mdd"], abs=1e-6)

    por_robo = resultado["por_robo"]
    assert por_robo["resgat"]["contribuicao_drawdown"] == pytest.approx(-3386.0, abs=1e-2)
    assert por_robo["resgat"]["participacao_drawdown_pct"] == pytest.approx(76.0471645143178, abs=1e-4)
    assert por_robo["resgat"]["frequencia_lidera_perda_drawdown"] == pytest.approx(0.45454545454545453, abs=1e-6)
    assert por_robo["gridhedge"]["participacao_drawdown_pct"] == pytest.approx(6.47950589556429, abs=1e-4)
    assert por_robo["romanos2"]["participacao_drawdown_pct"] == pytest.approx(17.47332959011791, abs=1e-4)
    soma_pct = sum(v["participacao_drawdown_pct"] for v in por_robo.values())
    assert soma_pct == pytest.approx(100.0, abs=1e-6)
    soma_freq = sum(v["frequencia_lidera_perda_drawdown"] for v in por_robo.values())
    assert soma_freq == pytest.approx(1.0, abs=1e-6)


def test_contribuicao_risco_por_robo_exige_ao_menos_2_robos():
    diarios = {"resgat": _diarios_reais()["resgat"]}
    with pytest.raises(ValueError, match="2"):
        contribuicao_risco_por_robo(diarios)


def test_contribuicao_risco_por_robo_uniao_explicita_nao_deixa_nan_vazar():
    # usar_janela_comum=False -- mesma convenção de robustez_portfolio:
    # NaN (robô ainda não existia) vira 0 antes de covariância/ES/
    # drawdown, não silenciosamente propaga NaN pro resultado.
    diarios = _diarios_reais()
    largo_uniao = sincronizar_portfolio(diarios)
    assert largo_uniao.isna().any().any()  # confirma que há NaN de fato

    resultado = contribuicao_risco_por_robo(diarios, usar_janela_comum=False, **_PARAMS_RISCO)
    for v in resultado["por_robo"].values():
        assert all(x == x for x in v.values())  # nenhum NaN (x != x só é True para NaN)


# --- Scores individuais separados (backlog de prompts/otimizacao.pdf §3,
# fora dos épicos do PDF-fonte) --------------------------------------------
#
# "Não some imediatamente os três [scores] em uma nota arbitrária" --
# decisão CONFIRMADA com o usuário (AGENTS.md §24): em vez de reduzir
# cada eixo (retorno/risco/diversificação) a UM número (o que exigiria
# inventar uma fórmula de normalização/peso não pedida por ninguém),
# `scores_individuais_portfolio` devolve as métricas BRUTAS de cada eixo,
# agrupadas em 3 seções por robô -- nenhuma agregação nova, só reuso do
# que já existe (`metrics`/`drawdowns`/`correlacao_*`/
# `contribuicao_risco_por_robo`) organizado pelo eixo que o documento
# atribui a cada métrica (§3):
# - retorno: lucro líquido, expectativa diária, desvio padrão diário
#   ("estabilidade"), resultado excluindo os `fracao_melhores_dias`
#   melhores dias (mesmo mecanismo de corte por quantil de
#   `metrics.var_historico`, só no lado superior da série).
# - risco: MDD, ES, pior dia, duração máxima de drawdown, maior
#   sequência de perdas.
# - diversificação: correlação média, correlação nos dias negativos
#   (`correlacao_perdas`), coincidência nos piores dias
#   (`correlacao_piores_dias`), contribuição ao drawdown do portfólio
#   (reusa `contribuicao_risco_por_robo`, não recalcula), retorno médio
#   quando os OUTROS robôs (combinados) perderam.
# Valores conferidos por script antes destes testes.

_PARAMS_SCORES = dict(percentil_cauda=95)


def test_scores_individuais_portfolio_retorno():
    diarios = _diarios_reais()
    scores = scores_individuais_portfolio(diarios, **_PARAMS_SCORES)

    resgat = scores["resgat"]["retorno"]
    assert resgat["lucro_liquido"] == pytest.approx(12962.0, abs=1e-2)
    assert resgat["expectativa_diaria"] == pytest.approx(41.544871794871796, abs=1e-6)
    assert resgat["desvio_padrao_diario"] == pytest.approx(345.3259859397448, abs=1e-4)
    assert resgat["resultado_sem_melhores_dias"] == pytest.approx(-1638.0, abs=1e-2)


def test_scores_individuais_portfolio_risco():
    diarios = _diarios_reais()
    scores = scores_individuais_portfolio(diarios, **_PARAMS_SCORES)

    gridhedge = scores["gridhedge"]["risco"]
    assert gridhedge["mdd"] == pytest.approx(-3141.0600000000013, abs=1e-2)
    assert gridhedge["es"] == pytest.approx(-751.565625, abs=1e-2)
    assert gridhedge["pior_dia"] == pytest.approx(-783.49, abs=1e-2)
    assert gridhedge["duracao_drawdown_max"] == 39
    assert gridhedge["maior_sequencia_perdas"] == 4


def test_scores_individuais_portfolio_diversificacao():
    diarios = _diarios_reais()
    scores = scores_individuais_portfolio(diarios, **_PARAMS_SCORES)

    romanos2 = scores["romanos2"]["diversificacao"]
    assert romanos2["correlacao_media"] == pytest.approx(0.018617651691687505, abs=1e-5)
    assert romanos2["correlacao_dias_negativos"] == pytest.approx(-0.2987707592823811, abs=1e-5)
    assert romanos2["coincidencia_piores_dias"] == pytest.approx(-0.3095429267867986, abs=1e-5)
    assert romanos2["contribuicao_drawdown_portfolio_pct"] == pytest.approx(17.47332959011791, abs=1e-4)
    assert romanos2["retorno_quando_outros_perdem"] == pytest.approx(18.641666666666666, abs=1e-6)


def test_scores_individuais_portfolio_nao_combina_em_nota_unica():
    # Garantia estrutural do pedido do usuário: nenhuma chave de nível
    # "robô" além das 3 seções nomeadas -- em particular, nenhum "score"
    # ou "nota" combinada.
    diarios = _diarios_reais()
    scores = scores_individuais_portfolio(diarios, **_PARAMS_SCORES)
    for por_robo in scores.values():
        assert set(por_robo.keys()) == {"retorno", "risco", "diversificacao"}


def test_scores_individuais_portfolio_exige_ao_menos_2_robos():
    diarios = {"resgat": _diarios_reais()["resgat"]}
    with pytest.raises(ValueError, match="2"):
        scores_individuais_portfolio(diarios)


# --- Tarefa 10.8: otimização de portfólio (busca discreta) --------------
#
# lâmina ideal.pdf §13/tarefas e épicos.pdf tarefa 10.8: busca discreta
# (não otimização contínua, pedido explícito do PDF-fonte) sobre
# combinações de número de contratos por robô -- 0 é um candidato válido
# (excluir o robô inteiramente do portfólio, pedido explícito do
# usuário: "tirar um robô também é uma possibilidade"). Só os objetivos
# que NÃO precisam de uma política de vapo para o portfólio (decisão
# ainda não tomada) são implementados: maximizar RLT, minimizar |MDD/L|,
# maximizar lucro com limite de MDD. Valores conferidos por script antes
# destes testes (candidatos pequenos para o script ser verificável à
# mão: resgat 0/3/6, gridhedge 0/1, romanos2 0/2 -- 12 combinações).

_MARGENS_POR_CONTRATO_10_8 = {"resgat": 1000.0, "gridhedge": 5000.0, "romanos2": 2500.0}
_CANDIDATOS_10_8 = {"resgat": [0, 3, 6], "gridhedge": [0, 1], "romanos2": [0, 2]}
_PARAMS_10_8 = dict(percentil_cauda=95, fracao_reserva_operacional=0.10, increment=500)


def test_otimizar_portfolio_maximizar_rlt_pode_excluir_robo():
    # Default agora restringe CADA candidato à sua própria janela comum
    # (usar_janela_comum=True) -- ver docstring de restringir_janela_comum.
    diarios = _diarios_reais()
    resultado = otimizar_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        objetivo="maximizar_rlt", **_PARAMS_10_8,
    )
    assert resultado["n_combinacoes_testadas"] == 11
    melhor = resultado["melhores"][0]
    # o melhor RLT agora exclui DOIS dos três robôs (só resgat) --
    # demonstração ainda mais direta de que excluir robôs pode vencer.
    assert melhor["alocacao"] == {"resgat": 6, "gridhedge": 0, "romanos2": 0}
    assert melhor["score"] == pytest.approx(3.330857142857143, abs=1e-6)
    assert melhor["lucro_total"] == pytest.approx(34974.0, abs=1e-2)


def test_otimizar_portfolio_minimizar_mdd_sobre_limiar():
    diarios = _diarios_reais()
    resultado = otimizar_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        objetivo="minimizar_mdd_sobre_limiar", **_PARAMS_10_8,
    )
    melhor = resultado["melhores"][0]
    assert melhor["alocacao"] == {"resgat": 3, "gridhedge": 1, "romanos2": 2}
    assert melhor["score"] == pytest.approx(-0.193, abs=1e-6)


def test_otimizar_portfolio_maximizar_lucro_com_limite_mdd():
    diarios = _diarios_reais()
    resultado = otimizar_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        objetivo="maximizar_lucro_com_limite_mdd", limite_mdd=-3000.0, **_PARAMS_10_8,
    )
    melhor = resultado["melhores"][0]
    assert melhor["alocacao"] == {"resgat": 3, "gridhedge": 0, "romanos2": 2}
    assert melhor["lucro_total"] == pytest.approx(28268.5, abs=1e-2)
    assert melhor["mdd"] >= -3000.0


def test_otimizar_portfolio_uniao_explicita_preserva_comportamento_antigo():
    # usar_janela_comum=False -- opt-out explícito, mesmos valores já
    # verificados antes desta mudança de default.
    diarios = _diarios_reais()
    resultado = otimizar_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        objetivo="maximizar_rlt", usar_janela_comum=False, **_PARAMS_10_8,
    )
    melhor = resultado["melhores"][0]
    assert melhor["alocacao"] == {"resgat": 6, "gridhedge": 0, "romanos2": 2}
    assert melhor["score"] == pytest.approx(3.7841, abs=1e-3)
    assert melhor["lucro_total"] == pytest.approx(56761.5, abs=1e-2)


def test_otimizar_portfolio_maximizar_lucro_exige_limite_mdd():
    diarios = _diarios_reais()
    with pytest.raises(ValueError, match="limite_mdd"):
        otimizar_portfolio(
            diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
            objetivo="maximizar_lucro_com_limite_mdd",
        )


def test_otimizar_portfolio_sem_combinacao_valida_levanta_erro():
    diarios = _diarios_reais()
    with pytest.raises(ValueError, match="[Nn]enhuma"):
        otimizar_portfolio(
            diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
            objetivo="maximizar_lucro_com_limite_mdd", limite_mdd=-1000.0, **_PARAMS_10_8,
        )


# --- Separação busca/seleção (pedido de acompanhamento do usuário): a
# busca (cara, uma varredura completa) e a seleção por objetivo (barata,
# só ordena/filtra o que já foi calculado) são funções diferentes -- assim
# trocar de objetivo na UI não recalcula a busca inteira, só reordena a
# tabela já pronta. `otimizar_portfolio` continua existindo como atalho
# que faz as duas coisas numa chamada só (mesmo comportamento de antes).


def test_buscar_combinacoes_portfolio_traz_todas_as_metricas_sem_objetivo():
    diarios = _diarios_reais()
    resultados = buscar_combinacoes_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8, **_PARAMS_10_8,
    )
    assert len(resultados) == 11
    for r in resultados:
        assert set(r) >= {
            "alocacao", "lucro_total", "mdd", "es_95",
            "limiar_ativo", "rlt_acumulado", "mdd_sobre_limiar",
        }
        assert "score" not in r  # score é conceito de seleção, não de busca


def test_selecionar_melhores_combinacoes_reordena_sem_recalcular():
    diarios = _diarios_reais()
    resultados = buscar_combinacoes_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8, **_PARAMS_10_8,
    )

    por_rlt = selecionar_melhores_combinacoes(resultados, objetivo="maximizar_rlt")
    assert por_rlt["melhores"][0]["alocacao"] == {"resgat": 6, "gridhedge": 0, "romanos2": 0}
    assert por_rlt["melhores"][0]["score"] == pytest.approx(3.330857142857143, abs=1e-6)

    por_risco = selecionar_melhores_combinacoes(resultados, objetivo="minimizar_mdd_sobre_limiar")
    assert por_risco["melhores"][0]["alocacao"] == {"resgat": 3, "gridhedge": 1, "romanos2": 2}
    assert por_risco["melhores"][0]["score"] == pytest.approx(-0.193, abs=1e-6)

    por_lucro = selecionar_melhores_combinacoes(
        resultados, objetivo="maximizar_lucro_com_limite_mdd", limite_mdd=-3000.0,
    )
    assert por_lucro["melhores"][0]["alocacao"] == {"resgat": 3, "gridhedge": 0, "romanos2": 2}
    assert por_lucro["melhores"][0]["lucro_total"] == pytest.approx(28268.5, abs=1e-2)


def test_selecionar_melhores_combinacoes_exige_limite_mdd():
    with pytest.raises(ValueError, match="limite_mdd"):
        selecionar_melhores_combinacoes([{}], objetivo="maximizar_lucro_com_limite_mdd")


def test_selecionar_melhores_combinacoes_objetivo_invalido():
    with pytest.raises(ValueError, match="objetivo"):
        selecionar_melhores_combinacoes([{}], objetivo="maximizar_foo")


def test_otimizar_portfolio_equivale_a_busca_mais_selecao():
    diarios = _diarios_reais()
    direto = otimizar_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        objetivo="maximizar_rlt", **_PARAMS_10_8,
    )
    resultados = buscar_combinacoes_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8, **_PARAMS_10_8,
    )
    composto = selecionar_melhores_combinacoes(resultados, objetivo="maximizar_rlt")
    assert direto["melhores"][0]["alocacao"] == composto["melhores"][0]["alocacao"]
    assert direto["n_combinacoes_testadas"] == composto["n_combinacoes_testadas"]


# --- Busca com filtros de sobrevivência + dedupe de composição/escala
# (backlog de prompts/otimizacao.pdf, fora dos épicos do PDF-fonte) ------
#
# Pedido explícito do usuário: NÃO sobrescrever buscar_combinacoes_portfolio
# (compatibilidade e os testes acima continuam intactos) -- esta é uma
# função NOVA e paralela, pensada para comparação lado a lado na UI.
# Reusa o MESMO pipeline por combinação (sincronizar_portfolio/
# metricas_agregadas/limiar_agregado_portfolio/rlt_e_risco_portfolio) --
# só muda QUANTAS combinações chegam até ele, em três camadas baratas
# aplicadas ANTES do cálculo caro, na ordem que cada uma fica disponível:
#   1. Dedupe de composição/escala: [2,2] é a MESMA composição que [1,1]
#      em outra escala -- mantém só a de menor escala (documento-fonte
#      §13: "escolha a menor escala que represente razoavelmente").
#      Puramente combinatório -- não toca nenhum dado.
#   2. Filtros de sobrevivência baratos: mínimo de robôs ativos, margem
#      máxima agregada -- calculados só a partir da alocação e de
#      `margens_por_contrato`, antes de sincronizar qualquer série.
#   3. `perda_diaria_maxima`: usa o PIOR DIA HISTÓRICO da combinação
#      (`combinada.min()`, já disponível logo após sincronizar) -- NÃO
#      um cenário estressado/Monte Carlo (que ficaria caro por
#      combinação e é o oposto do funil barato que este filtro deveria
#      ser; estresse via Monte Carlo é para finalistas, backlog
#      separado).
# Deliberadamente NÃO incluídos nesta rodada: exposição bruta (nenhuma
# noção de "exposição" existe hoje no código -- inventar uma violaria
# AGENTS.md §8) e contribuição máxima de risco por robô (exigiria rodar
# `contribuicao_risco_por_robo` por combinação, o oposto de um filtro
# barato). Valores conferidos por script antes destes testes.

_CANDIDATOS_DEDUPE = {"resgat": [0, 1, 2, 4], "gridhedge": [0, 1, 2]}
_MARGENS_DEDUPE = {"resgat": 1000.0, "gridhedge": 5000.0}


def test_buscar_combinacoes_portfolio_com_filtros_dedupe_composicao():
    diarios = {k: v for k, v in _diarios_reais().items() if k in ("resgat", "gridhedge")}
    resultado = buscar_combinacoes_portfolio_com_filtros(
        diarios, _MARGENS_DEDUPE, _CANDIDATOS_DEDUPE, deduplicar_composicao=True,
    )
    assert resultado["n_combinacoes_totais"] == 12
    assert resultado["n_puladas_composicao_duplicada"] == 5
    assert resultado["n_puladas_sobrevivencia"] == 0
    assert resultado["n_puladas_perda_diaria"] == 0
    assert resultado["n_avaliadas"] == 6

    alocacoes = [r["alocacao"] for r in resultado["resultados"]]
    esperadas = [
        {"resgat": 0, "gridhedge": 1},
        {"resgat": 1, "gridhedge": 0},
        {"resgat": 1, "gridhedge": 1},
        {"resgat": 1, "gridhedge": 2},
        {"resgat": 2, "gridhedge": 1},
        {"resgat": 4, "gridhedge": 1},
    ]
    for esperada in esperadas:
        assert esperada in alocacoes
    # as versões escaladas NÃO devem sobreviver -- só a de menor escala.
    assert {"resgat": 0, "gridhedge": 2} not in alocacoes
    assert {"resgat": 2, "gridhedge": 0} not in alocacoes
    assert {"resgat": 4, "gridhedge": 0} not in alocacoes
    assert {"resgat": 2, "gridhedge": 2} not in alocacoes
    assert {"resgat": 4, "gridhedge": 2} not in alocacoes


def test_buscar_combinacoes_portfolio_com_filtros_sobrevivencia():
    diarios = _diarios_reais()
    resultado = buscar_combinacoes_portfolio_com_filtros(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        min_robos_ativos=2, margem_maxima=12000.0, **_PARAMS_10_8,
    )
    assert resultado["n_combinacoes_totais"] == 12
    assert resultado["n_puladas_composicao_duplicada"] == 0
    assert resultado["n_puladas_sobrevivencia"] == 7
    assert resultado["n_puladas_perda_diaria"] == 0
    assert resultado["n_avaliadas"] == 5

    alocacoes = [r["alocacao"] for r in resultado["resultados"]]
    assert {"resgat": 0, "gridhedge": 1, "romanos2": 2} in alocacoes
    assert {"resgat": 3, "gridhedge": 0, "romanos2": 2} in alocacoes
    assert {"resgat": 3, "gridhedge": 1, "romanos2": 0} in alocacoes
    assert {"resgat": 6, "gridhedge": 0, "romanos2": 2} in alocacoes
    assert {"resgat": 6, "gridhedge": 1, "romanos2": 0} in alocacoes
    # margem 13.000/16.000 > 12.000 -- podadas mesmo tendo 3 robôs ativos.
    assert {"resgat": 3, "gridhedge": 1, "romanos2": 2} not in alocacoes
    assert {"resgat": 6, "gridhedge": 1, "romanos2": 2} not in alocacoes


def test_buscar_combinacoes_portfolio_com_filtros_limite_por_cluster():
    # Continuação de "Clusters de risco": impor um limite de contratos
    # POR CLUSTER (não só por robô individual) nas restrições da busca --
    # backlog de prompts/otimizacao.pdf §4/§5. resgat+gridhedge no mesmo
    # cluster (hipotético, não pela correlação real -- só para testar a
    # restrição em si), romanos2 sozinho.
    diarios = _diarios_reais()
    clusters = [["resgat", "gridhedge"], ["romanos2"]]
    resultado = buscar_combinacoes_portfolio_com_filtros(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        clusters=clusters, max_contratos_por_cluster=6, **_PARAMS_10_8,
    )
    assert resultado["n_combinacoes_totais"] == 12
    assert resultado["n_puladas_cluster"] == 2
    assert resultado["n_avaliadas"] == 9

    alocacoes = [r["alocacao"] for r in resultado["resultados"]]
    # resgat=6 + gridhedge=1 -> 7 contratos no cluster, acima do limite.
    assert {"resgat": 6, "gridhedge": 1, "romanos2": 0} not in alocacoes
    assert {"resgat": 6, "gridhedge": 1, "romanos2": 2} not in alocacoes
    # resgat=6 sozinho (gridhedge=0) fica exatamente no limite (6) -- passa.
    assert {"resgat": 6, "gridhedge": 0, "romanos2": 2} in alocacoes


# --- Concentração por CONTRIBUIÇÃO AO DRAWDOWN (backlog de
# prompts/portfolioBuilder.pdf, fora dos épicos do PDF-fonte) --------------
#
# Continuação dos limites por robô/cluster acima -- decisão CONFIRMADA
# com o usuário: em vez de contagem de contratos (já existente) ou
# margem, este limite usa a CONTRIBUIÇÃO REAL AO DRAWDOWN (mesma lógica
# de `contribuicao_risco_por_robo`, extraída para `_contribuicao_
# drawdown_por_robo` para ser reusada aqui sem resincronizar `diarios`
# do zero nem recalcular volatilidade/ES, irrelevantes para este
# filtro). Comparação usa o valor COM SINAL (não `abs`) -- uma
# participação NEGATIVA significa que aquele robô amorteceu o
# drawdown (diversificação), nunca deveria contar como concentração.
# Combinações cuja série combinada nunca teve NENHUM drawdown (raro,
# mas possível) não são podadas por este filtro -- nada para atribuir,
# não é um erro (distinto de `contribuicao_risco_por_robo`, que levanta
# `ValueError` nesse caso -- lá é uma carteira JÁ ESCOLHIDA sendo
# auditada, aqui é uma entre milhares de candidatas de uma busca).
# Valores conferidos por script antes destes testes.


def test_buscar_combinacoes_portfolio_com_filtros_limite_risco_por_robo():
    diarios = _diarios_reais()
    resultado = buscar_combinacoes_portfolio_com_filtros(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        limite_risco_por_robo_pct=90.0, **_PARAMS_10_8,
    )
    assert resultado["n_combinacoes_totais"] == 12
    assert resultado["n_puladas_risco"] == 7
    assert resultado["n_avaliadas"] == 4

    alocacoes = [r["alocacao"] for r in resultado["resultados"]]
    for esperada in [
        {"resgat": 0, "gridhedge": 1, "romanos2": 2},
        {"resgat": 3, "gridhedge": 1, "romanos2": 2},
        {"resgat": 6, "gridhedge": 0, "romanos2": 2},
        {"resgat": 6, "gridhedge": 1, "romanos2": 2},
    ]:
        assert esperada in alocacoes
    # resgat sozinho concentra 100% do drawdown -- podada.
    assert {"resgat": 3, "gridhedge": 0, "romanos2": 0} not in alocacoes
    assert {"resgat": 6, "gridhedge": 0, "romanos2": 0} not in alocacoes


def test_buscar_combinacoes_portfolio_com_filtros_limite_risco_por_cluster():
    diarios = _diarios_reais()
    clusters = [["resgat", "gridhedge"], ["romanos2"]]
    resultado = buscar_combinacoes_portfolio_com_filtros(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        clusters=clusters, limite_risco_por_cluster_pct=95.0, **_PARAMS_10_8,
    )
    assert resultado["n_puladas_risco"] == 7
    assert resultado["n_avaliadas"] == 4
    alocacoes = [r["alocacao"] for r in resultado["resultados"]]
    assert {"resgat": 3, "gridhedge": 1, "romanos2": 2} in alocacoes
    # cluster resgat+gridhedge concentra 100% do drawdown (romanos2 == 0).
    assert {"resgat": 3, "gridhedge": 1, "romanos2": 0} not in alocacoes


# --- Máximo de contratos NO TOTAL (backlog de
# prompts/portfolioBuilder.pdf §"Passo 3", fora dos épicos do PDF-fonte) ---
#
# Distinto de `max_contratos_por_cluster` (soma dentro de um grupo) --
# aqui é a soma de TODOS os robôs da alocação, qualquer que seja o
# agrupamento. Camada 1 (sobrevivência), pura aritmética sobre a
# combinação -- pruning acontece ANTES de qualquer outro filtro, no
# mesmo ponto do dedupe de composição/escala.


def test_buscar_combinacoes_portfolio_com_filtros_max_contratos_total():
    diarios = _diarios_reais()
    resultado = buscar_combinacoes_portfolio_com_filtros(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        max_contratos_total=5, **_PARAMS_10_8,
    )
    assert resultado["n_combinacoes_totais"] == 12
    assert resultado["n_puladas_sobrevivencia"] == 5
    assert resultado["n_avaliadas"] == 6

    alocacoes = [r["alocacao"] for r in resultado["resultados"]]
    for esperada in [
        {"resgat": 0, "gridhedge": 0, "romanos2": 2},
        {"resgat": 0, "gridhedge": 1, "romanos2": 0},
        {"resgat": 0, "gridhedge": 1, "romanos2": 2},
        {"resgat": 3, "gridhedge": 0, "romanos2": 0},
        {"resgat": 3, "gridhedge": 0, "romanos2": 2},
        {"resgat": 3, "gridhedge": 1, "romanos2": 0},
    ]:
        assert esperada in alocacoes
    # total 6, 7, 8 ou 9 contratos -- acima do limite de 5.
    assert {"resgat": 3, "gridhedge": 1, "romanos2": 2} not in alocacoes
    assert {"resgat": 6, "gridhedge": 0, "romanos2": 0} not in alocacoes


def test_buscar_combinacoes_portfolio_com_filtros_perda_diaria_maxima():
    diarios = _diarios_reais()
    resultado = buscar_combinacoes_portfolio_com_filtros(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        perda_diaria_maxima=-1000.0, **_PARAMS_10_8,
    )
    assert resultado["n_puladas_perda_diaria"] == 7
    assert resultado["n_avaliadas"] == 4
    alocacoes = [r["alocacao"] for r in resultado["resultados"]]
    for esperada in [
        {"resgat": 0, "gridhedge": 0, "romanos2": 2},
        {"resgat": 0, "gridhedge": 1, "romanos2": 0},
        {"resgat": 3, "gridhedge": 0, "romanos2": 0},
        {"resgat": 3, "gridhedge": 0, "romanos2": 2},
    ]:
        assert esperada in alocacoes


# --- MDD máximo (backlog de prompts/portfolioBuilder.pdf "Passo 2",
# fora dos épicos do PDF-fonte) --------------------------------------------
#
# Distinto de `perda_diaria_maxima` (pior DIA histórico) -- este filtro
# usa o MDD (drawdown peak-to-trough) da combinação, calculado
# diretamente (`drawdowns.*` sobre a série combinada) sem rodar
# `metricas_agregadas` inteira (que também calcula TUW/pior mês/lucro
# mensal, irrelevantes para este filtro) -- mesmo espírito de custo
# incremental modesto já documentado para os filtros de risco por
# drawdown. Serve para o "MDD de projeto" do Passo 2 do Builder
# efetivamente restringir a busca, não só rotular o resultado depois.


def test_buscar_combinacoes_portfolio_com_filtros_mdd_maximo():
    diarios = _diarios_reais()
    resultado = buscar_combinacoes_portfolio_com_filtros(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        mdd_maximo=-3000.0, **_PARAMS_10_8,
    )
    assert resultado["n_puladas_mdd"] == 7
    assert resultado["n_avaliadas"] == 4
    alocacoes = [r["alocacao"] for r in resultado["resultados"]]
    for esperada in [
        {"resgat": 3, "gridhedge": 0, "romanos2": 0},
        {"resgat": 3, "gridhedge": 1, "romanos2": 0},
        {"resgat": 3, "gridhedge": 0, "romanos2": 2},
        {"resgat": 0, "gridhedge": 0, "romanos2": 2},
    ]:
        assert esperada in alocacoes
    assert {"resgat": 6, "gridhedge": 1, "romanos2": 2} not in alocacoes


def test_buscar_combinacoes_portfolio_com_filtros_equivale_a_busca_original_sem_filtros():
    # Sem nenhum filtro/dedupe ligado, deve reproduzir EXATAMENTE
    # buscar_combinacoes_portfolio -- é o MESMO pipeline por combinação,
    # só muda a camada de seleção de quais combinações chegam nele.
    diarios = _diarios_reais()
    original = buscar_combinacoes_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8, **_PARAMS_10_8,
    )
    novo = buscar_combinacoes_portfolio_com_filtros(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8, **_PARAMS_10_8,
    )
    assert novo["n_avaliadas"] == len(original)
    chave = lambda r: tuple(sorted(r["alocacao"].items()))
    assert sorted(novo["resultados"], key=chave) == sorted(original, key=chave)


def test_buscar_combinacoes_portfolio_com_filtros_excede_limite_levanta_erro():
    diarios = _diarios_reais()
    candidatos_grandes = {"resgat": list(range(50)), "gridhedge": list(range(50)), "romanos2": list(range(50))}
    with pytest.raises(ValueError, match="excede o limite"):
        buscar_combinacoes_portfolio_com_filtros(
            diarios, _MARGENS_POR_CONTRATO_10_8, candidatos_grandes,
        )


# --- Funil de seleção em 4 camadas (backlog de prompts/otimizacao.pdf §6,
# fora dos épicos do PDF-fonte) --------------------------------------------
#
# "Eu não escolheria entre 'máximo RLT' e 'mínimo MDD'. Usaria uma
# sequência [de camadas]." Forma CONFIRMADA com o usuário antes de
# implementar (AGENTS.md §24, TASKS.md já sinalizava "precisa de
# alinhamento antes de tocar"):
#   1. sobrevivência: reusa `buscar_combinacoes_portfolio_com_filtros`
#      (já existe, nenhuma lógica nova aqui).
#   2. eficiência: ranqueia os sobreviventes por RLT/|MDD| (computável
#      dos campos já existentes, nenhuma fórmula nova) e mantém os
#      `top_n_eficiencia` melhores.
#   3. robustez: roda `vizinhanca_local` (já existe) em cada um dos
#      `top_n_eficiencia`, elimina quem tem a MÉDIA do RLT das vizinhas
#      abaixo de `(1 - tolerancia_robustez_pct/100) × RLT da base` --
#      "todas as vizinhas ruins" vira "média das vizinhas ruim" (critério
#      de agregação, não literal do documento, mas a leitura mais direta
#      de "a carteira E as vizinhas são boas" como afirmação coletiva).
#      Sem walk-forward ainda (backlog separado), esta é a única
#      evidência de robustez disponível hoje.
#   4. simplicidade: entre os sobreviventes da camada 3, ordena por
#      eficiência decrescente e, como desempate, por total de contratos
#      crescente -- não uma comparação de similaridade epsilon (isso já
#      existe separadamente na Fronteira de Pareto).
# Cada camada expõe os avaliados E os sobreviventes -- mesmo princípio
# de transparência já usado nos filtros de sobrevivência e no
# epsilon-Pareto (nunca esconder o que foi descartado). Valores
# conferidos por script antes destes testes.

_PARAMS_FUNIL = dict(percentil_cauda=95, fracao_reserva_operacional=0.10, increment=500)


def test_funil_selecao_portfolio_encaminha_max_contratos_total_e_mdd_maximo():
    # Backlog de prompts/portfolioBuilder.pdf: funil_selecao_portfolio
    # precisa encaminhar os filtros novos da camada 1
    # (max_contratos_total/mdd_maximo/limite_risco_por_robo_pct/
    # limite_risco_por_cluster_pct) para buscar_combinacoes_portfolio_
    # com_filtros -- senão o Builder não consegue restringir a busca
    # pelo orçamento de risco (Passo 2) nem pela concentração (Passo 3).
    diarios = _diarios_reais()
    funil = funil_selecao_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        max_contratos_total=5, mdd_maximo=-3000.0, **_PARAMS_FUNIL,
    )
    camada1 = funil["camada1_sobrevivencia"]
    assert camada1["n_combinacoes_totais"] == 12
    # mesmos números já verificados isoladamente para cada filtro --
    # aqui só confirma que chegam à camada 1 quando passados por aqui.
    assert camada1["n_puladas_sobrevivencia"] >= 5  # max_contratos_total=5 sozinho já poda 5
    assert camada1["n_puladas_mdd"] >= 0
    for r in camada1["resultados"]:
        assert sum(r["alocacao"].values()) <= 5
        assert r["mdd"] >= -3000.0


def test_funil_selecao_portfolio_camada2_eficiencia():
    diarios = _diarios_reais()
    funil = funil_selecao_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        top_n_eficiencia=5, tolerancia_robustez_pct=20.0, **_PARAMS_FUNIL,
    )
    assert funil["camada1_sobrevivencia"]["n_avaliadas"] == 11

    camada2 = funil["camada2_eficiencia"]
    assert len(camada2) == 5
    alocacoes_camada2 = [r["alocacao"] for r in camada2]
    assert alocacoes_camada2[0] == {"resgat": 3, "gridhedge": 0, "romanos2": 0}
    assert camada2[0]["eficiencia_rlt_mdd"] == pytest.approx(0.0015381976514051985, abs=1e-8)
    assert alocacoes_camada2[-1] == {"resgat": 3, "gridhedge": 1, "romanos2": 2}
    # ordem estritamente decrescente por eficiência.
    assert [r["eficiencia_rlt_mdd"] for r in camada2] == sorted(
        [r["eficiencia_rlt_mdd"] for r in camada2], reverse=True,
    )


def test_funil_selecao_portfolio_camada3_robustez():
    diarios = _diarios_reais()
    funil = funil_selecao_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        top_n_eficiencia=5, tolerancia_robustez_pct=20.0, **_PARAMS_FUNIL,
    )
    camada3 = funil["camada3_robustez"]
    assert len(camada3["avaliados"]) == 5
    assert len(camada3["sobreviventes"]) == 3

    por_alocacao = {tuple(sorted(r["alocacao"].items())): r for r in camada3["avaliados"]}
    caso_nao_robusto = por_alocacao[tuple(sorted({"resgat": 3, "gridhedge": 0, "romanos2": 0}.items()))]
    assert caso_nao_robusto["robusto"] is False
    assert caso_nao_robusto["media_rlt_vizinhas"] == pytest.approx(2.2979020163754376, abs=1e-6)

    caso_robusto = por_alocacao[tuple(sorted({"resgat": 0, "gridhedge": 0, "romanos2": 2}.items()))]
    assert caso_robusto["robusto"] is True
    assert caso_robusto["media_rlt_vizinhas"] == pytest.approx(2.3849827428499557, abs=1e-6)

    alocacoes_sobreviventes = [r["alocacao"] for r in camada3["sobreviventes"]]
    assert {"resgat": 0, "gridhedge": 0, "romanos2": 2} in alocacoes_sobreviventes
    assert {"resgat": 3, "gridhedge": 0, "romanos2": 2} in alocacoes_sobreviventes
    assert {"resgat": 3, "gridhedge": 1, "romanos2": 2} in alocacoes_sobreviventes
    assert {"resgat": 3, "gridhedge": 0, "romanos2": 0} not in alocacoes_sobreviventes
    assert {"resgat": 6, "gridhedge": 0, "romanos2": 0} not in alocacoes_sobreviventes


def test_funil_selecao_portfolio_camada4_simplicidade():
    diarios = _diarios_reais()
    funil = funil_selecao_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8,
        top_n_eficiencia=5, tolerancia_robustez_pct=20.0, **_PARAMS_FUNIL,
    )
    camada4 = funil["camada4_simplicidade"]
    assert len(camada4) == 3
    assert [r["alocacao"] for r in camada4] == [
        {"resgat": 0, "gridhedge": 0, "romanos2": 2},
        {"resgat": 3, "gridhedge": 0, "romanos2": 2},
        {"resgat": 3, "gridhedge": 1, "romanos2": 2},
    ]
    assert [r["total_contratos"] for r in camada4] == [2, 5, 6]


# --- Monte Carlo em duas fases: robustez só nos finalistas (backlog de
# prompts/otimizacao.pdf §10, fora dos épicos do PDF-fonte) ----------------
#
# "O Monte Carlo entra DEPOIS da triagem, não para rodar profundamente em
# todas as 6 mil combinações." `robustez_dos_finalistas` roda
# `robustez_portfolio`/os esquemas (`circular_block_bootstrap` ou o novo
# `embaralhamento_dias`, mais `aplicar_choque` opcional) só sobre uma
# lista pequena de finalistas (tipicamente
# `funil_selecao_portfolio(...)['camada4_simplicidade']`) -- nenhuma
# fórmula nova, só reusa `_sincronizar_alocacao` (já existente) e as
# funções de `tradefolio.monte_carlo` diretamente (não
# `robustez_portfolio`, que não expõe esquema/choques -- ela permanece
# intocada e continua servindo o modo Robô único/o uso manual já
# existente na UI). Verificado por equivalência: chamar
# `robustez_dos_finalistas` com uma seed fixa deve reproduzir EXATAMENTE
# o que sincronizar a alocação manualmente e rodar
# `circular_block_bootstrap`/`resumo_trajetorias` à mão daria.


def test_robustez_dos_finalistas_equivale_a_chamada_manual():
    diarios = _diarios_reais()
    finalistas = [
        {"alocacao": {"resgat": 3, "gridhedge": 0, "romanos2": 0}, "limiar_ativo": 5000.0},
        {"alocacao": {"resgat": 0, "gridhedge": 0, "romanos2": 2}, "limiar_ativo": 4000.0},
    ]
    resultados = robustez_dos_finalistas(
        diarios, _MARGENS_POR_CONTRATO_10_8, finalistas,
        tamanho_bloco=10, n_trajetorias=200, horizonte=50, seed=7,
    )
    assert len(resultados) == 2
    assert [r["alocacao"] for r in resultados] == [f["alocacao"] for f in finalistas]

    for r, finalista in zip(resultados, finalistas):
        # reconstrução manual usando o mesmo caminho que buscar_combinacoes_portfolio usa
        diarios_ativos = {}
        margens_manuais = {}
        for nome, n_contratos in finalista["alocacao"].items():
            if n_contratos == 0:
                continue
            d = diarios[nome].copy()
            d["liquido"] = d["liquido_por_contrato"] * n_contratos
            diarios_ativos[nome] = d
            margens_manuais[nome] = _MARGENS_POR_CONTRATO_10_8[nome] * n_contratos
        largo_manual = restringir_janela_comum(sincronizar_portfolio(diarios_ativos))
        base_manual = circular_block_bootstrap(
            largo_manual, tamanho_bloco=10, n_trajetorias=200, horizonte=50, seed=7,
        )
        resumo_manual = resumo_trajetorias(
            base_manual, minimum_margin=sum(margens_manuais.values()), limiar=finalista["limiar_ativo"],
        )
        assert r["lucro_p50"] == pytest.approx(resumo_manual["lucro_p50"])
        assert r["mdd_p95"] == pytest.approx(resumo_manual["mdd_p95"])
        assert r["cdar_95"] == pytest.approx(resumo_manual["cdar_95"])
        assert r["probabilidade_toca_margem"] == pytest.approx(resumo_manual["probabilidade_toca_margem"])
        assert r["esquema"] == "bloco"
        assert r["choques_aplicados"] == []


def test_robustez_dos_finalistas_esquema_embaralhamento():
    diarios = _diarios_reais()
    finalistas = [{"alocacao": {"resgat": 3, "gridhedge": 0, "romanos2": 0}, "limiar_ativo": 5000.0}]
    resultados = robustez_dos_finalistas(
        diarios, _MARGENS_POR_CONTRATO_10_8, finalistas,
        esquema="embaralhamento", n_trajetorias=100, seed=7,
    )
    assert resultados[0]["esquema"] == "embaralhamento"


def test_robustez_dos_finalistas_aplica_choques_em_sequencia():
    diarios = _diarios_reais()
    finalistas = [{"alocacao": {"resgat": 3, "gridhedge": 0, "romanos2": 0}, "limiar_ativo": 5000.0}]
    resultados = robustez_dos_finalistas(
        diarios, _MARGENS_POR_CONTRATO_10_8, finalistas,
        tamanho_bloco=10, n_trajetorias=100, horizonte=50, seed=7,
        choques=["pior_dia_repetido"],
    )
    assert resultados[0]["choques_aplicados"] == ["pior_dia_repetido"]
    # o choque deve pesar no MDD -- comparado à mesma seed sem choque.
    sem_choque = robustez_dos_finalistas(
        diarios, _MARGENS_POR_CONTRATO_10_8, finalistas,
        tamanho_bloco=10, n_trajetorias=100, horizonte=50, seed=7,
    )
    assert resultados[0]["mdd_p50"] <= sem_choque[0]["mdd_p50"]


def test_robustez_dos_finalistas_esquema_invalido_levanta_erro():
    diarios = _diarios_reais()
    finalistas = [{"alocacao": {"resgat": 3, "gridhedge": 0, "romanos2": 0}, "limiar_ativo": 5000.0}]
    with pytest.raises(ValueError, match="esquema"):
        robustez_dos_finalistas(diarios, _MARGENS_POR_CONTRATO_10_8, finalistas, esquema="magico")


# --- Shortlist final com perfis nomeados (backlog de
# prompts/otimizacao.pdf §18, fora dos épicos do PDF-fonte) ----------------
#
# "Permitir ao usuário ver se a otimização complexa realmente supera
# referências simples." Perfis implementados: Minimum Risk (menor MDD
# dentro de um retorno mínimo), Growth (maior lucro dentro de um risco
# máximo), Balanced (ponto da Fronteira de Pareto mais próximo do canto
# ideal normalizado -- técnica padrão de "knee point" em otimização
# multiobjetivo, não uma fórmula inventada), Handcrafted Risk (peso IGUAL
# entre clusters, e DENTRO de cada cluster peso por risco inverso --
# "um voto por cluster", evita que vários robôs correlacionados dominem
# só por serem vários), e os 3 benchmarks fixos: carteira atual do
# usuário (se informada), contratos iguais entre todos os robôs, risco
# inverso GLOBAL (sem olhar clusters). **"Most Robust" deliberadamente
# NÃO implementado** -- o próprio backlog condiciona isso a walk-forward
# existir, que ainda não existe (só robustez local, que já existe).
# Valores conferidos por script antes destes testes.

_PARAMS_SHORTLIST = dict(percentil_cauda=95, fracao_reserva_operacional=0.10, increment=500)


def test_shortlist_portfolio_minimum_risk_e_growth():
    diarios = _diarios_reais()
    resultados = buscar_combinacoes_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8, **_PARAMS_SHORTLIST,
    )
    shortlist = shortlist_portfolio(
        resultados, diarios, _MARGENS_POR_CONTRATO_10_8, total_contratos_benchmark=12,
        retorno_minimo=15000.0, risco_maximo=-3000.0, **_PARAMS_SHORTLIST,
    )
    assert shortlist["minimum_risk"]["alocacao"] == {"resgat": 3, "gridhedge": 0, "romanos2": 0}
    assert shortlist["minimum_risk"]["mdd"] == pytest.approx(-2067.0, abs=1e-2)
    assert shortlist["growth"]["alocacao"] == {"resgat": 3, "gridhedge": 0, "romanos2": 2}
    assert shortlist["growth"]["lucro_total"] == pytest.approx(28268.5, abs=1e-2)


def test_shortlist_portfolio_balanced_e_ponto_da_fronteira():
    diarios = _diarios_reais()
    resultados = buscar_combinacoes_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8, **_PARAMS_SHORTLIST,
    )
    shortlist = shortlist_portfolio(
        resultados, diarios, _MARGENS_POR_CONTRATO_10_8, total_contratos_benchmark=12,
        **_PARAMS_SHORTLIST,
    )
    assert shortlist["balanced"]["alocacao"] == {"resgat": 3, "gridhedge": 1, "romanos2": 2}
    fronteira = fronteira_pareto(resultados, "lucro_total", "mdd")
    assert shortlist["balanced"]["alocacao"] in [r["alocacao"] for r in fronteira]


def test_shortlist_portfolio_handcrafted_risk_um_voto_por_cluster():
    diarios = _diarios_reais()
    resultados = buscar_combinacoes_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8, **_PARAMS_SHORTLIST,
    )
    clusters_singleton = [["resgat"], ["gridhedge"], ["romanos2"]]
    shortlist = shortlist_portfolio(
        resultados, diarios, _MARGENS_POR_CONTRATO_10_8, total_contratos_benchmark=12,
        clusters=clusters_singleton, **_PARAMS_SHORTLIST,
    )
    # com clusters todos de 1 membro, "um voto por cluster" vira
    # exatamente contratos iguais -- ilustra o efeito de dar 1 voto por
    # cluster em vez de por robô (aqui degenerado, mas o mecanismo é o
    # mesmo que evitaria 4 robôs de reversão dominarem por serem vários).
    assert shortlist["handcrafted_risk"]["alocacao"] == {"resgat": 4, "gridhedge": 4, "romanos2": 4}
    assert shortlist["handcrafted_risk"]["alocacao"] == shortlist["contratos_iguais"]["alocacao"]


def test_shortlist_portfolio_risco_inverso_e_contratos_iguais():
    diarios = _diarios_reais()
    resultados = buscar_combinacoes_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8, **_PARAMS_SHORTLIST,
    )
    shortlist = shortlist_portfolio(
        resultados, diarios, _MARGENS_POR_CONTRATO_10_8, total_contratos_benchmark=12,
        **_PARAMS_SHORTLIST,
    )
    assert shortlist["contratos_iguais"]["alocacao"] == {"resgat": 4, "gridhedge": 4, "romanos2": 4}
    # risco inverso favorece o robô de MENOR desvio padrão (gridhedge) --
    # diferente de contratos iguais, exatamente por isso é um benchmark
    # distinto.
    assert shortlist["risco_inverso"]["alocacao"] == {"resgat": 4, "gridhedge": 5, "romanos2": 3}


def test_shortlist_portfolio_carteira_atual_quando_informada():
    diarios = _diarios_reais()
    resultados = buscar_combinacoes_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8, **_PARAMS_SHORTLIST,
    )
    alocacao_atual = {"resgat": 3, "gridhedge": 1, "romanos2": 2}
    shortlist = shortlist_portfolio(
        resultados, diarios, _MARGENS_POR_CONTRATO_10_8, total_contratos_benchmark=12,
        alocacao_atual=alocacao_atual, **_PARAMS_SHORTLIST,
    )
    assert shortlist["carteira_atual"]["alocacao"] == alocacao_atual
    esperado = next(r for r in resultados if r["alocacao"] == alocacao_atual)
    assert shortlist["carteira_atual"]["mdd"] == pytest.approx(esperado["mdd"], abs=1e-2)
    assert shortlist["carteira_atual"]["lucro_total"] == pytest.approx(esperado["lucro_total"], abs=1e-2)


def test_shortlist_portfolio_sem_carteira_atual_ou_clusters_omite_chaves():
    diarios = _diarios_reais()
    resultados = buscar_combinacoes_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8, **_PARAMS_SHORTLIST,
    )
    shortlist = shortlist_portfolio(
        resultados, diarios, _MARGENS_POR_CONTRATO_10_8, total_contratos_benchmark=12,
        **_PARAMS_SHORTLIST,
    )
    assert "carteira_atual" not in shortlist
    assert "handcrafted_risk" not in shortlist
    assert "most_robust" not in shortlist  # deliberadamente não implementado (walk-forward ausente)


# --- Curva de limiares (backlog de prompts/otimizacao.pdf, fora dos
# épicos do PDF-fonte) -----------------------------------------------------
#
# Documento-fonte §7: em vez de pedir ao usuário um único MDD máximo,
# gerar uma curva com vários limiares e, "para cada limiar, retornar
# somente a carteira de maior RLT". Distinto do objetivo já existente
# "maximizar_lucro_com_limite_mdd" em `selecionar_melhores_combinacoes`
# (que maximiza LUCRO sob a mesma restrição de MDD) -- RLT e lucro bruto
# são objetivos diferentes, substituir um pelo outro silenciosamente
# desrepresentaria o que "melhor" significa aqui (AGENTS.md §8), por
# isso `curva_limiares_mdd` é uma função própria, não uma chamada
# repetida ao objetivo já existente. Valores conferidos por script antes
# destes testes.


def test_curva_limiares_mdd():
    diarios = _diarios_reais()
    resultados = buscar_combinacoes_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8, **_PARAMS_10_8,
    )
    curva = curva_limiares_mdd(resultados, limites_mdd=[-1000.0, -2000.0, -3000.0, -5000.0])

    assert [ponto["limite_mdd"] for ponto in curva] == [-1000.0, -2000.0, -3000.0, -5000.0]

    assert curva[0]["n_combinacoes_validas"] == 0
    assert curva[0]["melhor"] is None
    assert curva[1]["n_combinacoes_validas"] == 0
    assert curva[1]["melhor"] is None

    assert curva[2]["n_combinacoes_validas"] == 4
    assert curva[2]["melhor"]["alocacao"] == {"resgat": 3, "gridhedge": 0, "romanos2": 0}
    assert curva[2]["melhor"]["rlt_acumulado"] == pytest.approx(3.1794545454545453, abs=1e-6)

    assert curva[3]["n_combinacoes_validas"] == 11
    assert curva[3]["melhor"]["alocacao"] == {"resgat": 6, "gridhedge": 0, "romanos2": 0}
    assert curva[3]["melhor"]["rlt_acumulado"] == pytest.approx(3.330857142857143, abs=1e-6)


def test_curva_limiares_mdd_lista_vazia():
    assert curva_limiares_mdd([], limites_mdd=[-1000.0]) == [
        {"limite_mdd": -1000.0, "n_combinacoes_validas": 0, "melhor": None},
    ]


# --- Robustez local para contratos inteiros (backlog de
# prompts/otimizacao.pdf §9, fora dos épicos do PDF-fonte) ----------------
#
# "Teste vizinhas [±1 contrato por robô, uma de cada vez] e transferências
# [-1 num robô, +1 noutro]. Se a carteira é excelente mas todas as
# vizinhas são ruins, ela provavelmente explora uma coincidência
# histórica. Se a carteira e as vizinhas são boas, é um platô robusto."
# `vizinhanca_local` NÃO decide "robusto ou não" (é uma tolerância de
# produto, não uma convenção do PDF-fonte) -- só calcula a base e cada
# vizinha, mesmo formato de `buscar_combinacoes_portfolio` mais um campo
# `tipo` identificando a perturbação. Reusa `_sincronizar_alocacao`/
# `_metricas_de_alocacao` (extraídos de `buscar_combinacoes_portfolio_
# com_filtros` para as duas funções novas compartilharem -- a função
# ORIGINAL `buscar_combinacoes_portfolio` permanece intocada, pedido
# explícito do usuário). Valores conferidos por script (uma "busca" de
# 1 candidato por vizinha, via `buscar_combinacoes_portfolio` já testada)
# antes destes testes.

_BASE_VIZINHANCA = {"resgat": 3, "gridhedge": 1, "romanos2": 2}


def test_vizinhanca_local_base_e_contagem():
    diarios = _diarios_reais()
    resultado = vizinhanca_local(
        _BASE_VIZINHANCA, diarios, _MARGENS_POR_CONTRATO_10_8, **_PARAMS_10_8,
    )
    assert resultado["base"]["alocacao"] == _BASE_VIZINHANCA
    assert resultado["base"]["mdd"] == pytest.approx(-3281.0, abs=1e-2)
    assert resultado["base"]["rlt_acumulado"] == pytest.approx(2.0669958823529413, abs=1e-6)
    # 3 robôs × 2 (±1) + 6 transferências (permutations de 3, 2 a 2)
    assert len(resultado["vizinhas"]) == 12


def test_vizinhanca_local_perturbacao_unica_por_robo():
    # "tipo" identifica QUAL robô mudou (ex. "±1 resgat"), não a direção
    # -- as duas direções (-1/+1) do mesmo robô compartilham o mesmo
    # rótulo de tipo; a direção já está implícita na própria `alocacao`.
    diarios = _diarios_reais()
    resultado = vizinhanca_local(
        _BASE_VIZINHANCA, diarios, _MARGENS_POR_CONTRATO_10_8, **_PARAMS_10_8,
    )
    tipos_resgat = [v for v in resultado["vizinhas"] if v["tipo"] == "±1 resgat"]
    assert len(tipos_resgat) == 2  # -1 e +1

    esperados = {
        ("resgat", 2): (-3323.5, 2.0611622916666663, 32978.596666666665),
        ("resgat", 4): (-3323.8333333333344, 2.0161763963963963, 37299.26333333333),
        ("gridhedge", 0): (-2755.5, 2.4581304347826087, 28268.5),
        ("gridhedge", 2): (-4928.100000000002, 1.7503900000000001, 42009.36),
        ("romanos2", 1): (-2379.01, 1.7317985714285715, 24245.18),
        ("romanos2", 3): (-4722.5, 2.2454965853658537, 46032.68),
    }
    vizinhas_por_alocacao = {tuple(sorted(v["alocacao"].items())): v for v in resultado["vizinhas"]}
    for (nome, novo_valor), (mdd, rlt, lucro) in esperados.items():
        aloc = dict(_BASE_VIZINHANCA)
        aloc[nome] = novo_valor
        v = vizinhas_por_alocacao[tuple(sorted(aloc.items()))]
        assert v["tipo"] == f"±1 {nome}"
        assert v["mdd"] == pytest.approx(mdd, abs=1e-2)
        assert v["rlt_acumulado"] == pytest.approx(rlt, abs=1e-6)
        assert v["lucro_total"] == pytest.approx(lucro, abs=1e-2)


def test_vizinhanca_local_transferencias():
    diarios = _diarios_reais()
    resultado = vizinhanca_local(
        _BASE_VIZINHANCA, diarios, _MARGENS_POR_CONTRATO_10_8, **_PARAMS_10_8,
    )
    vizinhas_por_alocacao = {tuple(sorted(v["alocacao"].items())): v for v in resultado["vizinhas"]}

    caso = {"resgat": 2, "gridhedge": 2, "romanos2": 2}  # transferência resgat->gridhedge
    v = vizinhas_por_alocacao[tuple(sorted(caso.items()))]
    assert v["tipo"] == "transferência resgat -> gridhedge"
    assert v["mdd"] == pytest.approx(-5471.433333333334, abs=1e-2)
    assert v["rlt_acumulado"] == pytest.approx(1.6957032624113475, abs=1e-6)

    caso2 = {"resgat": 3, "gridhedge": 0, "romanos2": 3}  # transferência gridhedge->romanos2
    v2 = vizinhas_por_alocacao[tuple(sorted(caso2.items()))]
    assert v2["tipo"] == "transferência gridhedge -> romanos2"
    assert v2["rlt_acumulado"] == pytest.approx(2.6108166666666666, abs=1e-6)


def test_vizinhanca_local_nunca_gera_contratos_negativos():
    diarios = _diarios_reais()
    resultado = vizinhanca_local(
        {"resgat": 0, "gridhedge": 1, "romanos2": 2}, diarios, _MARGENS_POR_CONTRATO_10_8, **_PARAMS_10_8,
    )
    for v in resultado["vizinhas"]:
        assert all(n >= 0 for n in v["alocacao"].values())
    # resgat=0 só tem a direção +1 -- "±1 resgat" -1 não deveria existir
    tipos = [v["tipo"] for v in resultado["vizinhas"]]
    assert tipos.count("±1 resgat") == 1


def test_vizinhanca_local_sem_transferencias():
    diarios = _diarios_reais()
    resultado = vizinhanca_local(
        _BASE_VIZINHANCA, diarios, _MARGENS_POR_CONTRATO_10_8,
        incluir_transferencias=False, **_PARAMS_10_8,
    )
    assert len(resultado["vizinhas"]) == 6
    assert all("transferência" not in v["tipo"] for v in resultado["vizinhas"])


def test_vizinhanca_local_carteira_base_degenerada_levanta_erro():
    diarios = _diarios_reais()
    with pytest.raises(ValueError, match="degenerada"):
        vizinhanca_local({"resgat": 0, "gridhedge": 0, "romanos2": 0}, diarios, _MARGENS_POR_CONTRATO_10_8)


# --- Robustez (Monte Carlo) do portfólio ---------------------------------
#
# tarefas e épicos.pdf tarefa 8.1: "Para portfólio: Todos os robôs
# permanecem sincronizados pela data." A máquina de bootstrap
# (tradefolio.monte_carlo.circular_block_bootstrap/resumo_trajetorias) já
# foi construída para isso desde o Épico 8 -- aceita um pd.DataFrame
# multi-coluna e soma entre colunas por trajetória (mesma linha/data
# sorteada para todos os robôs juntos, preservando a correlação real
# entre eles em cada bloco sorteado). Nenhuma fórmula nova aqui, só
# reuso. Valores conferidos por script (seed fixa) antes destes testes.


def test_robustez_portfolio_reusa_bootstrap_multi_coluna():
    diarios = _diarios_reais()
    largo = restringir_janela_comum(sincronizar_portfolio(diarios))

    resumo = robustez_portfolio(
        largo, tamanho_bloco=20, n_trajetorias=2000, horizonte=252, seed=42,
        minimum_margin=45000.0, limiar=53000.0,
    )

    assert resumo["seed"] == 42
    assert resumo["tamanho_bloco"] == 20
    assert resumo["n_trajetorias"] == 2000
    assert resumo["horizonte"] == 252
    assert resumo["lucro_p50"] == pytest.approx(33425.94000000001, abs=1e-2)
    assert resumo["mdd_p95"] == pytest.approx(-5517.5594999999985, abs=1e-2)
    assert resumo["probabilidade_prejuizo"] == pytest.approx(0.0, abs=1e-9)
    assert resumo["probabilidade_toca_margem"] == pytest.approx(0.0, abs=1e-9)
    assert resumo["probabilidade_termina_abaixo_do_limiar"] == pytest.approx(0.9995, abs=1e-4)


def test_robustez_portfolio_preenche_nan_com_zero_antes_de_reamostrar():
    # Escopo "união" (usar_janela_comum=False) tem NaN antes de cada robô
    # existir -- robustez_portfolio deve tratar isso como 0 (mesma
    # convenção de serie_combinada), não deixar NaN vazar pro bootstrap.
    diarios = _diarios_reais()
    largo_uniao = sincronizar_portfolio(diarios)
    assert largo_uniao.isna().any().any()  # confirma que há NaN de fato

    resumo = robustez_portfolio(largo_uniao, tamanho_bloco=20, n_trajetorias=100, horizonte=50, seed=1)
    assert not any(v != v for v in (resumo["lucro_p50"], resumo["mdd_p50"]))  # sem NaN no resultado


def test_robustez_portfolio_sem_minimum_margin_ou_limiar_omite_chaves():
    diarios = _diarios_reais()
    largo = restringir_janela_comum(sincronizar_portfolio(diarios))
    resumo = robustez_portfolio(largo, tamanho_bloco=20, n_trajetorias=100, horizonte=50, seed=1)
    assert "probabilidade_toca_margem" not in resumo
    assert "probabilidade_termina_abaixo_do_limiar" not in resumo


# --- Fronteira de Pareto discreta (pedido de acompanhamento do usuário,
# fora dos épicos do PDF-fonte) -----------------------------------------
#
# Discutido com o usuário antes de implementar: Markowitz (pesos
# contínuos, variância como risco) não encaixa neste domínio (contratos
# são discretos; o projeto inteiro já usa MDD/ES/limiar como vocabulário
# de risco, não variância/Sharpe). A fronteira de Pareto DISCRETA, sobre
# as combinações que `buscar_combinacoes_portfolio` já calcula, não
# precisa de nenhuma convenção nova: só identifica quais combinações já
# testadas não são dominadas por nenhuma outra (nenhuma outra é
# simultaneamente igual/melhor nos dois eixos e estritamente melhor em
# pelo menos um). Convenção "maior é melhor" nos dois eixos -- eixos de
# risco (mdd/es_95/mdd_sobre_limiar) já são negativos nesta base de
# código, então "maior" = "menos negativo" = mais seguro, sem precisar
# inverter sinal. Valores conferidos por script antes destes testes.


def test_fronteira_pareto_lucro_vs_mdd():
    diarios = _diarios_reais()
    resultados = buscar_combinacoes_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8, **_PARAMS_10_8,
    )
    fronteira = fronteira_pareto(resultados, eixo_retorno="lucro_total", eixo_risco="mdd")

    alocacoes = [r["alocacao"] for r in fronteira]
    assert alocacoes == [
        {"resgat": 6, "gridhedge": 1, "romanos2": 2},
        {"resgat": 3, "gridhedge": 1, "romanos2": 2},
        {"resgat": 3, "gridhedge": 0, "romanos2": 2},
        {"resgat": 3, "gridhedge": 0, "romanos2": 0},
    ]
    # dominada por {resgat:3, gridhedge:1, romanos2:2} (lucro maior E mdd
    # melhor) -- não deve aparecer na fronteira.
    assert {"resgat": 6, "gridhedge": 0, "romanos2": 2} not in alocacoes


def test_fronteira_pareto_rlt_vs_mdd_sobre_limiar():
    diarios = _diarios_reais()
    resultados = buscar_combinacoes_portfolio(
        diarios, _MARGENS_POR_CONTRATO_10_8, _CANDIDATOS_10_8, **_PARAMS_10_8,
    )
    fronteira = fronteira_pareto(resultados, eixo_retorno="rlt_acumulado", eixo_risco="mdd_sobre_limiar")

    alocacoes = [r["alocacao"] for r in fronteira]
    assert alocacoes == [
        {"resgat": 6, "gridhedge": 0, "romanos2": 0},
        {"resgat": 3, "gridhedge": 0, "romanos2": 0},
        {"resgat": 0, "gridhedge": 0, "romanos2": 2},
        {"resgat": 3, "gridhedge": 0, "romanos2": 2},
        {"resgat": 3, "gridhedge": 1, "romanos2": 2},
    ]


def test_fronteira_pareto_vazia_para_lista_vazia():
    assert fronteira_pareto([], eixo_retorno="lucro_total", eixo_risco="mdd") == []


def test_fronteira_pareto_um_unico_resultado_sempre_esta_na_fronteira():
    resultado = {"alocacao": {"a": 1}, "lucro_total": 100.0, "mdd": -10.0}
    assert fronteira_pareto([resultado], eixo_retorno="lucro_total", eixo_risco="mdd") == [resultado]


# --- Epsilon-Pareto (tolerância econômica) -- backlog de
# prompts/otimizacao.pdf §8, fora dos épicos do PDF-fonte ------------------
#
# "A diferença entre RLT R$80.000/MDD R$14.000 e RLT R$80.200/MDD
# R$14.100 provavelmente não é economicamente relevante" -- o documento
# pede tolerância por eixo para tratar combinações "economicamente
# iguais" como uma só. Tolerância é decisão de PRODUTO, não convenção
# financeira do PDF-fonte -- perguntado ao usuário antes de implementar
# (AGENTS.md §24): resposta foi deixar configurável ao vivo na UI, sem
# fixar um padrão no código -- por isso `tolerancia_retorno_pct`/
# `tolerancia_risco_pct` são parâmetros com default `0.0` (nenhuma
# tolerância -- reproduz exatamente o comportamento anterior de
# `fronteira_pareto`, só dedup de empates exatos), não um valor do
# documento-fonte (1%/2%) fixado no código; a UI em `app.py` que decide
# expor 1%/2% como valor inicial dos campos.
#
# Algoritmo: sobre a fronteira ESTRITA já calculada (skyline, inalterado
# acima), varre em ordem de retorno decrescente mantendo um
# "representante" -- um ponto cujos dois eixos estejam dentro da
# tolerância (relativa, `abs(diferenca) / abs(valor_do_representante)`)
# do representante ATUAL é agrupado com ele e descartado; um ponto fora
# da tolerância em qualquer eixo vira o novo representante. Comparação
# sempre contra o representante fixo do grupo corrente (nunca contra o
# último ponto agrupado) -- evita "encadeamento" onde uma sequência de
# pontos levemente distantes uns dos outros acabaria colapsando pontos
# muito distantes entre si. Valores conferidos à mão (dados sintéticos
# pequenos, para isolar o algoritmo de ruído de dado real).

_FRONTEIRA_EPSILON_SINTETICA = [
    {"alocacao": {"a": 1}, "lucro_total": 10000.0, "mdd": -1000.0},
    {"alocacao": {"a": 2}, "lucro_total": 9950.0, "mdd": -980.0},   # 0.5% retorno, 2.0% risco de #1 -> agrupa
    {"alocacao": {"a": 3}, "lucro_total": 8000.0, "mdd": -500.0},   # 20% de #1 -> não agrupa, vira representante
    {"alocacao": {"a": 4}, "lucro_total": 5000.0, "mdd": -100.0},   # 37.5% de #3 -> não agrupa
]


def test_fronteira_pareto_epsilon_agrupa_pontos_proximos():
    fronteira = fronteira_pareto(
        _FRONTEIRA_EPSILON_SINTETICA, eixo_retorno="lucro_total", eixo_risco="mdd",
        tolerancia_retorno_pct=1.0, tolerancia_risco_pct=2.0,
    )
    alocacoes = [r["alocacao"] for r in fronteira]
    assert alocacoes == [{"a": 1}, {"a": 3}, {"a": 4}]  # {"a": 2} agrupado com {"a": 1}


def test_fronteira_pareto_epsilon_expoe_combinacoes_agrupadas():
    # Pedido de acompanhamento do usuário: a tabela da UI não mostrava as
    # combinações que o agrupamento epsilon removeu -- cada representante
    # precisa carregar QUEM foi agrupado com ele, não só desaparecer.
    fronteira = fronteira_pareto(
        _FRONTEIRA_EPSILON_SINTETICA, eixo_retorno="lucro_total", eixo_risco="mdd",
        tolerancia_retorno_pct=1.0, tolerancia_risco_pct=2.0,
    )
    representante_1 = next(r for r in fronteira if r["alocacao"] == {"a": 1})
    assert [ag["alocacao"] for ag in representante_1["_agrupados"]] == [{"a": 2}]

    representante_3 = next(r for r in fronteira if r["alocacao"] == {"a": 3})
    assert representante_3["_agrupados"] == []
    representante_4 = next(r for r in fronteira if r["alocacao"] == {"a": 4})
    assert representante_4["_agrupados"] == []


def test_fronteira_pareto_epsilon_zero_reproduz_comportamento_exato():
    # Default (0.0/0.0) -- nenhum agrupamento, só dedup de empates exatos
    # (comportamento anterior a este item, preservado byte a byte).
    fronteira_sem_tolerancia = fronteira_pareto(
        _FRONTEIRA_EPSILON_SINTETICA, eixo_retorno="lucro_total", eixo_risco="mdd",
    )
    fronteira_tolerancia_zero = fronteira_pareto(
        _FRONTEIRA_EPSILON_SINTETICA, eixo_retorno="lucro_total", eixo_risco="mdd",
        tolerancia_retorno_pct=0.0, tolerancia_risco_pct=0.0,
    )
    assert fronteira_sem_tolerancia == fronteira_tolerancia_zero
    alocacoes = [r["alocacao"] for r in fronteira_sem_tolerancia]
    assert alocacoes == [{"a": 1}, {"a": 2}, {"a": 3}, {"a": 4}]  # todos ficam, nenhum é dominado


def test_fronteira_pareto_epsilon_nao_agrupa_alem_do_representante_fixo():
    # Comparação é sempre contra o representante do grupo, não contra o
    # último ponto agrupado -- evita encadeamento.
    pontos = [
        {"alocacao": {"a": 1}, "lucro_total": 100.0, "mdd": -10.0},
        {"alocacao": {"a": 2}, "lucro_total": 99.0, "mdd": -9.9},   # 1% de #1 -> agrupa com #1
        {"alocacao": {"a": 3}, "lucro_total": 98.01, "mdd": -9.801},  # ~1% de #2, mas ~2% de #1 -> NÃO agrupa (representante é #1)
    ]
    fronteira = fronteira_pareto(
        pontos, eixo_retorno="lucro_total", eixo_risco="mdd",
        tolerancia_retorno_pct=1.0, tolerancia_risco_pct=1.0,
    )
    alocacoes = [r["alocacao"] for r in fronteira]
    assert alocacoes == [{"a": 1}, {"a": 3}]


def test_fronteira_pareto_epsilon_lista_vazia():
    assert fronteira_pareto([], eixo_retorno="lucro_total", eixo_risco="mdd", tolerancia_retorno_pct=1.0) == []
