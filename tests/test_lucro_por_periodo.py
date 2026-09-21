"""RED: tradefolio.portfolio.lucro_por_periodo ainda não existe.

Convenção (documentada, AGENTS.md §8): soma da série COMBINADA (R$ total,
mesma base de `metricas_agregadas["lucro_mensal"]`) por período-calendário.
Semana = segunda a domingo, rotulada pela segunda-feira que a abre; mês =
mês-calendário, rotulado pelo primeiro dia. `completo` é False para o
primeiro/último período quando a série começa/termina no meio dele.
Datas: 2025-01-06 é segunda-feira.
"""
import pandas as pd
import pytest

from tradefolio.portfolio import lucro_por_periodo


def _serie():
    idx = pd.to_datetime(
        ["2025-01-08", "2025-01-09", "2025-01-10", "2025-01-13", "2025-01-14", "2025-02-03"]
    )
    return pd.Series([10.0, -4.0, 3.0, 5.0, -20.0, 7.0], index=idx)


def test_semanal_soma_e_rotulo_segunda():
    r = lucro_por_periodo(_serie(), "semanal")
    assert list(r.index) == [pd.Timestamp("2025-01-06"), pd.Timestamp("2025-01-13")] + [
        pd.Timestamp("2025-01-20"), pd.Timestamp("2025-01-27"), pd.Timestamp("2025-02-03")
    ]
    assert r.loc["2025-01-06", "lucro"] == 9.0
    assert r.loc["2025-01-13", "lucro"] == -15.0
    # semanas sem pregão na série ficam 0 (não removidas)
    assert r.loc["2025-01-20", "lucro"] == 0.0
    assert r.loc["2025-02-03", "lucro"] == 7.0


def test_mensal_soma_e_rotulo_primeiro_dia():
    r = lucro_por_periodo(_serie(), "mensal")
    assert list(r.index) == [pd.Timestamp("2025-01-01"), pd.Timestamp("2025-02-01")]
    assert r["lucro"].tolist() == [-6.0, 7.0]


def test_completo_marca_bordas_parciais():
    r = lucro_por_periodo(_serie(), "mensal")
    assert r["completo"].tolist() == [False, False]
    r = lucro_por_periodo(_serie(), "semanal")
    assert r["completo"].iloc[0] == False  # começa quarta
    assert r["completo"].iloc[1] == True   # segunda a sexta presentes
    assert r["completo"].iloc[-1] == False  # termina segunda


def test_frequencia_invalida():
    with pytest.raises(ValueError):
        lucro_por_periodo(_serie(), "anual")
