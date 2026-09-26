"""
RED: reconstruir_trades tracks ONE net-position counter across the whole
`ordens` argument, with no split by instrument (`Ativo`).

Found while grounding a post about trade reconstruction: on a real
two-instrument file (`dados_exemplo/orders_roboraiz.csv`, WIN+WDO),
reconstruir_trades(ordens) on the combined file returns 900 trades, while
reconstructing WIN and WDO separately (via `validation.extrair_raiz_ativo`,
the same per-instrument split `daily.agregar_diario_por_ativo` already
uses) gives 791 + 801 = 1592. `report_data.calcular_pagina2` calls
`reconstruir_trades(ordens)` on the whole file with no per-instrument split
anywhere in the chain from `app.py`/`report.py` -- so Profit Factor, win
rate and streaks (Página 2) are wrong today for any multi-instrument robot.

Minimal repro below (2 instruments, interleaved, no real data needed):
WIN opens at 09:00, WDO opens at 09:02 (WIN still open), WIN closes at
09:05 (WDO still open -- net position across BOTH instruments is not
zero, so the combined algorithm does NOT close a trade here), WDO closes
at 09:10 (only now does the combined net position hit zero). Two real,
independent trades (one per instrument) get merged into one.
"""
from pathlib import Path

import pandas as pd
import pytest

from tradefolio.trades import reconstruir_trades

CABECALHO = (
    "#;Data/Hora;Ativo;C/V;Quantidade;Preço limite;Status;Tipo;"
    "Quantidade executada;Preço médio;Resultado (Abs.);Resultado %;Resultado (R$)"
)


def _parse_valor_br(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip().replace({"-": None})
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


@pytest.fixture
def ordens_dois_ativos(tmp_path: Path) -> pd.DataFrame:
    linhas = [
        '1;02/01/2025 / 09:00:00;WINF25;C;2;140000;executada;entrada;2;140000;-;-;-',
        '2;02/01/2025 / 09:02:00;WDOF25;C;1;5000,00;executada;entrada;1;5000,00;-;-;-',
        '3;02/01/2025 / 09:05:00;WINF25;V;2;140100;executada;saída;2;140100;200,00;0,07;200,00',
        '4;02/01/2025 / 09:10:00;WDOF25;V;1;5010,00;executada;saída;1;5010,00;10,00;0,20;10,00',
    ]
    caminho = tmp_path / "dois_ativos.csv"
    caminho.write_text(CABECALHO + "\n" + "\n".join(linhas) + "\n", encoding="utf-8")

    df = pd.read_csv(caminho, sep=";", quotechar='"', encoding="utf-8")
    df["dt"] = pd.to_datetime(df["Data/Hora"], format="%d/%m/%Y / %H:%M:%S")
    df["Resultado (R$)"] = _parse_valor_br(df["Resultado (R$)"])
    df["Quantidade executada"] = pd.to_numeric(df["Quantidade executada"], errors="coerce")
    return df.sort_values("dt").reset_index(drop=True)


def test_reconstruir_trades_nao_mistura_posicao_entre_ativos(ordens_dois_ativos):
    # WIN e WDO nunca interagem -- são 2 trades independentes, não 1.
    # Sem o split por instrumento, a posição combinada só zera na ÚLTIMA
    # saída (09:10), fundindo os dois trades reais em um só.
    trades = reconstruir_trades(ordens_dois_ativos)
    assert len(trades) == 2
    assert sorted(trades["resultado_bruto"]) == [10.0, 200.0]


def test_reconstruir_trades_real_multi_ativo_bate_com_split_manual():
    # Regressão contra dados reais (mesmos números conferidos ao apurar o
    # post): a série combinada deve reconciliar EXATAMENTE com a soma dos
    # dois ativos reconstruídos separadamente.
    from tradefolio.loaders import carregar_ordens
    from tradefolio.validation import extrair_raiz_ativo

    caminho = Path(__file__).parent.parent / "dados_exemplo" / "orders_roboraiz.csv"
    ordens = carregar_ordens(str(caminho))

    trades = reconstruir_trades(ordens)

    ordens["ativo_raiz"] = ordens["Ativo"].map(extrair_raiz_ativo)
    n_por_ativo = sum(
        len(reconstruir_trades(grupo)) for _, grupo in ordens.groupby("ativo_raiz")
    )
    assert len(trades) == n_por_ativo
    assert n_por_ativo == 1592
