"""
RED: tradefolio.deterioracao ainda não existe (AGENTS.md épico 8, tarefa
8.3 "cenários deteriorados").

Seis transformações independentes e compostáveis (o PDF-fonte pede
"permitir independentemente", não uma função combinada única) sobre
Series simples -- Series in, Series out -- para poderem ser encadeadas
entre si e alimentar `tradefolio.monte_carlo.circular_block_bootstrap`
diretamente (ex. `circular_block_bootstrap(ampliar_perdas(reduzir_ganhos(serie, 0.1), 0.1), ...)`).

Decisões de design tomadas (documentadas, não escondidas -- AGENTS.md §8):
- `reduzir_ganhos`/`ampliar_perdas` só tocam dias estritamente positivos/
  negativos, respectivamente -- um dia exatamente zero não muda (mesma
  convenção de "quebra de sequência" já usada em
  `metrics.maior_sequencia`).
- `remover_melhores_dias` ZERA (não remove a data) os N maiores valores
  -- a série precisa continuar com o mesmo índice/tamanho para seguir
  alimentando drawdown/bootstrap.
- `duplicar_piores_dias`: sem uma definição literal única no PDF-fonte
  (dobrar o dia NO LUGAR, ou inserir uma data nova?) -- escolhido dobrar
  o valor NO LUGAR (multiplicar por 2), porque inserir uma data exigiria
  decidir onde no calendário B3 ela entraria, quebrando o alinhamento
  com `alignment.preencher_calendario_b3`. Documentado, não uma
  ambiguidade escondida.
- `aumentar_custos`/`aplicar_slippage` recebem as séries componentes
  (`bruto`/`custo`/`n_trades`) em vez do `diario` inteiro -- mantém a
  mesma assinatura "Series in, Series out" das outras quatro, e evita
  decidir se um `custo_mensal` eventualmente presente entraria ou não
  (fica de fora deliberadamente: "aumento de custos" no PDF-fonte é
  sobre o custo de negociação B3, não sobre a assinatura mensal
  pedida pelo usuário, que é um conceito à parte).

Valores conferidos por script contra tests/fixtures/mini_fixture_orders.csv
(contratos_referencia=1) antes deste teste: bruto=[200,-50,-300,0,0],
custo=[1,2,1,0,1], liquido=[199,-52,-301,0,-1], n_trades=[1,2,1,0,1].
"""
import warnings

import pandas as pd
import pytest

from tradefolio.deterioracao import (
    aplicar_slippage,
    aumentar_custos,
    ampliar_perdas,
    duplicar_piores_dias,
    reduzir_ganhos,
    remover_melhores_dias,
)
from tradefolio.report_data import montar_dataframe_diario

CSV = "tests/fixtures/mini_fixture_orders.csv"


def _diario():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return montar_dataframe_diario(CSV, contratos_referencia=1)


def test_reduzir_ganhos_so_toca_dias_positivos():
    diario = _diario()
    ajustada = reduzir_ganhos(diario["liquido"], fracao=0.10)
    esperado = pd.Series(
        [199.0 * 0.9, -52.0, -301.0, 0.0, -1.0], index=diario.index, name="liquido",
    )
    pd.testing.assert_series_equal(ajustada, esperado)


def test_ampliar_perdas_so_toca_dias_negativos():
    diario = _diario()
    ajustada = ampliar_perdas(diario["liquido"], fracao=0.10)
    esperado = pd.Series(
        [199.0, -52.0 * 1.1, -301.0 * 1.1, 0.0, -1.0 * 1.1], index=diario.index, name="liquido",
    )
    pd.testing.assert_series_equal(ajustada, esperado)


def test_reduzir_ganhos_fracao_negativa_levanta_erro():
    diario = _diario()
    with pytest.raises(ValueError):
        reduzir_ganhos(diario["liquido"], fracao=-0.1)


def test_ampliar_perdas_fracao_negativa_levanta_erro():
    diario = _diario()
    with pytest.raises(ValueError):
        ampliar_perdas(diario["liquido"], fracao=-0.1)


def test_remover_melhores_dias_zera_sem_remover_a_data():
    diario = _diario()
    ajustada = remover_melhores_dias(diario["liquido"], n=1)
    esperado = pd.Series([0.0, -52.0, -301.0, 0.0, -1.0], index=diario.index, name="liquido")
    pd.testing.assert_series_equal(ajustada, esperado)
    assert len(ajustada) == len(diario)


def test_duplicar_piores_dias_dobra_no_lugar():
    diario = _diario()
    ajustada = duplicar_piores_dias(diario["liquido"], n=1)
    esperado = pd.Series([199.0, -52.0, -602.0, 0.0, -1.0], index=diario.index, name="liquido")
    pd.testing.assert_series_equal(ajustada, esperado)
    assert len(ajustada) == len(diario)


def test_aumentar_custos_recomputa_liquido():
    diario = _diario()
    ajustado = aumentar_custos(diario["bruto"], diario["custo"], fracao=0.5)
    esperado = pd.Series([198.5, -53.0, -301.5, 0.0, -1.5], index=diario.index)
    pd.testing.assert_series_equal(ajustado, esperado, check_names=False)


def test_aplicar_slippage_custo_extra_por_trade():
    diario = _diario()
    ajustado = aplicar_slippage(diario["liquido"], diario["n_trades"], valor_por_trade=5.0)
    esperado = pd.Series([194.0, -62.0, -306.0, 0.0, -6.0], index=diario.index)
    pd.testing.assert_series_equal(ajustado, esperado, check_names=False)


def test_transformacoes_sao_componiveis():
    # a mesma serie pode passar por mais de uma transformacao em cadeia,
    # sem nenhuma funcao "combinada" especial -- prova a composabilidade
    # pedida no PDF-fonte ("permitir independentemente").
    diario = _diario()
    combinado = ampliar_perdas(reduzir_ganhos(diario["liquido"], fracao=0.10), fracao=0.10)
    esperado = pd.Series(
        [199.0 * 0.9, -52.0 * 1.1, -301.0 * 1.1, 0.0, -1.0 * 1.1], index=diario.index, name="liquido",
    )
    pd.testing.assert_series_equal(combinado, esperado)
