"""
RED: tradefolio.metrics ainda não existe.

payoff, profit_factor e expectancia sao formulas genericas (AGENTS.md
§8.1: mesma formula serve para serie diaria ou de trades, com o cuidado de
nao misturar as duas bases). Caso principal vem da serie diaria por
contrato de tests/fixtures/mini_fixture_expected.md (ja alinhada no
calendario B3: 5 pregoes, 07/01 = 0,0 por nao ter ordem nesse dia).

Casos de borda (AGENTS.md §8.3/§8.5: "definir comportamento para serie sem
perdas ou sem ganhos antes de implementar") sao definidos e testados aqui,
nao deixados implicitos:
- sem perdas -> payoff e profit_factor = +inf (nada limita o ganho)
- sem ganhos -> payoff e profit_factor = 0.0 (nao ha o que classificar como
  vencedor)
- serie vazia de sinal (todos os valores zero) -> nan (razao indefinida,
  nao existe amostra de ganho nem de perda)
"""
import math

import pandas as pd
import pytest

from tradefolio.metrics import (
    expectancia,
    ganho_medio,
    payoff,
    perda_media,
    profit_factor,
    taxa_negativos,
    taxa_neutros,
    taxa_positivos,
)

SERIE_DIARIA_MINI_FIXTURE = pd.Series([99.50, -26.00, -150.50, 0.00, -0.50])
# tests/fixtures/mini_fixture_expected.md, "Métricas esperadas — nível trade":
# resultado_liquido dos 5 trades reconstruídos.
SERIE_TRADES_MINI_FIXTURE = pd.Series([199.0, 99.0, -151.0, -301.0, -1.0])


def test_payoff_caso_principal():
    assert payoff(SERIE_DIARIA_MINI_FIXTURE) == pytest.approx(1.686441, rel=1e-6)


def test_profit_factor_caso_principal():
    assert profit_factor(SERIE_DIARIA_MINI_FIXTURE) == pytest.approx(0.562147, rel=1e-6)


def test_expectancia_caso_principal():
    assert expectancia(SERIE_DIARIA_MINI_FIXTURE) == pytest.approx(-15.50, rel=1e-6)


def test_payoff_sem_perdas_e_infinito():
    assert payoff(pd.Series([10.0, 20.0, 30.0])) == math.inf


def test_profit_factor_sem_perdas_e_infinito():
    assert profit_factor(pd.Series([10.0, 20.0, 30.0])) == math.inf


def test_payoff_sem_ganhos_e_zero():
    assert payoff(pd.Series([-10.0, -20.0])) == 0.0


def test_profit_factor_sem_ganhos_e_zero():
    assert profit_factor(pd.Series([-10.0, -20.0])) == 0.0


def test_payoff_serie_toda_neutra_e_nan():
    assert math.isnan(payoff(pd.Series([0.0, 0.0, 0.0])))


def test_profit_factor_serie_toda_neutra_e_nan():
    assert math.isnan(profit_factor(pd.Series([0.0, 0.0, 0.0])))


def test_taxas_dia_a_dia_caso_principal():
    # mini fixture: % dias positivos 20%, negativos 60%, neutros 20% (1/5, 3/5, 1/5)
    assert taxa_positivos(SERIE_DIARIA_MINI_FIXTURE) == pytest.approx(0.2)
    assert taxa_negativos(SERIE_DIARIA_MINI_FIXTURE) == pytest.approx(0.6)
    assert taxa_neutros(SERIE_DIARIA_MINI_FIXTURE) == pytest.approx(0.2)


def test_taxa_positivos_e_a_mesma_formula_para_win_rate_de_trades():
    # mini fixture: win rate (por trade) = 40% (2/5) -- mesma funcao, serie de trades
    assert taxa_positivos(SERIE_TRADES_MINI_FIXTURE) == pytest.approx(0.4)


def test_taxas_com_serie_vazia_e_nan():
    vazia = pd.Series([], dtype=float)
    assert math.isnan(taxa_positivos(vazia))
    assert math.isnan(taxa_negativos(vazia))
    assert math.isnan(taxa_neutros(vazia))


def test_ganho_medio_e_perda_media_nivel_dia():
    # mini fixture: gain medio 99,50 / loss medio -59,00
    assert ganho_medio(SERIE_DIARIA_MINI_FIXTURE) == pytest.approx(99.50)
    assert perda_media(SERIE_DIARIA_MINI_FIXTURE) == pytest.approx(-59.00)


def test_ganho_medio_e_perda_media_nivel_trade():
    # mini fixture pagina 2: lucro medio/trade vencedor 149,00, prejuizo medio/trade perdedor -151,00
    assert ganho_medio(SERIE_TRADES_MINI_FIXTURE) == pytest.approx(149.00)
    assert perda_media(SERIE_TRADES_MINI_FIXTURE) == pytest.approx(-151.00)


def test_ganho_medio_sem_ganhos_e_nan():
    assert math.isnan(ganho_medio(pd.Series([-10.0, -20.0])))


def test_perda_media_sem_perdas_e_nan():
    assert math.isnan(perda_media(pd.Series([10.0, 20.0])))
