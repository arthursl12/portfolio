"""
RED: tradefolio.portfolio_builder ainda não existe.

Backlog de `prompts/portfolioBuilder.pdf`, fora dos épicos do PDF-fonte
(tarefas e épicos.pdf). Este módulo é a camada de ORQUESTRAÇÃO do
"Portfolio Builder" (fluxo guiado de 7 passos) -- ele reusa o engine já
existente em `tradefolio.portfolio`/`limiar`/`drawdowns`/`metrics`/
`report_data`, não reimplementa nenhuma fórmula financeira nova
(AGENTS.md §8). Ver `prompts/portfolioBuilder.pdf` e o plano aprovado
para o desenho completo.

Decisões confirmadas com o usuário antes de implementar (AGENTS.md §24):
- Reconciliação do orçamento de risco contra o modelo de limiar já
  existente (não aceitar silenciosamente um teto irrealista).
- Concentração por robô/cluster usa contribuição ao DRAWDOWN (não
  margem nem contagem de contratos) -- ver `test_portfolio.py`'s
  extensão de `buscar_combinacoes_portfolio_com_filtros`.
- Cenário de degradação por EA reaberto, mas só para o finalista já
  escolhido (não a grade inteira de busca).
- Campos de "qualidade dos dados"/"infraestrutura compartilhada" --
  OMITIDOS nesta versão (nenhum dos dois conceitos existe no modelo de
  dados; TASKS.md já sinaliza "qualidade dos dados" como Épico 14, fora
  de escopo).
"""
import warnings

import pandas as pd
import pytest

from tradefolio.portfolio_builder import (
    cenario_degradacao_finalista,
    montar_cartao_ea,
    orcamento_de_risco,
    plano_operacional,
)
from tradefolio.report_data import montar_dataframe_diario

_MARGENS_POR_CONTRATO_10_8 = {"resgat": 1000.0, "gridhedge": 5000.0, "romanos2": 2500.0}
_PARAMS_10_8 = dict(percentil_cauda=95, fracao_reserva_operacional=0.10, increment=500)


def _diarios_reais():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return {
            "resgat": montar_dataframe_diario("dados_exemplo/orders_resgat.csv"),
            "gridhedge": montar_dataframe_diario("dados_exemplo/orders_gridhedge.csv"),
            "romanos2": montar_dataframe_diario("dados_exemplo/orders_romanos2.csv"),
        }

# --- Passo 1: cartão curto por EA -----------------------------------------
#
# Todos os campos reusam funções já existentes (drawdowns/metrics/
# report_data) -- nenhuma fórmula nova. Valores conferidos por script
# contra dados_exemplo/orders_resgat.csv antes destes testes.


def _diario_resgat():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return montar_dataframe_diario("dados_exemplo/orders_resgat.csv")


def test_montar_cartao_ea_campos_basicos():
    diario = _diario_resgat()
    cartao = montar_cartao_ea(diario)

    assert cartao["pregoes"] == 623
    assert cartao["meses_historico"] == pytest.approx(29.86202365308804, abs=1e-6)
    assert cartao["mdd_por_contrato"] == pytest.approx(-689.0, abs=1e-2)
    assert cartao["pior_dia_por_contrato"] == pytest.approx(-222.16666666666666, abs=1e-6)
    assert cartao["tempo_max_recuperacao"] == 102
    assert cartao["dependencia_5_melhores_dias_pct"] == pytest.approx(106.45622462400641, abs=1e-4)


def test_montar_cartao_ea_rlt_por_contrato_so_com_margem():
    diario = _diario_resgat()

    sem_margem = montar_cartao_ea(diario)
    assert sem_margem["rlt_por_contrato"] is None

    com_margem = montar_cartao_ea(diario, margem_por_contrato=1000.0)
    assert com_margem["rlt_por_contrato"] == pytest.approx(2.9145, abs=1e-6)


def test_montar_cartao_ea_alerta_historico_curto():
    diario = _diario_resgat()
    # ~29.86 meses de histórico -- não é curto para o padrão (9 meses,
    # mesmo degrau já usado por limiar._DEGRAUS_INCERTEZA).
    assert montar_cartao_ea(diario)["alerta_historico_curto"] is False
    # limiar bem mais alto que o histórico disponível -> alerta dispara.
    assert montar_cartao_ea(diario, limiar_historico_curto_meses=30)["alerta_historico_curto"] is True


# --- Passo 2: orçamento de risco -------------------------------------------
#
# mdd_projeto = perda_maxima_aceitavel * (1 - margem_seguranca_pct/100) --
# exemplo do próprio documento-fonte: capital R$40.000, perda máxima
# R$15.000, margem 30% -> MDD de projeto R$10.500 (reproduzido abaixo
# exatamente). Reconciliação (decisão confirmada com o usuário): compara
# contra o MDD histórico e o limiar de capital de uma carteira de
# REFERÊNCIA (1 contrato de cada EA candidato) -- ambos calculados por
# quem chama (`metricas_agregadas`/`limiar_agregado_portfolio`, já
# existentes), `orcamento_de_risco` só faz a aritmética/comparação.


