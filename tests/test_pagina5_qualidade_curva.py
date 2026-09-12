"""
RED: report_data.calcular_pagina5 ainda não existe (lâmina ideal.pdf §9
"qualidade da curva"). Só compõe tradefolio.concentracao (já
implementado/testado nesta sessão), sobre a série TOTAL (diario['liquido'],
mesma decisão de escala de calcular_pagina4) e a série mensal
correspondente.

Valores conferidos por script contra dados_exemplo/orders_roboraiz.csv:
top1 dia=5,949%, top5=27,613%, top10=48,852%; melhor mês=13,007%, top3
meses=31,295%; lucro sem melhor dia=16.884,00, sem top5 dias=12.995,00,
sem melhor mês=15.617,00, sem top3 meses=12.334,00; antes dos últimos 60
dias=12.425,00; % dias abaixo de zero=1,236%; última data negativa
22/05/2023; pregões desde consolidação positiva=824; nenhum alerta
disparado (robô real e saudável, mesmo padrão já visto com Romanos).
"""
import warnings

import pandas as pd
import pytest

from tradefolio.alignment import preencher_calendario_b3
from tradefolio.daily import agregar_diario
from tradefolio.loaders import carregar_ordens
from tradefolio.report_data import calcular_pagina5

CSV = "dados_exemplo/orders_roboraiz.csv"


def _diario_total():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ordens = carregar_ordens(CSV)
    return preencher_calendario_b3(agregar_diario(ordens, contratos_referencia=1))


def test_pagina5_concentracao():
    p5 = calcular_pagina5(_diario_total())
    assert p5["top1_dia"] == pytest.approx(0.05949, abs=1e-4)
    assert p5["top5_dias"] == pytest.approx(0.27613, abs=1e-4)
    assert p5["top10_dias"] == pytest.approx(0.48852, abs=1e-4)
    assert p5["melhor_mes_share"] == pytest.approx(0.13007, abs=1e-4)
    assert p5["top3_meses_share"] == pytest.approx(0.31295, abs=1e-4)


def test_pagina5_lucro_removendo_eventos():
    p5 = calcular_pagina5(_diario_total())
    assert p5["lucro_sem_melhor_dia"] == pytest.approx(16884.00)
    assert p5["lucro_sem_top5_dias"] == pytest.approx(12995.00)
    assert p5["lucro_sem_melhor_mes"] == pytest.approx(15617.00)
    assert p5["lucro_sem_top3_meses"] == pytest.approx(12334.00)
    assert p5["lucro_antes_dos_ultimos_60_dias"] == pytest.approx(12425.00)


def test_pagina5_permanencia_abaixo_de_zero():
    p5 = calcular_pagina5(_diario_total())
    assert p5["pct_dias_abaixo_de_zero"] == pytest.approx(0.012360, abs=1e-5)
    assert p5["ultima_data_negativa"] == pd.Timestamp("2023-05-22")
    assert p5["pregoes_desde_consolidacao_positiva"] == 824


def test_pagina5_alertas_vazio_para_robo_saudavel():
    p5 = calcular_pagina5(_diario_total())
    assert p5["alertas"] == []
