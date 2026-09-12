"""
RED: tradefolio.limiar ainda não existe.

Escopo desta primeira fatia (AGENTS.md épico 6, tarefas 6.3/6.4 -- as duas
únicas com fórmula concreta e sem ambiguidade no PDF-fonte): o prêmio por
histórico curto e o arredondamento. As tarefas 6.1/6.2/6.5 (decomposição
completa do limiar e seus perfis) ficam de fora deliberadamente -- exigem
decidir a fonte de cada termo (P95 ou P99? de qual série? deteriorado ou
não?) antes de codificar (AGENTS.md §8/§24: nunca adivinhar uma fórmula
financeira a partir de um esqueleto).

history_uncertainty_multiplier usa exatamente os degraus do PDF-fonte
(seção "Épico 6, Tarefa 6.3"), documentado como política configurável,
não verdade estatística (o próprio PDF exige isso).
"""
import math
import warnings

import pandas as pd
import pytest

from tradefolio.limiar import arredondar_limiar, decompor_limiar, history_uncertainty_multiplier


def test_history_uncertainty_multiplier_degraus_do_pdf():
    assert history_uncertainty_multiplier(3) == math.inf
    assert history_uncertainty_multiplier(5) == math.inf
    assert history_uncertainty_multiplier(6) == pytest.approx(2.0)
    assert history_uncertainty_multiplier(8) == pytest.approx(2.0)
    assert history_uncertainty_multiplier(9) == pytest.approx(1.5)
    assert history_uncertainty_multiplier(11) == pytest.approx(1.5)
    assert history_uncertainty_multiplier(12) == pytest.approx(1.2)
    assert history_uncertainty_multiplier(23) == pytest.approx(1.2)
    assert history_uncertainty_multiplier(24) == pytest.approx(1.1)
    assert history_uncertainty_multiplier(35) == pytest.approx(1.1)
    assert history_uncertainty_multiplier(36) == pytest.approx(1.0)
    assert history_uncertainty_multiplier(100) == pytest.approx(1.0)


def test_arredondar_limiar_multiplo_exato_fica_igual():
    assert arredondar_limiar(15000, increment=500) == 15000


def test_arredondar_limiar_arredonda_para_cima():
    assert arredondar_limiar(14621, increment=500) == 15000
    assert arredondar_limiar(14001, increment=1000) == 15000


def test_arredondar_limiar_increment_percentual_da_margem():
    # incremento como % da margem (ex. 10% de R$5.000 = R$500)
    assert arredondar_limiar(9621, increment=0.10, margem=5000) == 10000


def _serie_liquido_por_contrato_roboraiz() -> pd.Series:
    from tradefolio.alignment import preencher_calendario_b3
    from tradefolio.daily import agregar_diario
    from tradefolio.loaders import carregar_ordens

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ordens = carregar_ordens("dados_exemplo/orders_roboraiz.csv")
    diario = preencher_calendario_b3(agregar_diario(ordens))
    return diario["liquido_por_contrato"]


def test_decompor_limiar_p95_robo_raiz_historico_longo_sem_premio():
    from tradefolio.drawdowns import curva_equity, drawdown

    serie = _serie_liquido_por_contrato_roboraiz()
    dd = drawdown(curva_equity(serie))
    meses = (serie.index.max() - serie.index.min()).days / 30.44  # ~42.8

    resultado = decompor_limiar(
        minimum_margin=5000,
        drawdown_serie=dd,
        meses_historico=meses,
        percentil_cauda=95,
        fracao_reserva_operacional=0.10,
    )

    assert resultado["minimum_margin"] == 5000
    assert resultado["percentil_cauda"] == 95
    assert resultado["uncertainty_multiplier"] == pytest.approx(1.0)
    assert resultado["tail_drawdown_reserve"] == pytest.approx(1247.50, abs=1e-2)
    assert resultado["uncertainty_premium"] == pytest.approx(0.0, abs=1e-9)
    assert resultado["operational_reserve"] == pytest.approx(500.0)
    assert resultado["limiar_bruto"] == pytest.approx(6747.50, abs=1e-2)


def test_decompor_limiar_p99_e_p95_sao_toggle_nao_valor_fixo():
    from tradefolio.drawdowns import curva_equity, drawdown

    serie = _serie_liquido_por_contrato_roboraiz()
    dd = drawdown(curva_equity(serie))
    meses = (serie.index.max() - serie.index.min()).days / 30.44

    p99 = decompor_limiar(
        minimum_margin=5000,
        drawdown_serie=dd,
        meses_historico=meses,
        percentil_cauda=99,
        fracao_reserva_operacional=0.10,
    )

    assert p99["percentil_cauda"] == 99
    assert p99["tail_drawdown_reserve"] == pytest.approx(1550.975, abs=1e-2)
    assert p99["limiar_bruto"] == pytest.approx(7050.975, abs=1e-2)


def test_decompor_limiar_historico_curto_gera_premio_incerteza():
    dd = pd.Series([-1000.0] * 10)

    resultado = decompor_limiar(
        minimum_margin=5000,
        drawdown_serie=dd,
        meses_historico=8,  # < 9 meses -> multiplicador 2.0
        percentil_cauda=95,
        fracao_reserva_operacional=0.0,
    )

    assert resultado["uncertainty_multiplier"] == pytest.approx(2.0)
    assert resultado["tail_drawdown_reserve"] == pytest.approx(2000.0)
    assert resultado["uncertainty_premium"] == pytest.approx(1000.0)
    assert resultado["operational_reserve"] == pytest.approx(0.0)
    assert resultado["limiar_bruto"] == pytest.approx(7000.0)


def test_decompor_limiar_com_increment_inclui_limiar_recomendado():
    dd = pd.Series([-1000.0] * 10)

    resultado = decompor_limiar(
        minimum_margin=5000,
        drawdown_serie=dd,
        meses_historico=8,
        percentil_cauda=95,
        fracao_reserva_operacional=0.0,
        increment=500,
    )

    assert resultado["limiar_bruto"] == pytest.approx(7000.0)
    assert resultado["limiar_recomendado"] == pytest.approx(7000.0)


def test_decompor_limiar_percentil_invalido_levanta_erro():
    dd = pd.Series([-1000.0] * 10)
    with pytest.raises(ValueError):
        decompor_limiar(
            minimum_margin=5000,
            drawdown_serie=dd,
            meses_historico=42,
            percentil_cauda=90,
        )