def test_orcamento_de_risco_mdd_projeto_exemplo_do_documento():
    orcamento = orcamento_de_risco(
        capital_reservado=40000.0, perda_maxima_aceitavel=15000.0, margem_seguranca_pct=30.0,
    )
    assert orcamento["mdd_projeto"] == pytest.approx(10500.0, abs=1e-6)


def test_orcamento_de_risco_sem_referencia_nao_alerta():
    orcamento = orcamento_de_risco(
        capital_reservado=40000.0, perda_maxima_aceitavel=15000.0, margem_seguranca_pct=30.0,
    )
    assert orcamento["abaixo_do_historico"] is None
    assert orcamento["capital_insuficiente"] is None


def test_orcamento_de_risco_alerta_quando_teto_menor_que_historico():
    orcamento = orcamento_de_risco(
        capital_reservado=40000.0, perda_maxima_aceitavel=15000.0, margem_seguranca_pct=30.0,
        mdd_historico_referencia=-12000.0,  # |{-12000}| = 12000 > mdd_projeto 10500
        limiar_referencia=35000.0,
    )
    assert orcamento["mdd_projeto"] == pytest.approx(10500.0, abs=1e-6)
    assert orcamento["abaixo_do_historico"] is True
    assert orcamento["capital_insuficiente"] is False  # 40000 >= 35000


def test_orcamento_de_risco_sem_alerta_quando_teto_acima_do_historico():
    orcamento = orcamento_de_risco(
        capital_reservado=20000.0, perda_maxima_aceitavel=15000.0, margem_seguranca_pct=30.0,
        mdd_historico_referencia=-5000.0,
        limiar_referencia=35000.0,
    )
    assert orcamento["abaixo_do_historico"] is False
    assert orcamento["capital_insuficiente"] is True  # 20000 < 35000


# --- Passo 6: cenário de degradação de UM EA no finalista já escolhido
# (backlog de prompts/portfolioBuilder.pdf, esquema D reaberto SÓ para
# este contexto estreito -- decisão confirmada com o usuário) -----------
#
# Recompute DETERMINÍSTICO (não Monte Carlo -- "se o EA X perder Y% da
# expectativa" é um único cenário, não uma distribuição): reusa
# `deterioracao.reduzir_ganhos` (já existente, já testado para o modo
# Robô único) sobre a série de referência de UM robô só, dentro da
# alocação JÁ ESCOLHIDA -- nenhuma fórmula nova. `fracao_degradacao`
# mapeia direto para a linguagem do documento-fonte: 0.25 = "cai 25%",
# 0.5 = "cai 50%", 1.0 = "vai a zero" (zera os dias positivos -- só
# sobram as perdas), >1.0 = "torna-se negativa" (`reduzir_ganhos`
# multiplica os dias positivos por `1 - fracao`, que fica negativo
# quando `fracao > 1`, invertendo o sinal desses dias -- mesma função,
# nenhum caso especial). Valores conferidos por script antes destes
# testes (alocação {"resgat":3,"gridhedge":1,"romanos2":2}, EA
# degradado: gridhedge).

_ALOCACAO_DEGRADACAO = {"resgat": 3, "gridhedge": 1, "romanos2": 2}


def test_cenario_degradacao_finalista_baseline_bate_com_busca_original():
    diarios = _diarios_reais()
    resultado = cenario_degradacao_finalista(
        diarios, _ALOCACAO_DEGRADACAO, _MARGENS_POR_CONTRATO_10_8,
        robo_degradado="gridhedge", fracao_degradacao=0.5, **_PARAMS_10_8,
    )
    assert resultado["baseline"]["lucro_total"] == pytest.approx(35138.93, abs=1e-2)
    assert resultado["baseline"]["mdd"] == pytest.approx(-3281.0, abs=1e-2)


def test_cenario_degradacao_finalista_fracoes():
    diarios = _diarios_reais()
    esperados = {
        0.25: (26235.9325, -3475.625),
        0.5: (17332.935, -3670.25),
        1.0: (-473.06, -10258.57),
        1.5: (-18279.055, -23625.305),
    }
    for fracao, (lucro_esperado, mdd_esperado) in esperados.items():
        resultado = cenario_degradacao_finalista(
            diarios, _ALOCACAO_DEGRADACAO, _MARGENS_POR_CONTRATO_10_8,
            robo_degradado="gridhedge", fracao_degradacao=fracao, **_PARAMS_10_8,
        )
        assert resultado["degradado"]["lucro_total"] == pytest.approx(lucro_esperado, abs=1e-2)
        assert resultado["degradado"]["mdd"] == pytest.approx(mdd_esperado, abs=1e-2)
        assert resultado["delta_lucro_total"] == pytest.approx(
            lucro_esperado - 35138.93, abs=1e-2,
        )
        assert resultado["fracao_degradacao"] == fracao
        assert resultado["robo_degradado"] == "gridhedge"


