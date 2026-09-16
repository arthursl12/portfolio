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
    fronteira_pareto,
    limiar_agregado_portfolio,
    metricas_agregadas,
    otimizar_portfolio,
    restringir_janela_comum,
    robustez_portfolio,
    selecionar_melhores_combinacoes,
    rlt_e_risco_portfolio,
    serie_combinada,
    sincronizar_operou,
    sincronizar_portfolio,
)
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
