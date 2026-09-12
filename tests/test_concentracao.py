"""
RED: tradefolio.concentracao ainda não existe (AGENTS.md épico 5, tarefas
5.1 "concentração positiva" e 5.2 "resultado removendo eventos").

participacao_top_n é genérica sobre qualquer série (AGENTS.md §8.1) --
serve tanto para "participação dos 5 melhores dias" (serie diária) quanto
"participação dos 3 melhores meses" (serie mensal), mesma fórmula:
soma dos N maiores valores / soma total da série. Intencionalmente NÃO
limitada a [0, 1] -- um resultado acima de 100% (top N > lucro total) é
um sinal real de concentração patológica (a própria "lâmina ideal.pdf",
seção 9, tem isso como exemplo de alerta: "Os três melhores meses
representam 118% do lucro"), não um erro a esconder.

resultado_sem_top_n (genérica, mesma lógica) e
resultado_antes_dos_ultimos_n_dias (posicional -- só faz sentido para a
série diária ordenada cronologicamente, não para meses) implementam
"resultado removendo eventos".

Valores conferidos por script contra tests/fixtures/romanos_orders.csv
antes deste teste (312 pregões, 16 meses, lucro total R$10.893,75).
"""
import math

import pandas as pd
import pytest

from tradefolio.concentracao import (
    detectar_alertas_curva,
    participacao_top_n,
    pct_dias_abaixo_de_zero,
    pregoes_desde_consolidacao_positiva,
    primeira_data_positiva,
    resultado_antes_dos_ultimos_n_dias,
    resultado_sem_top_n,
    ultima_data_negativa,
)
from tradefolio.drawdowns import curva_equity

SERIE_MINI = pd.Series(
    [99.50, -26.00, -150.50, 0.00, -0.50],
    index=pd.DatetimeIndex(
        ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08"]
    ),
)


def _serie_e_mensal_romanos():
    import warnings

    from tradefolio.alignment import preencher_calendario_b3
    from tradefolio.daily import agregar_diario
    from tradefolio.loaders import carregar_ordens
    from tradefolio.monthly import agregar_mensal

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ordens = carregar_ordens("tests/fixtures/romanos_orders.csv")
    diario = preencher_calendario_b3(agregar_diario(ordens))
    serie = diario["liquido_por_contrato"]
    mensal = agregar_mensal(diario)["liquido_por_contrato"]
    return serie, mensal


def test_participacao_top_n_dias_romanos():
    serie, _ = _serie_e_mensal_romanos()
    assert participacao_top_n(serie, 1) == pytest.approx(0.099828, abs=1e-6)
    assert participacao_top_n(serie, 5) == pytest.approx(0.419002, abs=1e-6)
    assert participacao_top_n(serie, 10) == pytest.approx(0.731291, abs=1e-6)


def test_participacao_top_n_meses_romanos():
    _, mensal = _serie_e_mensal_romanos()
    assert participacao_top_n(mensal, 1) == pytest.approx(0.150453, abs=1e-6)
    assert participacao_top_n(mensal, 3) == pytest.approx(0.401010, abs=1e-6)


def test_participacao_pode_passar_de_100_por_cento():
    # concentracao patologica: top N > lucro total inteiro -- sinal real
    # (ver "lamina ideal.pdf" secao 9), nao deve ser limitado a [0,1].
    serie = pd.Series([100.0, 100.0, -150.0])  # total=50, top2=200 -> 400%
    assert participacao_top_n(serie, 2) == pytest.approx(4.0)


def test_participacao_com_lucro_total_zero_e_nan():
    serie = pd.Series([100.0, -100.0])
    assert math.isnan(participacao_top_n(serie, 1))


def test_resultado_sem_top_n_dias_romanos():
    serie, _ = _serie_e_mensal_romanos()
    assert resultado_sem_top_n(serie, 1) == pytest.approx(9806.25)
    assert resultado_sem_top_n(serie, 5) == pytest.approx(6329.25)


def test_resultado_sem_top_n_meses_romanos():
    _, mensal = _serie_e_mensal_romanos()
    assert resultado_sem_top_n(mensal, 1) == pytest.approx(9254.75)
    assert resultado_sem_top_n(mensal, 3) == pytest.approx(6525.25)


def test_resultado_antes_dos_ultimos_60_dias_romanos():
    serie, _ = _serie_e_mensal_romanos()
    assert resultado_antes_dos_ultimos_n_dias(serie, 60) == pytest.approx(6594.75)


def test_resultado_antes_dos_ultimos_n_dias_com_serie_curta_e_nan():
    serie = pd.Series([1.0, 2.0, 3.0])
    assert math.isnan(resultado_antes_dos_ultimos_n_dias(serie, 60))


