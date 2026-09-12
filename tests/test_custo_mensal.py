"""
RED: tradefolio.custo_mensal ainda não existe.

Escopo (pedido explícito do usuário, fora dos épicos do PDF-fonte): um
custo mensal de plataforma/assinatura por robô, em DEGRAUS por faixa de
número de contratos (não linear -- ex. 1-5 contratos custa X, 6-10 custa
Y), sempre mensal (não por trade), configurável pelo usuário e podendo
ser zero. Precisa refletir em lucro líquido e em tudo que deriva dele
(drawdown, Sharpe, RLT, etc.).

Decisões de design tomadas (documentadas, não escondidas):
- Faixas são [min_contratos, max_contratos] com AMBOS os limites
  inclusivos (`max_contratos=None` = sem limite superior). Faixas
  sobrepostas levantam erro na construção -- em vez de escolher um
  desempate silencioso para uma fronteira ambígua (o próprio exemplo do
  usuário usa "1-5" e "5-8", que se sobrepõem em 5), a tabela força quem
  a define a resolver a sobreposição explicitamente.
- O custo é debitado no ÚLTIMO PREGÃO B3 de cada mês presente em
  `diario` -- mesma convenção de apuração "último pregão do mês" já
  usada em tradefolio.vapo/"lâmina ideal.pdf" §6, não uma nova
  inventada. Aplica mesmo em dia NO_TRADE (o robô paga a assinatura
  independente de ter operado) e mesmo em mês PARCIAL (mesmo
  comportamento de tradefolio.monthly, que já processa mês incompleto
  em vez de descartá-lo).
- Uma coluna `custo_mensal` NOVA e separada de `custo` (que continua
  sendo só o emolumento B3, tradefolio.costs) -- nunca misturar a
  origem dos dois custos. `liquido` passa a ser `bruto - custo -
  custo_mensal`; `liquido_por_contrato` é recomputado na mesma proporção.
- Escopo só na série agregada do robô inteiro (`diario`), não no
  breakdown por ativo (`agregar_diario_por_ativo`) -- uma assinatura de
  plataforma não é atribuível a uma perna específica de um robô
  multi-ativo; ratear isso seria uma convenção nova e arbitrária.

Valores conferidos por script contra tests/fixtures/romanos_orders.csv
(contratos_referencia=1) antes deste teste: 30/06/2025 é o último pregão
de junho, com bruto=965,00/custo=1,00/liquido=964,00 antes do ajuste;
31/07/2025 é o último pregão de julho, um dia NO_TRADE
(bruto=custo=liquido=0,00 antes do ajuste).
"""
import warnings

import pandas as pd
import pytest

from tradefolio.custo_mensal import (
    FaixaCustoMensal,
    TabelaCustoMensal,
    aplicar_custo_mensal,
    custo_mensal_zero,
)
from tradefolio.report_data import montar_dataframe_diario

CSV = "tests/fixtures/romanos_orders.csv"


def _diario():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return montar_dataframe_diario(CSV, contratos_referencia=1)


def test_tabela_custo_mensal_faixas_sobrepostas_levanta_erro():
    with pytest.raises(ValueError):
        TabelaCustoMensal(faixas=(
            FaixaCustoMensal(1, 5, 100.0),
            FaixaCustoMensal(5, 8, 150.0),
        ))


def test_tabela_custo_mensal_custo_para_cada_faixa():
    tabela = TabelaCustoMensal(faixas=(
        FaixaCustoMensal(1, 5, 100.0),
        FaixaCustoMensal(6, 10, 150.0),
        FaixaCustoMensal(11, None, 200.0),
    ))
    assert tabela.custo_para(1) == 100.0
    assert tabela.custo_para(5) == 100.0
    assert tabela.custo_para(6) == 150.0
    assert tabela.custo_para(10) == 150.0
    assert tabela.custo_para(11) == 200.0
    assert tabela.custo_para(500) == 200.0


