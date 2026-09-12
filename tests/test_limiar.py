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

import pytest

from tradefolio.limiar import arredondar_limiar, history_uncertainty_multiplier


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