# ---------------------------------------------------------------------------
# épico 5.4: permanência abaixo do zero
# equity mini fixture = [99.50, 73.50, -77.00, -77.00, -77.50] (02,03,06,07,08/01)
# fica negativa a partir de 06/01 e NÃO recupera até o fim da amostra.
# ---------------------------------------------------------------------------


def test_pct_dias_abaixo_de_zero_mini_fixture():
    equity = curva_equity(SERIE_MINI)
    assert pct_dias_abaixo_de_zero(equity) == pytest.approx(0.6)  # 3 de 5 dias


def test_primeira_data_positiva_mini_fixture():
    equity = curva_equity(SERIE_MINI)
    assert primeira_data_positiva(equity) == pd.Timestamp("2025-01-02")


def test_ultima_data_negativa_mini_fixture():
    equity = curva_equity(SERIE_MINI)
    assert ultima_data_negativa(equity) == pd.Timestamp("2025-01-08")


def test_pregoes_desde_consolidacao_positiva_ainda_negativa_e_zero():
    # a amostra termina negativa (nunca recuperou) -- "dias desde a
    # consolidação positiva" é 0, não faz sentido contar uma consolidação
    # que ainda não aconteceu.
    equity = curva_equity(SERIE_MINI)
    assert pregoes_desde_consolidacao_positiva(equity) == 0


def test_primeira_data_positiva_e_ultima_negativa_sao_none_quando_nao_ocorrem():
    sempre_positiva = curva_equity(pd.Series([1.0, 2.0, 3.0]))
    assert ultima_data_negativa(sempre_positiva) is None

    sempre_negativa = curva_equity(pd.Series([-1.0, -2.0, -3.0]))
    assert primeira_data_positiva(sempre_negativa) is None


def test_permanencia_abaixo_de_zero_romanos():
    serie, _ = _serie_e_mensal_romanos()
    equity = curva_equity(serie)
    assert pct_dias_abaixo_de_zero(equity) == pytest.approx(4 / 312)
    assert primeira_data_positiva(equity) == pd.Timestamp("2025-06-11")
    assert ultima_data_negativa(equity) == pd.Timestamp("2025-06-27")
    assert pregoes_desde_consolidacao_positiva(equity) == 300


# ---------------------------------------------------------------------------
# épico 5.3: detectar curva salva recentemente (regras determinísticas)
# ---------------------------------------------------------------------------


def test_detectar_alertas_curva_romanos_e_saudavel_sem_alertas():
    # robô real, sem sinais de concentração patológica -- confirma que as
    # regras não disparam falso-positivo sobre uma curva normal.
    serie, mensal = _serie_e_mensal_romanos()
    assert detectar_alertas_curva(serie, mensal) == []


def test_alerta_negative_before_last_60_days():
    # 100 dias: os primeiros 40 somam -500 (negativo antes dos ultimos 60)
    serie = pd.Series([-12.5] * 40 + [1.0] * 60)
    alertas = detectar_alertas_curva(serie, pd.Series([100.0]))
    codigos = [a["warning_code"] for a in alertas]
    assert "NEGATIVE_BEFORE_LAST_60_DAYS" in codigos
    alerta = next(a for a in alertas if a["warning_code"] == "NEGATIVE_BEFORE_LAST_60_DAYS")
    assert alerta["severity"] == "high"
    assert alerta["observed_value"] == pytest.approx(-500.0)


def test_alerta_profit_saved_by_best_month():
    mensal = pd.Series([1000.0, 100.0, 100.0])  # melhor mes = 83.3% do lucro
    serie = pd.Series([1.0] * 100)  # nao deve disparar a regra dos 60 dias
    alertas = detectar_alertas_curva(serie, mensal)
    codigos = [a["warning_code"] for a in alertas]
    assert "PROFIT_SAVED_BY_BEST_MONTH" in codigos
    alerta = next(a for a in alertas if a["warning_code"] == "PROFIT_SAVED_BY_BEST_MONTH")
    assert alerta["severity"] == "high"
    assert alerta["observed_value"] == pytest.approx(1000 / 1200)


def test_alerta_top3_exceeds_total_profit():
    mensal = pd.Series([1000.0, 1000.0, 1000.0, -2500.0])  # top3=3000, total=500 -> 600%
    serie = pd.Series([1.0] * 100)
    alertas = detectar_alertas_curva(serie, mensal)
    codigos = [a["warning_code"] for a in alertas]
    assert "TOP3_EXCEEDS_TOTAL_PROFIT" in codigos
    alerta = next(a for a in alertas if a["warning_code"] == "TOP3_EXCEEDS_TOTAL_PROFIT")
    assert alerta["severity"] == "critical"
    assert alerta["observed_value"] == pytest.approx(6.0)
