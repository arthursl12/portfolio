"""
RED: agregar_diario e reconstruir_trades ainda tratam qualquer linha de
ordens.csv como executada, mesmo quando Status != "executada" (AGENTS.md
épico 1, tarefa 1.1 "manter ordens canceladas").

Descoberto em dados_exemplo/orders_roboraiz.csv: 213 ordens "cancelada" +
1 "expirada", todas com Quantidade executada == 0 e Tipo == "saída".

Duas correções necessárias, não uma:
1. agregar_diario deve ignorar ordens não executadas na agregação diária
   (custo, bruto, n_trades) -- hoje quantidade==0 já não afeta as somas,
   mas contar uma ordem cancelada em n_trades é factualmente errado
   (nada foi executado), não apenas uma questão de estilo.
2. reconstruir_trades tem um bug real: se uma ordem não executada (qty=0)
   chega com posição líquida já em 0, o loop entra no branch "posição==0"
   (abre um trade novo) e, como qty=0 não muda a posição, IMEDIATAMENTE
   fecha esse mesmo trade na mesma linha -- um trade fantasma de duração
   zero, resultado zero, seria contado. reconstruir_trades precisa pular
   ordens não executadas inteiramente.
"""
from pathlib import Path

import pandas as pd
import pytest

from tradefolio.daily import agregar_diario
from tradefolio.trades import reconstruir_trades

CABECALHO = (
    "#;Data/Hora;Ativo;C/V;Quantidade;Preço limite;Status;Tipo;"
    "Quantidade executada;Preço médio;Resultado (Abs.);Resultado %;Resultado (R$)"
)


def _parse_valor_br(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip().replace({"-": None})
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def _ordens_com_uma_cancelada(tmp_path: Path) -> pd.DataFrame:
    # trade normal (2 contratos) + uma ordem cancelada no meio, quando a
    # posição já está em zero (o cenário exato que quebra reconstruir_trades)
    linhas = [
        '1;02/01/2025 / 09:00:00;WINF25;C;2;140000;executada;entrada;2;140000;-;-;-',
        '2;02/01/2025 / 09:05:00;WINF25;V;2;140100;executada;saída;2;140100;200,00;0,07;200,00',
        '3;02/01/2025 / 10:00:00;WINF25;V;3;0,00;cancelada;saída;0;-;-;-;-',
        '4;03/01/2025 / 09:00:00;WINF25;C;2;140000;executada;entrada;2;140000;-;-;-',
        '5;03/01/2025 / 09:05:00;WINF25;V;2;140050;executada;saída;2;140050;100,00;0,04;100,00',
    ]
    caminho = tmp_path / "com_cancelada.csv"
    caminho.write_text(CABECALHO + "\n" + "\n".join(linhas) + "\n", encoding="utf-8")

    df = pd.read_csv(caminho, sep=";", quotechar='"', encoding="utf-8")
    df["dt"] = pd.to_datetime(df["Data/Hora"], format="%d/%m/%Y / %H:%M:%S")
    df["data"] = df["dt"].dt.normalize()
    df["Resultado (R$)"] = _parse_valor_br(df["Resultado (R$)"])
    df["Quantidade executada"] = pd.to_numeric(df["Quantidade executada"], errors="coerce")
    return df.sort_values("dt").reset_index(drop=True)


@pytest.fixture
def ordens(tmp_path):
    return _ordens_com_uma_cancelada(tmp_path)


def test_agregar_diario_ignora_ordem_cancelada_no_n_trades(ordens):
    diario = agregar_diario(ordens)
    # 02/01 tem 1 saida executada (a cancelada nao deve contar)
    assert diario.loc["2025-01-02", "n_trades"] == 1


def test_agregar_diario_ignora_ordem_cancelada_no_bruto_e_custo(ordens):
    diario = agregar_diario(ordens)
    # custo de 02/01: so a entrada(2) + saida executada(2) = 4 * 0.25 = 1.00
    # (a cancelada tem qtd 0, nao mudaria a soma, mas confirma que o filtro
    # por Status nao quebra o calculo correto)
    assert diario.loc["2025-01-02", "custo"] == pytest.approx(1.00)
    assert diario.loc["2025-01-02", "bruto"] == pytest.approx(200.00)


def test_reconstruir_trades_nao_cria_trade_fantasma_para_ordem_cancelada(ordens):
    trades = reconstruir_trades(ordens)
    # exatamente 2 trades reais (02/01 e 03/01) -- nao 3 (a cancelada nao
    # deve virar um "trade" de duracao zero e resultado zero)
    assert len(trades) == 2
    assert list(trades["resultado_bruto"]) == [200.0, 100.0]
