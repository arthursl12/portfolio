"""
RED: tradefolio.versions ainda não existe.

Convenção testada (AGENTS.md épico 0, tarefa 0.3 "versionar a
metodologia"): cada etapa do pipeline que já existe tem uma tag de versão
própria (para poder ser referenciada por tradefolio.metric_registry e,
futuramente, pela camada de proveniência exposta à IA). Etapas que ainda
não existem (portfólio, score, alertas) ficam explicitamente None --
não recebem uma versão inventada só para preencher a tabela.
"""
from tradefolio.versions import VERSOES

ETAPAS_IMPLEMENTADAS = (
    "parser_ordens",
    "validacao",
    "agregacao_diaria",
    "calendario_b3",
    "consolidacao_mensal",
    "reconstrucao_trades",
    "custos",
    "custo_mensal",
    "metricas",
    "drawdowns",
    "limiar",
    "concentracao",
    "vapo",
    "monte_carlo",
    "deterioracao",
)

ETAPAS_NAO_IMPLEMENTADAS = (
    "portfolio",
    "score",
    "alertas",
)


def test_etapas_implementadas_tem_versao_nao_vazia():
    for etapa in ETAPAS_IMPLEMENTADAS:
        assert etapa in VERSOES
        assert isinstance(VERSOES[etapa], str) and VERSOES[etapa]


def test_etapas_nao_implementadas_ficam_explicitamente_none():
    for etapa in ETAPAS_NAO_IMPLEMENTADAS:
        assert etapa in VERSOES
        assert VERSOES[etapa] is None


def test_nao_ha_etapas_nao_documentadas():
    assert set(VERSOES) == set(ETAPAS_IMPLEMENTADAS) | set(ETAPAS_NAO_IMPLEMENTADAS)
