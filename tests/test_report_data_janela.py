"""
RED: tradefolio.report_data.filtrar_por_janela ainda não existe.

Convenção: cada janela é relativa à ÚLTIMA data presente nos dados (não
à data de hoje -- o histórico do robô pode terminar no passado), usando
pd.DateOffset (meses/anos calendário, não dias fixos) para bater com a
expectativa de "1 mês" / "1 ano" reais. "desde o início" não filtra
nada. Um rótulo desconhecido levanta erro em vez de silenciosamente não
filtrar (AGENTS.md: nunca adivinhar uma convenção).
"""
import pandas as pd
import pytest

from tradefolio.report_data import JANELAS_DISPONIVEIS, filtrar_por_janela


@pytest.fixture
def diario_tres_anos() -> pd.DataFrame:
    # calendario diario simples (nao e B3 real, so para testar o corte de datas)
    datas = pd.date_range("2023-01-01", "2026-01-01", freq="D")
    return pd.DataFrame({"liquido_por_contrato": range(len(datas))}, index=datas)


def test_desde_o_inicio_nao_filtra(diario_tres_anos):
    resultado = filtrar_por_janela(diario_tres_anos, "desde o início")
    assert len(resultado) == len(diario_tres_anos)


def test_uma_semana(diario_tres_anos):
    resultado = filtrar_por_janela(diario_tres_anos, "1 semana")
    assert resultado.index.min() == diario_tres_anos.index.max() - pd.DateOffset(weeks=1)
    assert resultado.index.max() == diario_tres_anos.index.max()


def test_um_mes(diario_tres_anos):
    resultado = filtrar_por_janela(diario_tres_anos, "1 mês")
    assert resultado.index.min() == diario_tres_anos.index.max() - pd.DateOffset(months=1)


def test_tres_meses(diario_tres_anos):
    resultado = filtrar_por_janela(diario_tres_anos, "3 meses")
    assert resultado.index.min() == diario_tres_anos.index.max() - pd.DateOffset(months=3)


def test_seis_meses(diario_tres_anos):
    resultado = filtrar_por_janela(diario_tres_anos, "6 meses")
    assert resultado.index.min() == diario_tres_anos.index.max() - pd.DateOffset(months=6)


def test_um_ano(diario_tres_anos):
    resultado = filtrar_por_janela(diario_tres_anos, "1 ano")
    assert resultado.index.min() == diario_tres_anos.index.max() - pd.DateOffset(years=1)


def test_dois_anos(diario_tres_anos):
    resultado = filtrar_por_janela(diario_tres_anos, "2 anos")
    assert resultado.index.min() == diario_tres_anos.index.max() - pd.DateOffset(years=2)


def test_janela_desconhecida_levanta_erro(diario_tres_anos):
    with pytest.raises(ValueError, match="janela"):
        filtrar_por_janela(diario_tres_anos, "10 dias")


def test_janelas_disponiveis_lista_todos_os_rotulos():
    assert JANELAS_DISPONIVEIS == (
        "1 semana", "1 mês", "3 meses", "6 meses", "1 ano", "2 anos", "desde o início",
    )