def test_cenario_degradacao_finalista_robo_inexistente_levanta_erro():
    diarios = _diarios_reais()
    with pytest.raises(KeyError):
        cenario_degradacao_finalista(
            diarios, _ALOCACAO_DEGRADACAO, _MARGENS_POR_CONTRATO_10_8,
            robo_degradado="nao_existe", fracao_degradacao=0.5, **_PARAMS_10_8,
        )


# --- Passo 7: plano operacional (backlog de
# prompts/portfolioBuilder.pdf, fora dos épicos do PDF-fonte) --------------
#
# Formatação/bandas PURAS sobre números já calculados nos passos
# anteriores -- nenhuma fórmula nova. `faixas_pct` (padrão 50%/75%/100%
# do MDD de projeto) é um parâmetro explícito e ajustável, mesmo
# tratamento de todo outro "knob" de política já existente neste
# projeto -- não uma reprodução literal dos números de exemplo do
# documento-fonte (que não formam uma fração redonda de R$10.500: são
# só um exemplo ilustrativo, não uma fórmula declarada). Duas das cinco
# regras de acompanhamento do documento-fonte ("replicabilidade",
# "envelope simulado") exigem infraestrutura de acompanhamento ao vivo
# (a seção "Monitor" proposta pelo próprio documento, fora de escopo) --
# retornadas separadamente como lembretes manuais, nunca fingidas como
# sinal automático.


def test_plano_operacional_faixas_de_drawdown():
    plano = plano_operacional(
        alocacao_final={"resgat": 3, "gridhedge": 1, "romanos2": 2},
        margens_por_contrato=_MARGENS_POR_CONTRATO_10_8,
        capital_reservado=40000.0,
        mdd_projeto=10500.0,
    )
    assert plano["faixas"] == [
        {"min_dd": 0.0, "max_dd": 5250.0, "acao": "Operação normal."},
        {"min_dd": 5250.0, "max_dd": 7875.0, "acao": "Não aumentar a mão."},
        {"min_dd": 7875.0, "max_dd": 10500.0, "acao": "Reduzir e investigar."},
        {"min_dd": 10500.0, "max_dd": pytest.approx(float("inf")), "acao": "Suspender novas entradas e revisar o portfólio."},
    ]


def test_plano_operacional_margem_maxima_estimada():
    plano = plano_operacional(
        alocacao_final={"resgat": 3, "gridhedge": 1, "romanos2": 2},
        margens_por_contrato=_MARGENS_POR_CONTRATO_10_8,
        capital_reservado=40000.0,
        mdd_projeto=10500.0,
    )
    assert plano["margem_maxima_estimada"] == pytest.approx(13000.0, abs=1e-6)
    assert plano["capital_reservado"] == 40000.0
    assert plano["mdd_projeto"] == 10500.0
    assert plano["alocacao_final"] == {"resgat": 3, "gridhedge": 1, "romanos2": 2}


def test_plano_operacional_faixas_pct_ajustavel():
    plano = plano_operacional(
        alocacao_final={"resgat": 1}, margens_por_contrato={"resgat": 1000.0},
        capital_reservado=10000.0, mdd_projeto=1000.0, faixas_pct=(0.25, 0.5, 0.75),
    )
    assert [f["max_dd"] for f in plano["faixas"][:3]] == [250.0, 500.0, 750.0]


def test_plano_operacional_regras_computadas_vs_nao_computadas():
    plano = plano_operacional(
        alocacao_final={"resgat": 3, "gridhedge": 1, "romanos2": 2},
        margens_por_contrato=_MARGENS_POR_CONTRATO_10_8,
        capital_reservado=40000.0, mdd_projeto=10500.0, limite_risco_por_robo_pct=40.0,
    )
    assert plano["limite_risco_por_robo_pct"] == 40.0
    assert len(plano["regras_estaticas"]) >= 1
    assert len(plano["regras_nao_computadas"]) == 2
    for regra in plano["regras_nao_computadas"]:
        assert "replicabilidade" in regra.lower() or "envelope" in regra.lower()


def test_plano_operacional_limite_risco_padrao_e_exemplo_do_documento():
    plano = plano_operacional(
        alocacao_final={"resgat": 1}, margens_por_contrato={"resgat": 1000.0},
        capital_reservado=10000.0, mdd_projeto=1000.0,
    )
    assert plano["limite_risco_por_robo_pct"] == 45.0
