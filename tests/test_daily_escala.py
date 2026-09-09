"""
RED: tradefolio.daily.escalar_por_contratos ainda não existe.

Convenção (AGENTS.md §9 "Robot units and position sizing" + §7.1 lista
"operational-unit scaling" como cálculo puro a testar): os valores em
`liquido_por_contrato` (e a curva de equity/drawdown derivada dele) já
são normalizados para 1 contrato -- simular N contratos é escala linear
direta, assumida explicitamente pela própria normalização por-contrato
já usada em todo o pipeline (o custo B3 é uma taxa fixa por contrato, e
o CSV original já representa um tamanho de posição de referência fixo).

Importante: só os valores ABSOLUTOS (R$) escalam com o número de
contratos. Métricas percentuais (retorno %, drawdown %, Ulcer %) e
razões (Sharpe, Sortino, Calmar, Recovery Factor, Profit Factor, payoff)
são invariantes ao número de contratos -- não devem ser recalculadas
escalando o dataframe inteiro, e por isso esta função não mexe em
report_data.calcular_pagina1 (verificado algebricamente antes deste
teste: dobrar contratos dobra P&L e capital juntos, então a razão entre
eles não muda). escalar_por_contratos serve apenas para escalar os
campos/séries absolutos para exibição.
"""
import math

import pandas as pd
import pytest

from tradefolio.daily import escalar_por_contratos


def test_escala_um_valor_escalar():
    assert escalar_por_contratos(99.50, 4) == pytest.approx(398.00)


def test_escala_uma_serie():
    serie = pd.Series([1.0, -2.0, 3.0])
    resultado = escalar_por_contratos(serie, 3)
    pd.testing.assert_series_equal(resultado, pd.Series([3.0, -6.0, 9.0]))


def test_zero_contratos_produz_zero():
    assert escalar_por_contratos(150.0, 0) == 0.0


def test_um_contrato_mantem_valor_original():
    assert escalar_por_contratos(150.0, 1) == pytest.approx(150.0)


def test_n_contratos_negativo_levanta_erro():
    with pytest.raises(ValueError, match="negativo"):
        escalar_por_contratos(100.0, -1)
