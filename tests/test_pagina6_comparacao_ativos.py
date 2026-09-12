"""
RED: report_data.calcular_pagina6 ainda não existe (lâmina ideal.pdf §12
"comparação entre ativos internos" -- só faz sentido para robôs
multi-ativo; quem chama decide se chama, checando
nunique(ativo_raiz) > 1 antes -- esta função em si não guarda essa
lógica).

Reusa tradefolio.daily.pivotar_liquido_por_ativo (já testado) e aplica
drawdowns/correlação já existentes por cima -- nenhuma fórmula nova.
"Compensação nos piores dias" responde diretamente à pergunta do próprio
PDF ("Nos piores dias do WIN, quanto o WDO ganhou?"): para os N piores
dias de CADA ativo, o resultado do(s) outro(s) ativo(s) nessas mesmas
datas.

Valores conferidos por script contra dados_exemplo/orders_roboraiz.csv:
lucro WDO=2.303,50/WIN=15.648,50; MDD WDO=-2.524,00/WIN=-3.093,00;
correlação WDO×WIN=0,075056; pior dia de WDO é 13/02/2023 (-631,00), WIN
não operou nesse dia (0,00); pior dia de WIN é 25/08/2026 (-586,50), WDO
fez +119,00 nesse dia.
"""
import warnings

import pandas as pd
import pytest

from tradefolio.loaders import carregar_ordens
from tradefolio.report_data import calcular_pagina6

CSV = "dados_exemplo/orders_roboraiz.csv"


def _ordens():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return carregar_ordens(CSV)


def test_pagina6_lucro_e_mdd_por_ativo():
    p6 = calcular_pagina6(_ordens())
    assert set(p6["ativos"]) == {"WIN", "WDO"}
    assert p6["lucro_por_ativo"]["WIN"] == pytest.approx(15648.50)
    assert p6["lucro_por_ativo"]["WDO"] == pytest.approx(2303.50)
    assert p6["mdd_por_ativo"]["WDO"] == pytest.approx(-2524.00)
    assert p6["mdd_por_ativo"]["WIN"] == pytest.approx(-3093.00)


def test_pagina6_correlacao():
    p6 = calcular_pagina6(_ordens())
    corr = p6["correlacao_ativos"]
    assert corr.loc["WDO", "WIN"] == pytest.approx(0.075056, abs=1e-5)
    assert corr.loc["WDO", "WDO"] == pytest.approx(1.0)


def test_pagina6_compensacao_piores_dias():
    p6 = calcular_pagina6(_ordens(), n_piores_dias=5)
    piores_wdo = p6["compensacao_piores_dias"]["WDO"]
    assert len(piores_wdo) == 5
    linha_13fev = piores_wdo[piores_wdo["data"] == pd.Timestamp("2023-02-13")].iloc[0]
    assert linha_13fev["WDO"] == pytest.approx(-631.00)
    assert linha_13fev["WIN"] == pytest.approx(0.0)

    piores_win = p6["compensacao_piores_dias"]["WIN"]
    linha_25ago = piores_win[piores_win["data"] == pd.Timestamp("2026-08-25")].iloc[0]
    assert linha_25ago["WIN"] == pytest.approx(-586.50)
    assert linha_25ago["WDO"] == pytest.approx(119.00)
