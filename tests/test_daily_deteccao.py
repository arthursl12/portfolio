"""
RED: tradefolio.daily.detectar_contratos_referencia ainda não existe.

Bug encontrado ao carregar um CSV real (orders_resgat.csv, 6 contratos)
com o pipeline: report_data.montar_dataframe_diario e app.py chamavam
agregar_diario sem passar contratos_referencia, então o default
CONTRATOS_REFERENCIA_PADRAO=2 (específico do backtest do robô Romanos)
era aplicado silenciosamente a qualquer CSV -- AGENTS.md §9: "each robot
has an operational unit" que não pode ser assumido igual entre robôs.

Convenção adotada (não é uma fórmula financeira, é uma heurística de
detecção -- documentada explicitamente por não haver uma autoridade
externa a seguir): usa o valor mais frequente de 'Quantidade executada'
como referência, desde que represente pelo menos 90% das linhas. Esse
limiar tolera ruído de fills parciais (o próprio romanos_orders.csv, já
validado, tem 4 linhas com quantidade 1 em 1645 -- 99,76% ainda é 2).
Abaixo de 90% (ex.: orders_roboraiz.csv, que varia dinamicamente entre 0
e 9 contratos sem um valor dominante) não é seguro inferir uma única
referência -- levanta erro em vez de adivinhar.
"""
import pandas as pd
import pytest

from tradefolio.daily import detectar_contratos_referencia


def _ordens_com_quantidades(quantidades: list[int]) -> pd.DataFrame:
    return pd.DataFrame({"Quantidade executada": quantidades})


def test_detecta_quantidade_constante():
    assert detectar_contratos_referencia(_ordens_com_quantidades([6] * 100)) == 6


def test_tolera_minoria_de_fills_parciais():
    # 1641 linhas com 2, 4 linhas com 1 -- mesma proporção de
    # tests/fixtures/romanos_orders.csv (99,76% dominante)
    quantidades = [2] * 1641 + [1] * 4
    assert detectar_contratos_referencia(_ordens_com_quantidades(quantidades)) == 2


def test_levanta_erro_sem_valor_dominante():
    # nenhum valor unico chega a 90% das linhas
    quantidades = [3] * 43 + [1] * 40 + [2] * 17
    with pytest.raises(ValueError, match="contratos"):
        detectar_contratos_referencia(_ordens_com_quantidades(quantidades))


def test_mensagem_de_erro_mostra_a_distribuicao():
    quantidades = [3] * 43 + [1] * 40 + [2] * 17
    with pytest.raises(ValueError, match=r"3.*43|43.*3"):
        detectar_contratos_referencia(_ordens_com_quantidades(quantidades))
