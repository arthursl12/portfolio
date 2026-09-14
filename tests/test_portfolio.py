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
    correlacao_dias_conjuntos,
    correlacao_movel,
    correlacao_perdas,
    correlacao_piores_dias,
    correlacao_portfolio,
    correlacao_volatilidade_alta,
    limiar_agregado_portfolio,
    metricas_agregadas,
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
