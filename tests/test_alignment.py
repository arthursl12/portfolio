"""
RED: tradefolio.alignment.preencher_calendario_b3 ainda não existe.

Convenção testada (CLAUDE.md > "Trading calendar", AGENTS.md §10/§14/§15):
a série diária deve ser reindexada no calendário de pregões da B3 entre a
primeira e a última data presentes nos dados; um pregão sem nenhuma ordem
entra com resultado 0 e operou=False -- não é descartado nem confundido com
dado faltante.

Datas verificadas contra pandas_market_calendars (calendário 'B3') para
02-08/01/2025: 5 pregões (02, 03, 06, 07, 08) -- 07/01 é pregão sem ordem
na fixture (ver tests/fixtures/mini_fixture_expected.md).
"""
import pandas as pd

from tradefolio.alignment import preencher_calendario_b3


def _diario_sem_07_01() -> pd.DataFrame:
    # dados de tests/fixtures/mini_fixture_expected.md, tabela "Série diária"
    # -- 07/01 fica de fora de proposito: nenhuma ordem naquele dia.
    return pd.DataFrame(
        {
            "bruto": [200.00, -50.00, -300.00, 0.00],
            "custo": [1.00, 2.00, 1.00, 1.00],
            "n_trades": [1, 2, 1, 1],
        },
        index=pd.DatetimeIndex(
            ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-08"], name="data"
        ),
    )


def test_preenche_pregao_sem_ordem_com_zero():
    resultado = preencher_calendario_b3(_diario_sem_07_01())
    assert len(resultado) == 5
    dia_vazio = resultado.loc["2025-01-07"]
    assert dia_vazio["bruto"] == 0.0
    assert dia_vazio["custo"] == 0.0
    assert dia_vazio["n_trades"] == 0


def test_operou_e_falso_so_no_pregao_sem_ordem():
    resultado = preencher_calendario_b3(_diario_sem_07_01())
    assert resultado.loc["2025-01-07", "operou"] == False
    for data in ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-08"]:
        assert resultado.loc[data, "operou"] == True


def test_nao_estende_calendario_alem_dos_dados():
    resultado = preencher_calendario_b3(_diario_sem_07_01())
    assert resultado.index.min() == pd.Timestamp("2025-01-02")
    assert resultado.index.max() == pd.Timestamp("2025-01-08")
