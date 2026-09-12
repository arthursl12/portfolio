"""
RED: tradefolio.limiar.rlt_acumulado/rlt_mensal/rlt_anualizado/rlt_movel
ainda não existem (AGENTS.md épico 4.2 "RLT -- retorno sobre o limiar").

Escala confirmada com o usuário (pergunta feita nesta sessão, depois de
decompor_limiar já existir): minimum_margin é da POSIÇÃO TOTAL, não por
contrato. Logo RLT usa a série TOTAL (diario['liquido'], não
liquido_por_contrato) tanto no numerador quanto no drawdown que alimenta
decompor_limiar -- misturar as duas escalas quebraria a razão.

Um único limiar (float já calculado por decompor_limiar) serve de
denominador fixo para todas as variantes -- acumulado, mensal (uma série,
um valor por mês) e anualizado usam a MESMA referência; não é
recalculado por janela. "Móvel 3-6-12m" é uma função genérica
(AGENTS.md §8.1: mesma fórmula, janela como parâmetro) em vez de três
funções fixas.

Valores conferidos por script contra dados_exemplo/orders_roboraiz.csv
(liquido total, contratos_referencia irrelevante para essa coluna) antes
deste teste: limiar=13.495,00 (minimum_margin=10.000, P95 sobre drawdown
TOTAL=-2.495,00, multiplicador=1.0, reserva_operacional=1.000,00 -- 10%
de 10.000). Lucro líquido total = 17.952,00.
"""
import warnings

import pandas as pd
import pytest

from tradefolio.alignment import preencher_calendario_b3
from tradefolio.daily import agregar_diario
from tradefolio.drawdowns import curva_equity, drawdown
from tradefolio.limiar import (
    decompor_limiar,
    normalizar_por_limiar,
    rlt_acumulado,
    rlt_anualizado,
    rlt_movel,
    rlt_mensal,
)
from tradefolio.loaders import carregar_ordens
from tradefolio.monthly import agregar_mensal
from tradefolio import metrics

CSV = "dados_exemplo/orders_roboraiz.csv"
LIMIAR = 13495.00  # ver docstring do módulo


def _diario_total():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ordens = carregar_ordens(CSV)
    # contratos_referencia=1 é irrelevante aqui -- 'liquido' (escala
    # total) não depende dele, só 'liquido_por_contrato' depende.
    return preencher_calendario_b3(agregar_diario(ordens, contratos_referencia=1))


def test_rlt_acumulado():
    diario = _diario_total()
    resultado = rlt_acumulado(diario["liquido"].sum(), LIMIAR)
    assert resultado == pytest.approx(1.330270, rel=1e-5)


def test_rlt_acumulado_limiar_zero_retorna_nan():
    import math

    assert math.isnan(rlt_acumulado(1000.0, 0.0))


def test_rlt_mensal():
    diario = _diario_total()
    mensal = agregar_mensal(diario)
    serie_rlt = rlt_mensal(mensal["liquido"], LIMIAR)
    assert serie_rlt.iloc[-1] == pytest.approx(0.173027, rel=1e-5)
    assert len(serie_rlt) == len(mensal)


def test_rlt_anualizado():
    diario = _diario_total()
    resultado = rlt_anualizado(diario["liquido"], LIMIAR)
    assert resultado == pytest.approx(0.372894, rel=1e-5)


def test_rlt_movel_3_meses():
    diario = _diario_total()
    mensal = agregar_mensal(diario)
    serie_rlt_movel = rlt_movel(mensal["liquido"], LIMIAR, janela_meses=3)
    assert serie_rlt_movel.iloc[-1] == pytest.approx(0.321675, rel=1e-5)
    assert len(serie_rlt_movel) == len(mensal)
    # janela incompleta no inicio -> NaN, nao um numero inventado
    assert pd.isna(serie_rlt_movel.iloc[0])


def test_normalizar_por_limiar_metricas_de_risco():
    """AGENTS.md épico 4.4: MDD/L, Pior dia/L, ES95/L, Ulcer/L, Pior mês/L
    -- mesma função genérica usada por rlt_acumulado (§8.1), aplicada a
    valores de risco em vez de retorno. Todos na escala TOTAL (mesma
    convenção de escala confirmada para o limiar)."""
    from tradefolio.drawdowns import curva_equity, drawdown, maximo_drawdown, ulcer_index

    diario = _diario_total()
    serie = diario["liquido"]
    equity = curva_equity(serie)
    dd = drawdown(equity)
    mensal = agregar_mensal(diario)

    assert normalizar_por_limiar(maximo_drawdown(dd), LIMIAR) == pytest.approx(-0.248388, rel=1e-5)
    assert normalizar_por_limiar(serie.min(), LIMIAR) == pytest.approx(-0.059096, rel=1e-5)
    assert normalizar_por_limiar(metrics.expected_shortfall(serie, 0.95), LIMIAR) == pytest.approx(
        -0.039290, rel=1e-5
    )
    assert normalizar_por_limiar(ulcer_index(dd), LIMIAR) == pytest.approx(0.081259, rel=1e-5)
    assert normalizar_por_limiar(mensal["liquido"].min(), LIMIAR) == pytest.approx(-0.107373, rel=1e-5)


def test_normalizar_por_limiar_limiar_zero_retorna_nan():
    import math

    assert math.isnan(normalizar_por_limiar(-500.0, 0.0))
