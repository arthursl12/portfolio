"""
RED: tradefolio.report_data ainda não existe.

Teste de integração de ponta a ponta (AGENTS.md §7.2: CSV import ->
validação -> agregação diária -> custos -> equity líquida -> relatório de
performance), usando o mini fixture inteiro. Praticamente todo valor
esperado abaixo já veio hand-verificado em ciclos RED/GREEN anteriores
(tests/fixtures/mini_fixture_expected.md ou os testes de
drawdowns/metrics desta sessão) -- o que este teste verifica de novo é a
FIAÇÃO: que report_data alimenta a série certa na função certa e monta o
dict com as chaves que report.py espera.

retorno_bruto_pct/retorno_liquido_pct não estão no fixture -- calculados
e conferidos por script antes deste teste (ver histórico da sessão).
"""
from pathlib import Path

import pandas as pd
import pytest

from tradefolio.loaders import carregar_ordens
from tradefolio.report_data import calcular_pagina1, calcular_pagina2, calcular_pagina3, montar_dataframe_diario

FIXTURE = Path(__file__).parent / "fixtures" / "mini_fixture_orders.csv"


@pytest.fixture
def diario():
    return montar_dataframe_diario(FIXTURE)


@pytest.fixture
def ordens():
    return carregar_ordens(FIXTURE)


def test_montar_dataframe_diario_inclui_pregao_sem_ordem(diario):
    # 07/01 tem pregao na B3 mas nenhuma ordem -- deve entrar com 0 e operou=False
    assert len(diario) == 5
    assert diario.loc["2025-01-07", "operou"] == False


def test_pagina1_metricas_principais(diario):
    metricas, equity, drawdown = calcular_pagina1(diario)

    assert metricas["pregoes"] == 5
    assert metricas["lucro_liquido_2c"] == pytest.approx(-155.00)
    assert metricas["lucro_liquido_por_contrato"] == pytest.approx(-77.50)
    assert metricas["media_diaria"] == pytest.approx(-15.50)
    assert metricas["mediana_diaria"] == pytest.approx(-0.50)
    assert metricas["pct_dias_positivos"] == pytest.approx(0.2)
    assert metricas["pct_dias_negativos"] == pytest.approx(0.6)
    assert metricas["pct_dias_neutros"] == pytest.approx(0.2)
    assert metricas["gain_medio"] == pytest.approx(99.50)
    assert metricas["loss_medio"] == pytest.approx(-59.00)
    assert metricas["payoff"] == pytest.approx(1.686441, rel=1e-6)
    assert metricas["expectancia_diaria"] == pytest.approx(-15.50)
    assert metricas["profit_factor_diario"] == pytest.approx(0.562147, rel=1e-6)
    assert metricas["pior_dia"] == pytest.approx(-150.50)
    assert metricas["melhor_dia"] == pytest.approx(99.50)
    assert metricas["max_drawdown"] == pytest.approx(-177.00)
    assert metricas["time_under_water_max_pregoes"] == 4
    assert metricas["ulcer_index_rs"] == pytest.approx(137.338633, abs=1e-6)


def test_pagina1_percentuais_e_ratios(diario):
    metricas, _, _ = calcular_pagina1(diario)

    assert metricas["retorno_bruto_pct"] == pytest.approx(-7.5)
    assert metricas["retorno_liquido_pct"] == pytest.approx(-7.75)
    assert metricas["max_drawdown_pct"] == pytest.approx(-16.098226, abs=1e-6)
    assert metricas["ulcer_index_pct"] == pytest.approx(12.491008, abs=1e-6)
    assert metricas["sharpe"] == pytest.approx(-2.7498816613551633, rel=1e-9)
    assert metricas["sortino"] == pytest.approx(-3.0657026938917222, rel=1e-9)
    assert metricas["calmar"] == pytest.approx(-26.65430790960452, rel=1e-9)
    assert metricas["recovery_factor"] == pytest.approx(-0.4378531073446328, rel=1e-9)


def test_pagina1_periodo(diario):
    metricas, _, _ = calcular_pagina1(diario)
    import datetime
    assert metricas["periodo"] == (datetime.date(2025, 1, 2), datetime.date(2025, 1, 8))


def test_pagina2_trades_e_ratios(diario, ordens):
    p2 = calcular_pagina2(diario, ordens)
    assert p2["n_trades"] == 5
    assert p2["win_rate_trades"] == pytest.approx(0.4)
    assert p2["profit_factor_trades"] == pytest.approx(0.657837, rel=1e-6)
    assert p2["lucro_medio_trade"] == pytest.approx(149.00)
    assert p2["prejuizo_medio_trade"] == pytest.approx(-151.00)
    # AGENTS.md épico 4.5 "expectativa por operação": mean([199,99,-151,-301,-1])
    assert p2["expectancia_por_trade"] == pytest.approx(-31.00)


def test_pagina2_sequencias_trades_usam_datas_proprias_do_trade(diario, ordens):
    p2 = calcular_pagina2(diario, ordens)
    assert p2["maior_sequencia_positiva_trades"] == {
        "comprimento": 2,
        "valor_total": 298.00,
        "inicio": pd.Timestamp("2025-01-02 09:00:00"),
        "fim": pd.Timestamp("2025-01-03 09:05:00"),
    }
    assert p2["maior_sequencia_negativa_trades"] == {
        "comprimento": 3,
        "valor_total": -453.00,
        "inicio": pd.Timestamp("2025-01-03 10:00:00"),
        "fim": pd.Timestamp("2025-01-08 09:05:00"),
    }


def test_pagina2_sequencias_dias(diario, ordens):
    p2 = calcular_pagina2(diario, ordens)
    assert p2["maior_sequencia_positiva_dias"]["comprimento"] == 1
    assert p2["maior_sequencia_negativa_dias"]["comprimento"] == 2


def test_pagina2_episodios_drawdown_e_tuw(diario, ordens):
    p2 = calcular_pagina2(diario, ordens)
    assert len(p2["episodios_drawdown"]) == 1
    assert p2["episodios_drawdown"].iloc[0]["profundidade_rs"] == pytest.approx(-177.00)
    assert len(p2["piores_tuw"]) == 1
    assert p2["piores_tuw"].iloc[0]["pregoes_submerso"] == 4


def test_pagina3_distribuicao_e_cauda(diario):
    p3 = calcular_pagina3(diario)
    assert p3["media"] == pytest.approx(-15.50)
    assert p3["skewness"] == pytest.approx(-0.5429708576351356, rel=1e-9)
    assert p3["kurtosis"] == pytest.approx(1.8899298886667832, rel=1e-9)
    assert p3["percentis"][5] == pytest.approx(-125.60, abs=1e-6)
    assert p3["percentis"][95] == pytest.approx(79.60, abs=1e-6)
    assert p3["var_95"] == pytest.approx(-125.60, abs=1e-6)
    assert p3["var_99"] == pytest.approx(-145.52, abs=1e-6)
    assert p3["es_95"] == pytest.approx(-150.50, abs=1e-6)
    assert p3["es_99"] == pytest.approx(-150.50, abs=1e-6)
    assert p3["n_dias_negativos"] == 3
    assert p3["piores_5_media"] == pytest.approx(-15.50)
    assert p3["melhores_5_media"] == pytest.approx(-15.50)