def test_tabela_custo_mensal_contratos_fora_de_qualquer_faixa_levanta_erro():
    tabela = TabelaCustoMensal(faixas=(FaixaCustoMensal(1, 5, 100.0),))
    with pytest.raises(ValueError):
        tabela.custo_para(6)


def test_custo_mensal_zero_nao_cobra_nada():
    tabela = custo_mensal_zero()
    assert tabela.custo_para(1) == 0.0
    assert tabela.custo_para(999) == 0.0


def test_aplicar_custo_mensal_debita_no_ultimo_pregao_de_cada_mes():
    diario = _diario()
    tabela = TabelaCustoMensal(faixas=(FaixaCustoMensal(1, None, 100.0),))
    ajustado = aplicar_custo_mensal(diario, tabela, contratos_referencia=1)

    linha = ajustado.loc["2025-06-30"]
    assert linha["custo_mensal"] == pytest.approx(100.0)
    assert linha["custo"] == pytest.approx(1.0)  # custo B3 continua intocado
    assert linha["liquido"] == pytest.approx(964.0 - 100.0)
    assert linha["liquido_por_contrato"] == pytest.approx(964.0 - 100.0)

    # dia comum, no meio do mes -- nao debitado
    outro_dia = ajustado.loc["2025-06-11"]
    assert outro_dia["custo_mensal"] == pytest.approx(0.0)


def test_aplicar_custo_mensal_cobra_mesmo_em_dia_sem_operacao():
    diario = _diario()
    tabela = TabelaCustoMensal(faixas=(FaixaCustoMensal(1, None, 100.0),))
    ajustado = aplicar_custo_mensal(diario, tabela, contratos_referencia=1)

    linha = ajustado.loc["2025-07-31"]
    assert bool(linha["operou"]) is False
    assert linha["custo_mensal"] == pytest.approx(100.0)
    assert linha["liquido"] == pytest.approx(-100.0)


def test_aplicar_custo_mensal_zero_nao_muda_liquido():
    diario = _diario()
    ajustado = aplicar_custo_mensal(diario, custo_mensal_zero(), contratos_referencia=1)
    pd.testing.assert_series_equal(ajustado["liquido"], diario["liquido"])
    assert (ajustado["custo_mensal"] == 0.0).all()


def test_aplicar_custo_mensal_recalcula_liquido_por_contrato_proporcional():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        diario = montar_dataframe_diario(CSV, contratos_referencia=3)
    tabela = TabelaCustoMensal(faixas=(FaixaCustoMensal(1, None, 300.0),))
    ajustado = aplicar_custo_mensal(diario, tabela, contratos_referencia=3)

    linha = ajustado.loc["2025-06-30"]
    # liquido total cai 300; liquido_por_contrato (base 964/3) cai 300/3=100
    assert linha["liquido"] == pytest.approx(964.0 - 300.0)
    assert linha["liquido_por_contrato"] == pytest.approx(964.0 / 3 - 100.0)


def test_montar_dataframe_diario_aceita_tabela_custo_mensal_opcional():
    tabela = TabelaCustoMensal(faixas=(FaixaCustoMensal(1, None, 100.0),))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        sem_custo = montar_dataframe_diario(CSV, contratos_referencia=1)
        com_custo = montar_dataframe_diario(CSV, contratos_referencia=1, tabela_custo_mensal=tabela)

    assert "custo_mensal" not in sem_custo.columns
    assert com_custo.loc["2025-06-30", "custo_mensal"] == pytest.approx(100.0)
    assert com_custo.loc["2025-06-30", "liquido"] == pytest.approx(
        sem_custo.loc["2025-06-30", "liquido"] - 100.0
    )


def test_aplicar_custo_mensal_todos_os_meses_recebem_debito():
    diario = _diario()
    tabela = TabelaCustoMensal(faixas=(FaixaCustoMensal(1, None, 50.0),))
    ajustado = aplicar_custo_mensal(diario, tabela, contratos_referencia=1)

    n_meses = diario.index.to_period("M").nunique()
    assert (ajustado["custo_mensal"] > 0).sum() == n_meses
    assert ajustado["custo_mensal"].sum() == pytest.approx(50.0 * n_meses)
