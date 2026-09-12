"""
RED: tradefolio.daily.pivotar_liquido_por_ativo ainda não existe (AGENTS.md
épico 3.1/12 -- base para MDD e correlação por ativo na lâmina).

Reshape largo de agregar_diario_por_ativo['liquido'] (colunas = ativo_raiz),
reindexado no calendário B3 completo (mesmo range que a agregação
principal usaria) e 0-preenchido tanto para sessões sem NENHUMA ordem
(reindex) quanto para um (data, ativo) sem ordem DENTRO do range (fillna
-- unstack por si só deixaria NaN aqui, ex. WIN não operou no primeiro
dia do CSV, só WDO operou).

Valores conferidos por script contra dados_exemplo/orders_roboraiz.csv
antes deste teste: soma WIN=15.648,50 / WDO=2.303,50 (batem com
lucro_por_ativo já verificado nesta sessão), 890 pregões no range
completo, primeiro dia (2023-02-13) tem WDO=-631,00 e WIN=0,00 (WIN não
operou nesse dia).
"""
import warnings

import pandas as pd
import pytest

from tradefolio.daily import pivotar_liquido_por_ativo
from tradefolio.loaders import carregar_ordens

CSV = "dados_exemplo/orders_roboraiz.csv"


def _ordens():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return carregar_ordens(CSV)


def test_pivotar_liquido_por_ativo_colunas_e_totais():
    largo = pivotar_liquido_por_ativo(_ordens())
    assert set(largo.columns) == {"WIN", "WDO"}
    assert largo["WIN"].sum() == pytest.approx(15648.50)
    assert largo["WDO"].sum() == pytest.approx(2303.50)


def test_pivotar_liquido_por_ativo_reindexado_no_calendario_completo():
    largo = pivotar_liquido_por_ativo(_ordens())
    assert len(largo) == 890
    assert largo.index.min() == pd.Timestamp("2023-02-13")
    assert largo.index.max() == pd.Timestamp("2026-09-08")


def test_pivotar_liquido_por_ativo_preenche_zero_para_ativo_sem_ordem_no_dia():
    largo = pivotar_liquido_por_ativo(_ordens())
    # 13/02/2023: só WDO operou (WIN entra depois no historico)
    assert largo.loc["2023-02-13", "WDO"] == pytest.approx(-631.00)
    assert largo.loc["2023-02-13", "WIN"] == pytest.approx(0.0)
    assert not largo.isna().any().any()


def test_pivotar_liquido_por_ativo_um_unico_ativo():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ordens = carregar_ordens("tests/fixtures/romanos_orders.csv")
    largo = pivotar_liquido_por_ativo(ordens)
    assert list(largo.columns) == ["WIN"]
