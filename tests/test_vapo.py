"""
RED: tradefolio.vapo ainda não existe (AGENTS.md épico 7, tarefas
7.1/7.3 -- política de piso fixo e o motor mensal de vapo).

Escopo desta fatia (as únicas partes do épico 7 com fórmula concreta e
sem ambiguidade, uma vez resolvido o modelo abaixo -- o resto de 7.2 fica
de fora, ver módulo/TASKS.md): `PoliticaVapo` (ABC, mesmo padrão de
`tradefolio.importers.OrderImporter`) + `PoliticaPisoFixo` + o motor
`gerar_serie_vapo`.

Modelo do motor (derivado da ordem literal das colunas do PDF-fonte --
"Saldo inicial" carrega de mês para mês, não reseta -- e verificado por
não precisar de nenhuma constante inventada): `saldo` é um total corrente
(como uma equity), e "déficit anterior" é só uma leitura derivada de
`max(0, limiar - saldo_inicial)` para exibição -- não um estado extra
independente. Isso resolve `vapo_bruto = max(0, saldo_antes_do_vapo -
limiar)` sem precisar subtrair o déficit de novo (ele já está embutido em
`saldo_antes_do_vapo`, conferido numericamente abaixo).

Valores conferidos por script contra dados_exemplo/orders_roboraiz.csv
(agregar_mensal sobre a série TOTAL, mesma escala de limiar/RLT já
resolvida nesta sessão), limiar=13.500,00, aliquota_fiscal=0, saldo
inicial=0: 44 meses, o robô só ultrapassa o limiar em 2026-03 (primeiro
vapo=388,50, saldo_final=13.500,00); 2026-05 é um mês perdedor que
reabre déficit (saldo_final=12.932,50); total de vapo bruto no período =
4.452,00 em 5 meses com vapo > 0, maior vapo = 2.335,00 (2026-09).
"""
import warnings

import pandas as pd
import pytest

from tradefolio.alignment import preencher_calendario_b3
from tradefolio.daily import agregar_diario
from tradefolio.loaders import carregar_ordens
from tradefolio.monthly import agregar_mensal
from tradefolio.vapo import (
    PoliticaPisoFixo,
    PoliticaVapo,
    deficit_atual,
    frequencia_meses_com_vapo,
    gerar_serie_vapo,
    maior_sequencia_sem_vapo,
    maior_vapo,
    meses_positivos_sem_vapo_por_deficit,
    vlt_acumulado,
    vlt_mensal,
)

CSV = "dados_exemplo/orders_roboraiz.csv"
LIMIAR = 13500.0


def _mensal_roboraiz():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ordens = carregar_ordens(CSV)
    diario = preencher_calendario_b3(agregar_diario(ordens, contratos_referencia=1))
    return agregar_mensal(diario)


def test_politica_vapo_e_abstrata():
    with pytest.raises(TypeError):
        PoliticaVapo()


def test_politica_piso_fixo_excedente_simples():
    politica = PoliticaPisoFixo()
    assert politica.calcular_vapo_bruto(saldo_antes_do_vapo=12000, limiar=10000, deficit_anterior=0) == 2000
    assert politica.calcular_vapo_bruto(saldo_antes_do_vapo=8000, limiar=10000, deficit_anterior=2000) == 0


def test_gerar_serie_vapo_robo_raiz_real():
    mensal = _mensal_roboraiz()
    serie = gerar_serie_vapo(mensal, limiar=LIMIAR, politica=PoliticaPisoFixo())

    assert len(serie) == 44

    primeiro = serie.loc["2023-02"]
    assert primeiro["saldo_inicial"] == pytest.approx(0.0)
    assert primeiro["deficit_anterior"] == pytest.approx(13500.0)
    assert primeiro["vapo_bruto"] == pytest.approx(0.0)
    assert primeiro["saldo_final"] == pytest.approx(792.5)

    mes_perdedor_antes_do_piso = serie.loc["2023-08"]
    assert mes_perdedor_antes_do_piso["pnl_liquido"] == pytest.approx(-635.0)
    assert mes_perdedor_antes_do_piso["vapo_bruto"] == pytest.approx(0.0)
    assert mes_perdedor_antes_do_piso["saldo_final"] == pytest.approx(1883.5)

    primeiro_vapo = serie.loc["2026-03"]
    assert primeiro_vapo["vapo_bruto"] == pytest.approx(388.5)
    assert primeiro_vapo["saldo_final"] == pytest.approx(13500.0)

    mes_perdedor_depois_do_piso = serie.loc["2026-05"]
    assert mes_perdedor_depois_do_piso["deficit_anterior"] == pytest.approx(0.0)
    assert mes_perdedor_depois_do_piso["vapo_bruto"] == pytest.approx(0.0)
    assert mes_perdedor_depois_do_piso["saldo_final"] == pytest.approx(12932.5)

    mes_recuperacao = serie.loc["2026-06"]
    assert mes_recuperacao["deficit_anterior"] == pytest.approx(567.5)
    assert mes_recuperacao["vapo_bruto"] == pytest.approx(0.0)

    ultimo = serie.loc["2026-09"]
    assert ultimo["vapo_bruto"] == pytest.approx(2335.0)
    assert ultimo["saldo_final"] == pytest.approx(13500.0)

    assert serie["vapo_bruto"].sum() == pytest.approx(4452.0)
    assert (serie["vapo_bruto"] > 0).sum() == 5
    assert serie["vapo_bruto"].max() == pytest.approx(2335.0)


