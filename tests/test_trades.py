"""
RED: tradefolio.trades.reconstruir_trades ainda não existe.

Convenção testada (CLAUDE.md > "Trade reconstruction", AGENTS.md §9):
um trade é o intervalo em que a posição líquida sai de zero e volta a zero
(agrupando fills parciais), não uma linha de ordem nem uma linha "saída".
Valores esperados vêm de tests/fixtures/mini_fixture_expected.md (calculados
à mão).

O parsing do CSV abaixo é setup de teste (loaders.py ainda não existe), não
reproduz a lógica sob teste — apenas monta o formato de dataframe que
reconstruir_trades espera receber.
"""
from pathlib import Path

import pandas as pd
import pytest

from tradefolio.trades import reconstruir_trades

FIXTURE = Path(__file__).parent / "fixtures" / "mini_fixture_orders.csv"


def _parse_valor_br(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip().replace({"-": None})
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


@pytest.fixture
def ordens() -> pd.DataFrame:
    df = pd.read_csv(FIXTURE, sep=";", quotechar='"', encoding="utf-8")
    df["dt"] = pd.to_datetime(df["Data/Hora"], format="%d/%m/%Y / %H:%M:%S")
    df["Resultado (R$)"] = _parse_valor_br(df["Resultado (R$)"])
    df["Quantidade executada"] = pd.to_numeric(df["Quantidade executada"], errors="coerce")
    return df.sort_values("dt").reset_index(drop=True)


def test_reconstroi_cinco_trades(ordens):
    trades = reconstruir_trades(ordens)
    assert len(trades) == 5


def test_resultado_bruto_por_trade(ordens):
    trades = reconstruir_trades(ordens)
    assert list(trades["resultado_bruto"]) == [200.0, 100.0, -150.0, -300.0, 0.0]


def test_quantidade_negociada_conta_entrada_e_saida(ordens):
    # cada trade: 2 contratos na entrada + 2 na saida = 4 unidades executadas
    trades = reconstruir_trades(ordens)
    assert list(trades["qtd_negociada"]) == [4, 4, 4, 4, 4]


def test_resultado_liquido_desconta_custo_b3(ordens):
    # custo = qtd_negociada(4) * R$0,25 = R$1,00 por trade
    trades = reconstruir_trades(ordens)
    assert list(trades["resultado_liquido"]) == [199.0, 99.0, -151.0, -301.0, -1.0]


def test_trade_com_resultado_bruto_zero_fica_negativo_liquido(ordens):
    # trade 5 (08/01): resultado bruto exatamente zero, mas custo torna
    # o resultado liquido negativo -- nao deve ser classificado como ganho.
    trades = reconstruir_trades(ordens)
    quinto = trades.iloc[4]
    assert quinto["resultado_bruto"] == 0.0
    assert quinto["resultado_liquido"] == -1.0


def test_direcao_do_trade_segue_a_primeira_perna(ordens):
    trades = reconstruir_trades(ordens)
    # trade 1: primeira perna e compra (C)
    assert trades.iloc[0]["direcao"] == "compra"
    # trade 3 (03/01, segundo trade do dia): primeira perna e venda (V)
    assert trades.iloc[2]["direcao"] == "venda"
