"""
RED: tradefolio.daily.detectar_contratos_referencia_piramide ainda não existe.

Problema real (usuário, robô "Flecha"): entra contra a tendência e, se o
preço segue contra, REFORÇA a mesma posição em múltiplas pernas de
'entrada' (ex. 1 -> 1 -> 2 contratos) até reverter e fechar tudo numa
única 'saída' grande. `detectar_contratos_referencia` (heurística de
quantidade dominante, tests/test_daily_deteccao.py) e
`detectar_contratos_referencia_multi_ativo` (janela por ativo,
tests/test_daily_multi_ativo_referencia.py) falham nesse CSV -- nenhuma
quantidade de ordem é dominante, porque a saída soma pernas de tamanhos
variados, não repete um valor fixo. Confirmado rodando os dois contra
dados_exemplo/orders_flecha.csv antes deste teste: ambos levantam
ValueError em qualquer janela testada (30 a 5000 dias).

Convenção adotada nesta sessão para "contratos_referencia" de um robô
piramidante (decisão do usuário, não inventada -- AGENTS.md §24): o MDC
(GCD) das quantidades de TODAS as pernas de 'entrada' executadas -- a
menor unidade de reforço recorrente. Só é aplicada quando há evidência
ESTRUTURAL de piramidação (>= 1 trade reconstruído com mais de uma
perna de 'entrada'); sem essa evidência, levanta erro em vez de tratar
qualquer distribuição de quantidade não-dominante como piramidação --
isso incluiria orders_roboraiz.csv (tamanho de posição genuinamente
dinâmico, sem reforço em múltiplas pernas), que deve continuar exigindo
intervenção humana e por isso não é reproduzido aqui como caso de
sucesso.
"""
import warnings

import pandas as pd
import pytest

from tradefolio.daily import detectar_contratos_referencia_piramide
from tradefolio.loaders import carregar_ordens

CSV_FLECHA = "dados_exemplo/orders_flecha.csv"


def _ordens_flecha():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return carregar_ordens(CSV_FLECHA)


def _ordens_de_trades(trades: list[list[tuple[str, str, int]]]) -> pd.DataFrame:
    """Monta um DataFrame mínimo a partir de trades: cada trade é uma
    lista de pernas (C/V, Tipo, quantidade), em ordem cronológica. `dt`
    é atribuído sequencialmente (1 minuto por perna) para garantir a
    ordem que `sort_values("dt")` dentro da função depende."""
    linhas = []
    minuto = 0
    for trade in trades:
        for lado, tipo, qtd in trade:
            linhas.append(
                {
                    "dt": pd.Timestamp("2024-01-01") + pd.Timedelta(minutes=minuto),
                    "Status": "executada",
                    "C/V": lado,
                    "Tipo": tipo,
                    "Quantidade executada": qtd,
                }
            )
            minuto += 1
    return pd.DataFrame(linhas)


def test_detecta_unidade_1_quando_reforcos_sao_1_1_2():
    trades = [
        [("C", "entrada", 1), ("C", "entrada", 1), ("C", "entrada", 2), ("V", "saída", 4)],
        [("C", "entrada", 1), ("V", "saída", 1)],
    ]
    assert detectar_contratos_referencia_piramide(_ordens_de_trades(trades)) == 1


def test_detecta_unidade_maior_que_1_quando_reforcos_sao_multiplos_de_3():
    trades = [
        [("C", "entrada", 3), ("C", "entrada", 3), ("C", "entrada", 6), ("V", "saída", 12)],
        [("C", "entrada", 3), ("V", "saída", 3)],
    ]
    assert detectar_contratos_referencia_piramide(_ordens_de_trades(trades)) == 3


def test_levanta_erro_sem_evidencia_estrutural_de_piramide():
    # nenhum trade tem mais de uma perna de 'entrada' -- quantidade sem
    # valor dominante aqui não é piramidação, é outra coisa (ex.
    # dimensionamento dinâmico tipo orders_roboraiz.csv), e não deve ser
    # adivinhada.
    trades = [
        [("C", "entrada", 3), ("V", "saída", 3)],
        [("C", "entrada", 1), ("V", "saída", 1)],
        [("C", "entrada", 2), ("V", "saída", 2)],
    ]
    with pytest.raises(ValueError, match="piramid"):
        detectar_contratos_referencia_piramide(_ordens_de_trades(trades))


def test_flecha_end_to_end_flat_e_multi_ativo_falham_piramide_resolve():
    from tradefolio.daily import (
        detectar_contratos_referencia,
        detectar_contratos_referencia_multi_ativo,
    )

    ordens = _ordens_flecha()
    with pytest.raises(ValueError):
        detectar_contratos_referencia(ordens)
    with pytest.raises(ValueError):
        detectar_contratos_referencia_multi_ativo(ordens, dias_recentes=90)
    assert detectar_contratos_referencia_piramide(ordens) == 1
