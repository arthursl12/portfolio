"""
RED: tradefolio.metric_registry ainda não existe.

Convenção testada (AGENTS.md épico 0, tarefas 0.1 "dicionário oficial de
métricas" e 0.2 "separar tipos de informação"): todo dict retornado por
calcular_pagina1/2/3 deve ter, para cada chave que não seja um artefato de
dado bruto documentado, uma entrada em tradefolio.metric_registry.REGISTRO
com formula/frequência/unidade/origem/versão/campos necessários/tratamento
de dado ausente/tratamento de custos/interpretação/limitações -- é isso
que torna "nenhuma métrica pode existir apenas no componente visual" (tarefa
0.1) um invariante testado, não uma promessa em prosa.
"""
from pathlib import Path

import pytest

from tradefolio.loaders import carregar_ordens
from tradefolio.metric_registry import ARTEFATOS_DE_DADOS_EXCLUIDOS, ORIGENS_VALIDAS, REGISTRO
from tradefolio.report_data import (
    calcular_pagina1,
    calcular_pagina2,
    calcular_pagina3,
    montar_dataframe_diario,
)
from tradefolio.versions import VERSOES

FIXTURE = Path(__file__).parent / "fixtures" / "mini_fixture_orders.csv"

ARTEFATOS_ESPERADOS = frozenset(
    {"trades", "episodios_drawdown", "piores_tuw", "serie", "piores_5", "melhores_5"}
)


@pytest.fixture
def diario():
    return montar_dataframe_diario(FIXTURE)


@pytest.fixture
def ordens():
    return carregar_ordens(FIXTURE)


def test_artefatos_excluidos_sao_exatamente_os_documentados():
    assert ARTEFATOS_DE_DADOS_EXCLUIDOS == ARTEFATOS_ESPERADOS


def test_toda_chave_de_pagina1_tem_entrada_no_registro(diario):
    metricas, _, _ = calcular_pagina1(diario)
    faltando = [k for k in metricas if k not in REGISTRO and k not in ARTEFATOS_DE_DADOS_EXCLUIDOS]
    assert faltando == []


def test_toda_chave_de_pagina2_tem_entrada_no_registro_ou_e_artefato_documentado(diario, ordens):
    p2 = calcular_pagina2(diario, ordens)
    faltando = [k for k in p2 if k not in REGISTRO and k not in ARTEFATOS_DE_DADOS_EXCLUIDOS]
    assert faltando == []


def test_toda_chave_de_pagina3_tem_entrada_no_registro_ou_e_artefato_documentado(diario):
    p3 = calcular_pagina3(diario)
    faltando = [k for k in p3 if k not in REGISTRO and k not in ARTEFATOS_DE_DADOS_EXCLUIDOS]
    assert faltando == []


def test_cada_entrada_do_registro_tem_todos_os_campos_preenchidos():
    for metric_id, spec in REGISTRO.items():
        assert spec.id == metric_id
        assert spec.nome
        assert spec.pagina in (1, 2, 3)
        assert spec.formula
        assert spec.frequencia
        assert spec.unidade
        assert spec.origem
        assert spec.versao_etapa
        assert spec.campos_necessarios
        assert spec.tratamento_dado_ausente
        assert spec.tratamento_custos
        assert spec.interpretacao
        assert spec.limitacoes


def test_origem_de_cada_entrada_e_uma_das_categorias_validas():
    for spec in REGISTRO.values():
        assert spec.origem in ORIGENS_VALIDAS


def test_versao_etapa_de_cada_entrada_referencia_uma_etapa_ja_implementada():
    # tarefa 0.3: toda métrica já implementada precisa apontar para uma
    # etapa que tenha, ela mesma, uma versão concreta (não None) em
    # tradefolio.versions -- senão o vínculo formula-backend <-> versão
    # documentada (critério de aceite da tarefa 0.1) fica quebrado.
    for spec in REGISTRO.values():
        assert spec.versao_etapa in VERSOES
        assert VERSOES[spec.versao_etapa] is not None
