"""
RED: report_data.calcular_pagina1 ainda não expõe "lucro por ativo"
(AGENTS.md épico 4.1). O dado-base já existe desde o épico 3.1
(daily.agregar_diario_por_ativo), só falta ligar como métrica nomeada.

Parâmetro `ordens` é OPCIONAL e default None -- não muda a assinatura de
forma incompatível (app.py e os testes existentes que chamam
calcular_pagina1(diario) continuam funcionando sem alteração). Quando
`ordens` não é passado, a chave "lucro_por_ativo" simplesmente não
aparece no dict (não dá pra calcular sem as ordens brutas -- diario já
perdeu a granularidade por ativo).

Valores conferidos por script contra dados_exemplo/orders_roboraiz.csv
(WIN + WDO reais) antes deste teste: WDO=2303.50, WIN=15648.50, líquido
em escala bruta (não normalizado por contrato -- Robô Raiz não tem uma
única referência de contratos estável para WDO, ver tarefa 2.2/TASKS.md).
"""
import warnings

import pytest

from tradefolio.loaders import carregar_ordens
from tradefolio.report_data import calcular_pagina1, montar_dataframe_diario

CSV = "dados_exemplo/orders_roboraiz.csv"


def _carregar():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ordens = carregar_ordens(CSV)
        # contratos_referencia explícito: a detecção automática do CSV
        # inteiro genuinamente falha para este robô (WIN+WDO com tamanhos
        # de posição diferentes -- ver tarefa 2.2/TASKS.md), mas é
        # irrelevante aqui: lucro_por_ativo vem direto de `ordens`, em
        # escala bruta, não normalizado por contrato.
        diario = montar_dataframe_diario(CSV, contratos_referencia=1)
    return diario, ordens


def test_lucro_por_ativo_ausente_sem_ordens():
    diario, _ = _carregar()
    metricas, _, _ = calcular_pagina1(diario)
    assert "lucro_por_ativo" not in metricas


def test_lucro_por_ativo_presente_com_ordens():
    diario, ordens = _carregar()
    metricas, _, _ = calcular_pagina1(diario, ordens=ordens)
    assert metricas["lucro_por_ativo"] == pytest.approx(
        {"WDO": 2303.50, "WIN": 15648.50}
    )
