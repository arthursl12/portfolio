"""
RED: tradefolio.concentracao.dividir_em_subperiodos/metricas_por_subperiodo
ainda não existem (AGENTS.md épico 5.5 "dividir em subperíodos").

Escopo implementado, com o que fica deliberadamente de fora documentado
(não inventado): blocos de tamanho aproximadamente igual, escolhidos por
CONTAGEM DE PREGÕES (não por mês-calendário) conforme a duração total:
< 6 meses -> 1 bloco (histórico curto demais para subdividir); 6-12 meses
-> 3 blocos; 12-24 meses -> 4 blocos; > 24 meses -> semestres aproximados
(~126 pregões). O PDF-fonte também menciona "anos-calendário quando
disponíveis" -- NÃO implementado (alinhamento calendário exato exigiria
decidir como tratar o primeiro/último ano parcial, uma convenção
ambígua). "Estabilidade" (um dos campos pedidos) também não é
implementado -- termo não definido em lugar nenhum do PDF-fonte
(AGENTS.md §8: nunca inventar uma convenção sem definição). RLT por bloco
não é implementado -- bloqueado pelo Épico 6 (limiar), que não existe.

Valores conferidos por script contra tests/fixtures/romanos_orders.csv
(454 dias corridos ≈ 14,9 meses -> 4 blocos) antes deste teste.
"""
import warnings

import pandas as pd
import pytest

from tradefolio.alignment import preencher_calendario_b3
from tradefolio.concentracao import dividir_em_subperiodos, escolher_numero_de_blocos, metricas_por_subperiodo
from tradefolio.daily import agregar_diario
from tradefolio.loaders import carregar_ordens


def _serie_romanos() -> pd.Series:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ordens = carregar_ordens("tests/fixtures/romanos_orders.csv")
    diario = preencher_calendario_b3(agregar_diario(ordens))
    return diario["liquido_por_contrato"]


def test_escolher_numero_de_blocos_por_duracao():
    indice_curto = pd.date_range("2025-01-01", periods=100, freq="D")  # ~3 meses
    indice_6_12m = pd.date_range("2025-01-01", periods=250, freq="D")  # ~8 meses
    indice_12_24m = _serie_romanos().index  # ~14.9 meses
    indice_longo = pd.date_range("2020-01-01", periods=1200, freq="D")  # ~39 meses

    assert escolher_numero_de_blocos(pd.Series(0, index=indice_curto)) == 1
    assert escolher_numero_de_blocos(pd.Series(0, index=indice_6_12m)) == 3
    assert escolher_numero_de_blocos(pd.Series(0, index=indice_12_24m)) == 4
    assert escolher_numero_de_blocos(pd.Series(0, index=indice_longo)) > 4


def test_dividir_em_subperiodos_romanos_4_blocos_contiguos():
    serie = _serie_romanos()
    blocos = dividir_em_subperiodos(serie)
    assert len(blocos) == 4
    # blocos contiguos e sem sobreposicao: cobrem a serie inteira
    assert sum(len(b) for b in blocos) == len(serie)
    assert blocos[0].index.min() == serie.index.min()
    assert blocos[-1].index.max() == serie.index.max()


def test_metricas_por_subperiodo_romanos():
    serie = _serie_romanos()
    tabela = metricas_por_subperiodo(serie)

    assert len(tabela) == 4
    assert tabela.iloc[0]["inicio"] == pd.Timestamp("2025-06-11")
    assert tabela.iloc[0]["fim"] == pd.Timestamp("2025-09-29")
    assert tabela.iloc[0]["lucro"] == pytest.approx(1607.00)
    assert tabela.iloc[0]["max_drawdown"] == pytest.approx(-1193.50)
    assert tabela.iloc[0]["profit_factor"] == pytest.approx(1.3263, abs=1e-3)
    assert tabela.iloc[0]["pct_dias_positivos"] == pytest.approx(0.4487, abs=1e-3)

    assert tabela.iloc[3]["lucro"] == pytest.approx(4686.50)
    assert tabela.iloc[3]["max_drawdown"] == pytest.approx(-1441.50)


def test_dividir_em_subperiodos_historico_curto_retorna_um_bloco():
    serie = pd.Series([1.0] * 50, index=pd.date_range("2025-01-01", periods=50, freq="D"))
    blocos = dividir_em_subperiodos(serie)
    assert len(blocos) == 1
    assert len(blocos[0]) == 50
