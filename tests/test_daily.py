"""
RED: tradefolio.daily.agregar_diario ainda não existe.

Agrega ordens (nível de execução) em série diária de resultado bruto/custo/
líquido, antes do alinhamento no calendário B3 (isso é responsabilidade de
tradefolio.alignment, testado separadamente). Valores esperados vêm de
tests/fixtures/mini_fixture_expected.md, tabela "Série diária".

`n_trades` aqui conta linhas "saída" por dia (proxy aproximado, usado só
para o flag `operou` do alinhamento de calendário) -- não é o mesmo que a
contagem de trades reconstruídos de tradefolio.trades, que agrupa fills
parciais. Essa distinção já existe no código original (`operacoes_aprox`
vs. `n_trades_reconstruidos`) e não está sendo alterada aqui.
"""
from pathlib import Path

import pandas as pd

from tradefolio.daily import agregar_diario

FIXTURE = Path(__file__).parent / "fixtures" / "mini_fixture_orders.csv"


def _parse_valor_br(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip().replace({"-": None})
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def _carregar_ordens_fixture() -> pd.DataFrame:
    df = pd.read_csv(FIXTURE, sep=";", quotechar='"', encoding="utf-8")
    df["dt"] = pd.to_datetime(df["Data/Hora"], format="%d/%m/%Y / %H:%M:%S")
    df["data"] = df["dt"].dt.normalize()
    df["Resultado (R$)"] = _parse_valor_br(df["Resultado (R$)"])
    df["Quantidade executada"] = pd.to_numeric(df["Quantidade executada"], errors="coerce")
    return df.sort_values("dt").reset_index(drop=True)


def test_agregar_diario_bruto_custo_liquido():
    diario = agregar_diario(_carregar_ordens_fixture())

    esperado = pd.DataFrame(
        {
            "bruto": [200.0, -50.0, -300.0, 0.0],
            "custo": [1.0, 2.0, 1.0, 1.0],
            "n_trades": [1, 2, 1, 1],
            "liquido": [199.0, -52.0, -301.0, -1.0],
            "liquido_por_contrato": [99.5, -26.0, -150.5, -0.5],
        },
        index=pd.DatetimeIndex(
            ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-08"], name="data"
        ),
    )

    pd.testing.assert_frame_equal(
        diario[["bruto", "custo", "n_trades", "liquido", "liquido_por_contrato"]],
        esperado,
        check_dtype=False,
    )


def test_agregar_diario_nao_inclui_pregao_sem_ordem():
    # 07/01 nao tem ordens -- o alinhamento de calendario (tradefolio.alignment)
    # e quem preenche esse dia, nao agregar_diario.
    diario = agregar_diario(_carregar_ordens_fixture())
    assert pd.Timestamp("2025-01-07") not in diario.index
