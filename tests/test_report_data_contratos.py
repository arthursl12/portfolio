"""
RED: bug real encontrado com um CSV do usuário (orders_resgat.csv, 6
contratos) -- report_data.montar_dataframe_diario chamava agregar_diario
sem contratos_referencia, então CONTRATOS_REFERENCIA_PADRAO=2 (do
backtest do Romanos) era aplicado a qualquer CSV, mesmo um gravado a 6
contratos. calcular_pagina1 tinha o mesmo problema na fórmula de
retorno_bruto_pct.
"""
from pathlib import Path

import pandas as pd
import pytest

from tradefolio.report_data import calcular_pagina1, montar_dataframe_diario

CABECALHO = (
    "#;Data/Hora;Ativo;C/V;Quantidade;Preço limite;Status;Tipo;"
    "Quantidade executada;Preço médio;Resultado (Abs.);Resultado %;Resultado (R$)"
)


def _csv_seis_contratos(tmp_path: Path) -> Path:
    # mesmo shape de tests/fixtures/mini_fixture_orders.csv, mas a 6
    # contratos (como orders_resgat.csv) em vez de 2.
    linhas = [
        '1;02/01/2025 / 09:00:00;WINF25;C;6;140000;executada;entrada;6;140000;-;-;-',
        '2;02/01/2025 / 09:05:00;WINF25;V;6;140100;executada;saída;6;140100;600,00;0,07;600,00',
    ]
    caminho = tmp_path / "seis_contratos.csv"
    caminho.write_text(CABECALHO + "\n" + "\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def test_montar_dataframe_diario_detecta_seis_contratos_nao_dois(tmp_path):
    diario = montar_dataframe_diario(_csv_seis_contratos(tmp_path))
    # custo: 6 pernas (entrada) + 6 (saida) = 12 * 0.25 = 3.00; liquido = 600-3=597
    # liquido_por_contrato deve dividir por 6 (referencia real), nao por 2
    assert diario.loc["2025-01-02", "liquido_por_contrato"] == pytest.approx(597.0 / 6)


def test_calcular_pagina1_aceita_contratos_referencia_explicito(tmp_path):
    diario = montar_dataframe_diario(_csv_seis_contratos(tmp_path))
    metricas, _, _ = calcular_pagina1(diario, contratos_referencia=6)
    # retorno_bruto_pct usando a referencia correta (6, nao o default 2)
    assert metricas["retorno_bruto_pct"] == pytest.approx((600.0 / 6) / 1000 * 100)
