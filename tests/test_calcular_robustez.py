"""
RED: report_data.calcular_robustez ainda não existe.

Orquestra tradefolio.deterioracao + tradefolio.monte_carlo (AGENTS.md
épico 8) na mesma camada que já orquestra calcular_pagina1-6 -- evita
duplicar a lógica de composição em app.py e report.py (as duas UIs
chamam a mesma função, só mudam a apresentação).

Ordem de composição fixa (documentada, não escondida): aumentar_custos ->
aplicar_slippage -> reduzir_ganhos -> ampliar_perdas ->
remover_melhores_dias -> duplicar_piores_dias -> circular_block_bootstrap
-> resumo_trajetorias. Cada transformação só é aplicada se o parâmetro
correspondente for diferente do seu valor neutro (fracao/valor 0, n=0) --
por padrão (todos os parâmetros de deterioração em 0) o comportamento é
exatamente o bootstrap puro, sem nenhuma deterioração.

Valores conferidos por script contra tests/fixtures/romanos_orders.csv
(contratos_referencia=1) antes deste teste: slippage R$2/trade + redução
de ganhos 10% + ampliação de perdas 10%, bloco=20, 500 trajetórias,
horizonte=100, seed=123 -> lucro_p50=2604,40, mdd_p50=-3343,80,
probabilidade_prejuizo=0,226 (minimum_margin=5000 ->
probabilidade_toca_margem=0,026; limiar=8000 ->
probabilidade_termina_abaixo_do_limiar=0,948).
"""
import warnings

import pytest

from tradefolio.report_data import calcular_robustez, montar_dataframe_diario

CSV = "tests/fixtures/romanos_orders.csv"


def _diario():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return montar_dataframe_diario(CSV, contratos_referencia=1)


def test_calcular_robustez_com_deterioracao_e_probabilidades():
    diario = _diario()
    resumo = calcular_robustez(
        diario, tamanho_bloco=20, n_trajetorias=500, horizonte=100, seed=123,
        slippage_por_trade=2.0, reducao_ganhos=0.10, aumento_perdas=0.10,
        minimum_margin=5000, limiar=8000,
    )

    assert resumo["lucro_p50"] == pytest.approx(2604.40, abs=1e-1)
    assert resumo["mdd_p50"] == pytest.approx(-3343.80, abs=1e-1)
    assert resumo["probabilidade_prejuizo"] == pytest.approx(0.226, abs=1e-3)
    assert resumo["probabilidade_toca_margem"] == pytest.approx(0.026, abs=1e-3)
    assert resumo["probabilidade_termina_abaixo_do_limiar"] == pytest.approx(0.948, abs=1e-3)
    assert resumo["seed"] == 123
    assert resumo["tamanho_bloco"] == 20
    assert resumo["n_trajetorias"] == 500
    assert resumo["horizonte"] == 100


def test_calcular_robustez_sem_deterioracao_e_sem_margem_ou_limiar():
    diario = _diario()
    resumo = calcular_robustez(diario, tamanho_bloco=10, n_trajetorias=200, horizonte=50, seed=1)

    assert "probabilidade_toca_margem" not in resumo
    assert "probabilidade_termina_abaixo_do_limiar" not in resumo
    assert "lucro_p50" in resumo
    assert "mdd_p99" in resumo


def test_calcular_robustez_parametros_de_deterioracao_no_neutro_reproduz_bootstrap_puro():
    from tradefolio.monte_carlo import circular_block_bootstrap, resumo_trajetorias

    diario = _diario()
    direto = resumo_trajetorias(
        circular_block_bootstrap(diario["liquido"], tamanho_bloco=15, n_trajetorias=300, horizonte=80, seed=9)
    )
    via_robustez = calcular_robustez(diario, tamanho_bloco=15, n_trajetorias=300, horizonte=80, seed=9)

    assert via_robustez["lucro_p50"] == pytest.approx(direto["lucro_p50"])
    assert via_robustez["mdd_p99"] == pytest.approx(direto["mdd_p99"])
