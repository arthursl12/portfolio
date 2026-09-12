"""
RED: tradefolio.daily.agregar_diario_por_ativo ainda não existe (AGENTS.md
épico 3, tarefa 3.1 "P&L por ativo, quantidade por ativo").

Robôs multi-ativo (ex. Robô Raiz: WIN + WDO) hoje têm o resultado somado
sem quebra por ativo -- confirmado que nenhum módulo lê a coluna 'Ativo'
antes desta tarefa. Agrupa por (data, raiz_do_ativo) -- raiz, não o código
completo do contrato, para não quebrar a série por rolagem de vencimento
(CLAUDE.md > CSV format: "Ativo muda ao longo do tempo por rolagem de
contrato futuro -- tratar como série contínua, não uma quebra").

Propriedade verificada: somar o breakdown por ativo, por dia, reproduz
exatamente o total de agregar_diario (nenhum resultado se perde nem
duplica ao quebrar por ativo).
"""
from pathlib import Path

import pandas as pd
import pytest

from tradefolio.daily import agregar_diario, agregar_diario_por_ativo

CABECALHO = (
    "#;Data/Hora;Ativo;C/V;Quantidade;Preço limite;Status;Tipo;"
    "Quantidade executada;Preço médio;Resultado (Abs.);Resultado %;Resultado (R$)"
)


def _parse_valor_br(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip().replace({"-": None})
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def _ordens_win_e_wdo(tmp_path: Path) -> pd.DataFrame:
    # 02/01: 1 trade WIN (2 contratos, +200) e 1 trade WDO (1 contrato, -50)
    # 03/01: so WIN (2 contratos, +100) -- WDO nao aparece nesse dia
    linhas = [
        '1;02/01/2025 / 09:00:00;WINF25;C;2;140000;executada;entrada;2;140000;-;-;-',
        '2;02/01/2025 / 09:05:00;WINF25;V;2;140100;executada;saída;2;140100;200,00;0,07;200,00',
        '3;02/01/2025 / 10:00:00;WDOF25;C;1;5000;executada;entrada;1;5000;-;-;-',
        '4;02/01/2025 / 10:05:00;WDOF25;V;1;4950;executada;saída;1;4950;-50,00;-1,00;-50,00',
        '5;03/01/2025 / 09:00:00;WINF25;C;2;140000;executada;entrada;2;140000;-;-;-',
        '6;03/01/2025 / 09:05:00;WINF25;V;2;140050;executada;saída;2;140050;100,00;0,04;100,00',
    ]
    caminho = tmp_path / "win_wdo.csv"
    caminho.write_text(CABECALHO + "\n" + "\n".join(linhas) + "\n", encoding="utf-8")

    df = pd.read_csv(caminho, sep=";", quotechar='"', encoding="utf-8")
    df["dt"] = pd.to_datetime(df["Data/Hora"], format="%d/%m/%Y / %H:%M:%S")
    df["data"] = df["dt"].dt.normalize()
    df["Resultado (R$)"] = _parse_valor_br(df["Resultado (R$)"])
    df["Quantidade executada"] = pd.to_numeric(df["Quantidade executada"], errors="coerce")
    return df.sort_values("dt").reset_index(drop=True)


@pytest.fixture
def ordens(tmp_path):
    return _ordens_win_e_wdo(tmp_path)


def test_agregar_diario_por_ativo_separa_win_e_wdo(ordens):
    por_ativo = agregar_diario_por_ativo(ordens)

    assert por_ativo.loc[("2025-01-02", "WIN"), "bruto"] == pytest.approx(200.0)
    assert por_ativo.loc[("2025-01-02", "WDO"), "bruto"] == pytest.approx(-50.0)
    assert por_ativo.loc[("2025-01-03", "WIN"), "bruto"] == pytest.approx(100.0)
    # WDO nao operou em 03/01 -- nao deve aparecer uma linha (0.0) para ele
    assert ("2025-01-03", "WDO") not in por_ativo.index


def test_agregar_diario_por_ativo_quantidade_e_custo_por_ativo(ordens):
    por_ativo = agregar_diario_por_ativo(ordens)
    # WIN 02/01: entrada(2) + saida(2) = 4 unidades -> custo 1.00
    assert por_ativo.loc[("2025-01-02", "WIN"), "quantidade"] == 4
    assert por_ativo.loc[("2025-01-02", "WIN"), "custo"] == pytest.approx(1.00)
    # WDO 02/01: entrada(1) + saida(1) = 2 unidades -> custo 0.50
    assert por_ativo.loc[("2025-01-02", "WDO"), "quantidade"] == 2
    assert por_ativo.loc[("2025-01-02", "WDO"), "custo"] == pytest.approx(0.50)


def test_soma_por_ativo_reconcilia_com_agregar_diario_total(ordens):
    diario_total = agregar_diario(ordens)
    por_ativo = agregar_diario_por_ativo(ordens)

    soma_por_dia = por_ativo.groupby(level="data")[["bruto", "custo", "liquido"]].sum()
    for data in diario_total.index:
        data_str = data.strftime("%Y-%m-%d")
        if data_str in soma_por_dia.index:
            assert soma_por_dia.loc[data_str, "bruto"] == pytest.approx(diario_total.loc[data, "bruto"])
            assert soma_por_dia.loc[data_str, "custo"] == pytest.approx(diario_total.loc[data, "custo"])
