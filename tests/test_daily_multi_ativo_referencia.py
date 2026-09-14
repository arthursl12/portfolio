"""
RED: tradefolio.daily.contratos_referencia_por_ativo/
detectar_contratos_referencia_multi_ativo ainda não existem.

Problema real (usuário, robô Robô Raiz): a proporção entre pernas é
FIXA e indivisível -- "1 unidade" é 3 WIN + 2 WDO, não dá pra aumentar
só WIN ou só WDO; o próximo nível é 4 WDO + 6 WIN (2 unidades). Chamar
`detectar_contratos_referencia` sobre o CSV inteiro (misturando WIN e
WDO numa única distribuição de 'Quantidade executada') não detecta nada
-- nem WIN nem WDO dominam a mistura -- e é exatamente por isso que
`app.py` hoje trava com erro para esse CSV.

Mesmo POR PERNA, o histórico INTEIRO de WDO não tem quantidade dominante
(79,4%, abaixo do limiar de 90% -- já documentado no Épico 2.2/TASKS.md:
o robô mudou de 1 para 2 WDO por unidade em algum momento). Por isso
`dias_recentes` restringe a detecção a uma janela recente, sobre a
teoria de que a proporção ATUAL é o que importa para "Número de
unidades"/custo mensal/etc. -- não uma segmentação histórica completa
(isso seria o Épico 2.2 "próximo passo natural", ainda não implementado).

Janela de 90 dias escolhida como padrão documentado (não escondido) por
ser a menor testada que recupera a proporção completa (3 WIN + 2 WDO)
com sucesso nos dois lados -- conferido por script contra
dados_exemplo/orders_roboraiz.csv antes deste teste: 30/60/90/120/180
dias todos dão WDO=2/WIN=3; 365 dias já falha para WDO (79,4%, abaixo do
limiar). O parâmetro é ajustável pelo chamador, não fixado silenciosamente.
"""
import warnings

import pytest

from tradefolio.daily import contratos_referencia_por_ativo, detectar_contratos_referencia_multi_ativo
from tradefolio.loaders import carregar_ordens

CSV_MULTI_ATIVO = "dados_exemplo/orders_roboraiz.csv"
CSV_UNICO_ATIVO = "tests/fixtures/romanos_orders.csv"


def _ordens(csv):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return carregar_ordens(csv)


def test_contratos_referencia_por_ativo_janela_recente_recupera_proporcao():
    ordens = _ordens(CSV_MULTI_ATIVO)
    resultado = contratos_referencia_por_ativo(ordens, dias_recentes=90)
    assert resultado == {"WDO": 2, "WIN": 3}


def test_contratos_referencia_por_ativo_historico_inteiro_falha_para_wdo():
    # confirma que o problema é real e não foi "consertado" por acidente:
    # sem restringir a janela, WDO genuinamente não tem quantidade
    # dominante no histórico inteiro (mudou de proporção no passado).
    ordens = _ordens(CSV_MULTI_ATIVO)
    with pytest.raises(ValueError):
        contratos_referencia_por_ativo(ordens)


def test_contratos_referencia_por_ativo_janela_longa_demais_ainda_falha():
    ordens = _ordens(CSV_MULTI_ATIVO)
    with pytest.raises(ValueError):
        contratos_referencia_por_ativo(ordens, dias_recentes=365)


def test_contratos_referencia_por_ativo_sem_janela_funciona_para_ativo_unico():
    ordens = _ordens(CSV_UNICO_ATIVO)
    resultado = contratos_referencia_por_ativo(ordens)
    assert resultado == {"WIN": 2}


def test_detectar_contratos_referencia_multi_ativo_soma_as_pernas():
    ordens = _ordens(CSV_MULTI_ATIVO)
    total = detectar_contratos_referencia_multi_ativo(ordens, dias_recentes=90)
    assert total == 5  # 3 WIN + 2 WDO = "1 unidade"


def test_detectar_contratos_referencia_multi_ativo_equivale_a_detectar_contratos_referencia_para_ativo_unico():
    from tradefolio.daily import detectar_contratos_referencia

    ordens = _ordens(CSV_UNICO_ATIVO)
    assert detectar_contratos_referencia_multi_ativo(ordens) == detectar_contratos_referencia(ordens)
