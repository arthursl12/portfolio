"""
RED: tradefolio.metrics.maior_sequencia / maior_sequencia_detalhada ainda
não existem.

Convenção (AGENTS.md §7.1 "winning and losing streaks"; CLAUDE.md > "Trade
reconstruction" e mini_fixture_expected.md > "Casos de borda"): uma
sequência é uma corrida de dias/trades consecutivos com o mesmo sinal
(estritamente positivo ou estritamente negativo -- um valor exatamente
zero quebra a sequência, tanto para positivo quanto para negativo).

Nível trade: usa a série resultado_liquido dos 5 trades reconstruídos
(índice = número do trade, 1 a 5, batendo com os rótulos "trade #1" etc.
de tests/fixtures/mini_fixture_expected.md).

Nível dia: usa a série diária por contrato já alinhada no calendário B3
(mesma de test_metrics_tail_risk.py). Aqui 07/01 (dia sem trade, valor
0.0) quebra a sequência negativa entre 06/01 e 08/01 -- isso é o
comportamento correto no nível dia (um dia sem perda não é uma perda),
diferente do nível trade, onde 07/01 nunca aparece na série (trades são
indexados por trade, não por data), então lá a sequência não é
interrompida por ele. Valores de dia não estão no fixture (só os de
trade estão) -- foram calculados à mão e conferidos por script antes de
escrever este teste (ver histórico da sessão).
"""
import pandas as pd

from tradefolio.metrics import maior_sequencia, maior_sequencia_detalhada, maior_sequencia_mascara

SERIE_DIARIA = pd.Series(
    [99.50, -26.00, -150.50, 0.00, -0.50],
    index=pd.DatetimeIndex(
        ["2025-01-02", "2025-01-03", "2025-01-06", "2025-01-07", "2025-01-08"]
    ),
)

SERIE_TRADES = pd.Series([199.0, 99.0, -151.0, -301.0, -1.0], index=[1, 2, 3, 4, 5])


def test_maior_sequencia_positiva_dias():
    assert maior_sequencia(SERIE_DIARIA, positivo=True) == 1


def test_maior_sequencia_negativa_dias():
    # 07/01 (valor 0.0) quebra a sequencia entre 06/01 e 08/01
    assert maior_sequencia(SERIE_DIARIA, positivo=False) == 2


def test_maior_sequencia_positiva_trades():
    assert maior_sequencia(SERIE_TRADES, positivo=True) == 2


def test_maior_sequencia_negativa_trades():
    assert maior_sequencia(SERIE_TRADES, positivo=False) == 3


def test_maior_sequencia_detalhada_positiva_dias():
    resultado = maior_sequencia_detalhada(SERIE_DIARIA, positivo=True)
    assert resultado == {
        "comprimento": 1,
        "valor_total": 99.50,
        "inicio": pd.Timestamp("2025-01-02"),
        "fim": pd.Timestamp("2025-01-02"),
    }


def test_maior_sequencia_detalhada_negativa_dias():
    resultado = maior_sequencia_detalhada(SERIE_DIARIA, positivo=False)
    assert resultado == {
        "comprimento": 2,
        "valor_total": -176.50,
        "inicio": pd.Timestamp("2025-01-03"),
        "fim": pd.Timestamp("2025-01-06"),
    }


def test_maior_sequencia_detalhada_positiva_trades():
    # mini_fixture_expected.md: "2 trades, R$298,00 (trades #1 e #2)"
    resultado = maior_sequencia_detalhada(SERIE_TRADES, positivo=True)
    assert resultado == {"comprimento": 2, "valor_total": 298.00, "inicio": 1, "fim": 2}


def test_maior_sequencia_detalhada_negativa_trades():
    # mini_fixture_expected.md: "3 trades, R$-453,00 (trades #3, #4 e #5)"
    resultado = maior_sequencia_detalhada(SERIE_TRADES, positivo=False)
    assert resultado == {"comprimento": 3, "valor_total": -453.00, "inicio": 3, "fim": 5}


def test_maior_sequencia_detalhada_sem_ocorrencia():
    # serie so com valores negativos: nao ha sequencia positiva alguma
    resultado = maior_sequencia_detalhada(pd.Series([-1.0, -2.0, -3.0]), positivo=True)
    assert resultado == {"comprimento": 0, "valor_total": 0.0, "inicio": None, "fim": None}


def test_maior_sequencia_sem_ocorrencia_e_zero():
    assert maior_sequencia(pd.Series([-1.0, -2.0, -3.0]), positivo=True) == 0


# ---------------------------------------------------------------------------
# datas_inicio/datas_fim separados: necessario para trades, onde inicio e fim
# de UM trade podem ser instantes diferentes (nao apenas o indice da serie).
# Timestamps conferidos por script contra tests/fixtures/mini_fixture_orders.csv
# reconstruido (ver historico da sessao).
# ---------------------------------------------------------------------------

TRADES_INICIO = pd.Series(
    pd.to_datetime([
        "2025-01-02 09:00:00", "2025-01-03 09:00:00", "2025-01-03 10:00:00",
        "2025-01-06 09:00:00", "2025-01-08 09:00:00",
    ]),
    index=[1, 2, 3, 4, 5],
)
TRADES_FIM = pd.Series(
    pd.to_datetime([
        "2025-01-02 09:05:00", "2025-01-03 09:05:00", "2025-01-03 10:05:00",
        "2025-01-06 09:05:00", "2025-01-08 09:05:00",
    ]),
    index=[1, 2, 3, 4, 5],
)


def test_maior_sequencia_detalhada_com_datas_inicio_fim_separadas_positiva():
    resultado = maior_sequencia_detalhada(
        SERIE_TRADES, positivo=True, datas_inicio=TRADES_INICIO, datas_fim=TRADES_FIM
    )
    assert resultado == {
        "comprimento": 2,
        "valor_total": 298.00,
        "inicio": pd.Timestamp("2025-01-02 09:00:00"),
        "fim": pd.Timestamp("2025-01-03 09:05:00"),
    }


def test_maior_sequencia_detalhada_com_datas_inicio_fim_separadas_negativa():
    resultado = maior_sequencia_detalhada(
        SERIE_TRADES, positivo=False, datas_inicio=TRADES_INICIO, datas_fim=TRADES_FIM
    )
    assert resultado == {
        "comprimento": 3,
        "valor_total": -453.00,
        "inicio": pd.Timestamp("2025-01-03 10:00:00"),
        "fim": pd.Timestamp("2025-01-08 09:05:00"),
    }


def test_maior_sequencia_mascara_generaliza_qualquer_predicado():
    # AGENTS.md épico 7.4: "meses consecutivos sem vapo" precisa de uma
    # condição de igualdade (== 0), que maior_sequencia (só > 0 / < 0)
    # não cobre -- maior_sequencia_mascara aceita a máscara já pronta.
    serie = pd.Series([0.0, 0.0, 5.0, 0.0, 0.0, 0.0, -3.0])
    assert maior_sequencia_mascara(serie == 0) == 3


def test_maior_sequencia_mascara_sem_ocorrencia_e_zero():
    assert maior_sequencia_mascara(pd.Series([1.0, 2.0]) == 0) == 0


def test_maior_sequencia_usa_mascara_por_baixo():
    # maior_sequencia(serie, positivo) deve continuar dando o mesmo
    # resultado de antes -- é um refactor (extrair maior_sequencia_mascara),
    # não uma mudança de comportamento.
    assert maior_sequencia(SERIE_DIARIA, positivo=True) == 1
    assert maior_sequencia(SERIE_DIARIA, positivo=False) == 2