def test_gerar_serie_vapo_com_provisao_fiscal():
    mensal = pd.DataFrame(
        {"bruto": [2000.0], "custo": [0.0], "liquido": [2000.0]},
        index=pd.PeriodIndex(["2025-01"], freq="M", name="mes"),
    )
    serie = gerar_serie_vapo(mensal, limiar=1000.0, politica=PoliticaPisoFixo(), aliquota_fiscal=0.20)

    linha = serie.loc["2025-01"]
    assert linha["vapo_bruto"] == pytest.approx(1000.0)
    assert linha["provisao_fiscal"] == pytest.approx(200.0)
    assert linha["vapo_liquido"] == pytest.approx(800.0)
    # saldo_final desconta o BRUTO (a provisão fiscal é reportada, não
    # permanece na conta de trading) -- não o líquido.
    assert linha["saldo_final"] == pytest.approx(1000.0)


def test_metricas_do_vapo_robo_raiz_real():
    """AGENTS.md épico 7.4 -- VLT reusa limiar.rlt_acumulado/rlt_mensal
    (mesma fórmula genérica valor/limiar, AGENTS.md §8.1); frequência
    reusa metrics.taxa_positivos; maior sequência sem vapo reusa a nova
    metrics.maior_sequencia_mascara (extraída de maior_sequencia nesta
    mesma leva). Valores conferidos por script contra
    dados_exemplo/orders_roboraiz.csv, limiar=13.500,00."""
    mensal = _mensal_roboraiz()
    serie = gerar_serie_vapo(mensal, limiar=LIMIAR, politica=PoliticaPisoFixo())
    vapo_liquido = serie["vapo_liquido"]

    assert vlt_acumulado(vapo_liquido, LIMIAR) == pytest.approx(0.329778, rel=1e-5)
    assert vlt_mensal(vapo_liquido, LIMIAR).mean() == pytest.approx(0.007495, rel=1e-4)
    assert frequencia_meses_com_vapo(vapo_liquido) == pytest.approx(0.113636, rel=1e-5)
    assert maior_vapo(vapo_liquido) == pytest.approx(2335.0)
    assert maior_sequencia_sem_vapo(vapo_liquido) == 37
    assert meses_positivos_sem_vapo_por_deficit(serie) == 28
    assert deficit_atual(serie["saldo_final"], LIMIAR) == pytest.approx(0.0)


def test_deficit_atual_quando_serie_termina_abaixo_do_limiar():
    saldo_final = pd.Series([500.0, 800.0])
    assert deficit_atual(saldo_final, limiar=1000.0) == pytest.approx(200.0)


def test_gerar_serie_vapo_saldo_inicial_customizado():
    mensal = pd.DataFrame(
        {"bruto": [0.0], "custo": [0.0], "liquido": [0.0]},
        index=pd.PeriodIndex(["2025-01"], freq="M", name="mes"),
    )
    serie = gerar_serie_vapo(mensal, limiar=1000.0, politica=PoliticaPisoFixo(), saldo_inicial=1500.0)
    linha = serie.loc["2025-01"]
    assert linha["saldo_inicial"] == pytest.approx(1500.0)
    assert linha["deficit_anterior"] == pytest.approx(0.0)
    assert linha["vapo_bruto"] == pytest.approx(500.0)
