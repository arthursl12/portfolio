"""
RED: tradefolio.monthly.agregar_mensal ainda não existe.

Convenção testada (AGENTS.md épico 3.4 "consolidar resultados mensais"):
consolida a série diária já alinhada ao calendário B3 (preencher_calendario_b3)
em uma linha por mês-calendário, com soma de bruto/custo/liquido, contagem de
dias operados e de pregões, `trades` (soma de n_trades -- mesmo proxy
aproximado de tradefolio.daily, não o count reconstruído de
tradefolio.trades), melhor/pior dia (base liquido_por_contrato, igual a
report_data.calcular_pagina1) e `mes_completo`.

Datas verificadas contra pandas_market_calendars (calendário 'B3'):
- Janeiro/2025: pregões de 02/01 a 31/01 (13 pregões a partir de 15/01,
  quando a série testada começa nessa data -- mês parcial).
- Fevereiro/2025: pregões de 03/02 a 28/02 (20 pregões, todos presentes na
  série testada, que vai até 28/02 -- mês completo).
"""
import warnings

import pandas as pd
import pytest

from tradefolio.alignment import preencher_calendario_b3
from tradefolio.monthly import agregar_mensal


def _diario_jan_parcial_fev_completo() -> pd.DataFrame:
    # 15/01, 16/01 e 31/01 têm ordem; 10/02 tem ordem; 28/02 entra explicito
    # (zerado) só para que o máximo da série seja o último pregão real de
    # fevereiro -- todo o resto dos pregões B3 entre 15/01 e 28/02 entra
    # zerado via preencher_calendario_b3.
    bruto = pd.DataFrame(
        {
            "bruto": [100.0, -30.0, 50.0, 200.0, 0.0],
            "custo": [1.0, 1.0, 1.0, 1.0, 0.0],
            "n_trades": [1, 2, 1, 1, 0],
        },
        index=pd.DatetimeIndex(
            ["2025-01-15", "2025-01-16", "2025-01-31", "2025-02-10", "2025-02-28"],
            name="data",
        ),
    )
    bruto["liquido"] = bruto["bruto"] - bruto["custo"]
    bruto["liquido_por_contrato"] = bruto["liquido"] / 2
    return preencher_calendario_b3(bruto)


def test_agregar_mensal_soma_bruto_custo_liquido_e_conta_dias():
    mensal = agregar_mensal(_diario_jan_parcial_fev_completo())

    jan = mensal.loc["2025-01"]
    assert jan["bruto"] == 120.0
    assert jan["custo"] == 3.0
    assert jan["liquido"] == 117.0
    assert jan["dias_operados"] == 3
    assert jan["pregoes"] == 13
    assert jan["trades"] == 4

    fev = mensal.loc["2025-02"]
    assert fev["bruto"] == 200.0
    assert fev["dias_operados"] == 1
    assert fev["pregoes"] == 20
    assert fev["trades"] == 1


def test_agregar_mensal_melhor_e_pior_dia_usam_liquido_por_contrato():
    mensal = agregar_mensal(_diario_jan_parcial_fev_completo())

    jan = mensal.loc["2025-01"]
    assert jan["melhor_dia"] == 49.5  # 15/01: (100-1)/2
    assert jan["pior_dia"] == -15.5  # 16/01: (-30-1)/2

    fev = mensal.loc["2025-02"]
    assert fev["melhor_dia"] == 99.5  # 10/02: (200-1)/2
    assert fev["pior_dia"] == 0.0  # pregões sem ordem entram zerados


def test_agregar_mensal_marca_mes_parcial_na_borda_da_serie():
    mensal = agregar_mensal(_diario_jan_parcial_fev_completo())

    # janeiro só começa em 15/01 nos dados, mas o pregão B3 real de janeiro
    # começa em 02/01 -- mês parcial.
    assert mensal.loc["2025-01", "mes_completo"] == False
    # fevereiro está inteiro dentro dos dados (03/02 a 28/02, igual ao
    # calendário B3 real) -- mês completo.
    assert mensal.loc["2025-02", "mes_completo"] == True


def test_agregar_mensal_avisa_incomplete_month_para_mes_parcial():
    # AGENTS.md épico 1, tarefa 1.3 (INCOMPLETE_MONTH)
    with pytest.warns(UserWarning, match="2025-01") as record:
        agregar_mensal(_diario_jan_parcial_fev_completo())
    codigos = [r.message.codigo for r in record if hasattr(r.message, "codigo")]
    assert "INCOMPLETE_MONTH" in codigos


def test_agregar_mensal_nao_avisa_quando_todos_os_meses_completos():
    diario = _diario_jan_parcial_fev_completo()
    apenas_fevereiro = diario.loc["2025-02":]
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        agregar_mensal(apenas_fevereiro)
    codigos = [w.message.codigo for w in record if hasattr(w.message, "codigo")]
    assert "INCOMPLETE_MONTH" not in codigos
