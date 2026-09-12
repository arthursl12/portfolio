"""
RED: report_data.calcular_pagina4 ainda não existe (lâmina ideal.pdf §4/5/7
-- limiar, RLT, risco normalizado pelo limiar).

Escala TOTAL (diario['liquido'], não liquido_por_contrato) -- decisão de
escala confirmada nesta sessão para minimum_margin/limiar. `limiar_p95` e
`limiar_p99` (dicts de decompor_limiar) são calculados sempre os DOIS, para
mostrar lado a lado (resolução do usuário: "use both... toggle button
somewhere"); `percentil_cauda` escolhe qual alimenta o resto da página
(`limiar_ativo`, RLT, normalizações de risco).

Valores conferidos por script contra dados_exemplo/orders_roboraiz.csv
antes deste teste (minimum_margin=10.000, fracao_reserva_operacional=10%,
increment=500, percentil_cauda=95):
limiar_p95.limiar_recomendado=13.500, limiar_p99.limiar_recomendado=14.500,
rlt_acumulado=1,329778, rlt_anualizado=0,372756,
rlt_mensal médio=0,030222 / mediano=0,036407,
rlt_movel_3=0,321556 / _6=0,301000 / _12=0,556519,
mdd_total=-3.352,00 -> mdd_sobre_limiar=-0,248296,
pior_dia_total=-797,50 -> /L=-0,059074,
es95_total=-530,222 -> /L=-0,039276,
ulcer_total=1.096,591 -> /L=0,081229,
pior_mes_total=-1.449,00 -> /L=-0,107333.
"""
import warnings

import pytest

from tradefolio.alignment import preencher_calendario_b3
from tradefolio.daily import agregar_diario
from tradefolio.loaders import carregar_ordens
from tradefolio.report_data import calcular_pagina4

CSV = "dados_exemplo/orders_roboraiz.csv"


def _diario_total():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ordens = carregar_ordens(CSV)
    return preencher_calendario_b3(agregar_diario(ordens, contratos_referencia=1))


def test_pagina4_limiar_ambos_percentis_e_ativo():
    p4 = calcular_pagina4(
        _diario_total(), minimum_margin=10000, percentil_cauda=95,
        fracao_reserva_operacional=0.10, increment=500,
    )
    assert p4["limiar_p95"]["limiar_recomendado"] == pytest.approx(13500)
    assert p4["limiar_p99"]["limiar_recomendado"] == pytest.approx(14500)
    assert p4["percentil_cauda_ativo"] == 95
    assert p4["limiar_ativo"] == pytest.approx(13500)


def test_pagina4_rlt():
    p4 = calcular_pagina4(
        _diario_total(), minimum_margin=10000, percentil_cauda=95,
        fracao_reserva_operacional=0.10, increment=500,
    )
    assert p4["rlt_acumulado"] == pytest.approx(1.329778, rel=1e-5)
    assert p4["rlt_anualizado"] == pytest.approx(0.372756, rel=1e-5)
    assert p4["rlt_mensal_medio"] == pytest.approx(0.030222, rel=1e-4)
    assert p4["rlt_mensal_mediano"] == pytest.approx(0.036407, rel=1e-4)
    assert p4["rlt_movel_3"] == pytest.approx(0.321556, rel=1e-5)
    assert p4["rlt_movel_6"] == pytest.approx(0.301000, rel=1e-5)
    assert p4["rlt_movel_12"] == pytest.approx(0.556519, rel=1e-5)


def test_pagina4_risco_normalizado_pelo_limiar():
    p4 = calcular_pagina4(
        _diario_total(), minimum_margin=10000, percentil_cauda=95,
        fracao_reserva_operacional=0.10, increment=500,
    )
    assert p4["mdd_total"] == pytest.approx(-3352.00)
    assert p4["mdd_sobre_limiar"] == pytest.approx(-0.248296, rel=1e-5)
    assert p4["pior_dia_total"] == pytest.approx(-797.50)
    assert p4["pior_dia_sobre_limiar"] == pytest.approx(-0.059074, rel=1e-5)
    assert p4["es95_total"] == pytest.approx(-530.222, rel=1e-5)
    assert p4["es95_sobre_limiar"] == pytest.approx(-0.039276, rel=1e-4)
    assert p4["ulcer_total"] == pytest.approx(1096.591, rel=1e-5)
    assert p4["ulcer_sobre_limiar"] == pytest.approx(0.081229, rel=1e-4)
    assert p4["pior_mes_total"] == pytest.approx(-1449.00)
    assert p4["pior_mes_sobre_limiar"] == pytest.approx(-0.107333, rel=1e-4)


def test_pagina4_percentil_99_muda_limiar_ativo():
    p4 = calcular_pagina4(
        _diario_total(), minimum_margin=10000, percentil_cauda=99,
        fracao_reserva_operacional=0.10, increment=500,
    )
    assert p4["percentil_cauda_ativo"] == 99
    assert p4["limiar_ativo"] == pytest.approx(14500)
