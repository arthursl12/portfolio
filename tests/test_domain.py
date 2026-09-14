"""
RED: tradefolio.domain ainda não existe (AGENTS.md épico 2 -- camada fina
de metadados/domínio, aditiva sobre o pipeline funcional existente:
daily.py/metrics.py/drawdowns.py/etc. continuam exatamente como estão).

Escopo desta primeira versão (decidido com o usuário): Strategy,
StrategyConfiguration (+ PositionLeg), AnalysisRun, DataQualityIssue,
MetricResult. Deliberadamente NÃO implementados agora (documentado em
domain.py, não omitido silenciosamente): StrategyVersion (nada rastreia
mudança de versão de código ainda), Order/DailyResult/MonthlyResult (já
bem representados pelos DataFrames existentes -- envolvê-los agora só
duplicaria dado sem nova capacidade), ThresholdPolicy/WithdrawalPolicy
(Épicos 6/7 não existem), Portfolio/PortfolioAllocation (Épico 10 não
existe), SimulationRun (Épico 8 não existe).

`configuracao_a_partir_da_deteccao` liga StrategyConfiguration a
daily.detectar_contratos_referencia (épico 2.2 pede exatamente isso, não
recalcular do zero) -- rodado POR PERNA (ativo_raiz), não sobre o CSV
inteiro: um robô multi-ativo pode ter uma raiz com quantidade estável e
outra sem (WIN e WDO não mudam de tamanho necessariamente ao mesmo tempo).

Descoberta ao testar contra dados_exemplo/orders_roboraiz.csv: mesmo por
perna, WDO não tem quantidade dominante (79,4%, abaixo dos 90% de
FRACAO_MINIMA_DOMINANTE) -- esse robô mudou de tamanho de posição ao
longo do tempo (confirmado pela própria "lâmina ideal.pdf": "Alteração de
1 WDO para 2 WDO", "Alteração de 1 WIN para 3 WIN"). Isso é exatamente o
que épico 2.3 (períodos de validade) existe para modelar -- uma única
StrategyConfiguration para o histórico inteiro não cabe nesse robô, e a
função deve propagar o erro em vez de forçar um número, não silenciá-lo.
"""
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from tradefolio.domain import (
    AnalysisRun,
    DataQualityIssue,
    MetricResult,
    PortfolioAllocation,
    PositionLeg,
    Strategy,
    StrategyConfiguration,
    configuracao_a_partir_da_deteccao,
)
from tradefolio.loaders import carregar_ordens

CABECALHO = (
    "#;Data/Hora;Ativo;C/V;Quantidade;Preço limite;Status;Tipo;"
    "Quantidade executada;Preço médio;Resultado (Abs.);Resultado %;Resultado (R$)"
)


def _ordens_win_e_wdo_estaveis(tmp_path: Path) -> pd.DataFrame:
    linhas = [
        '1;02/01/2025 / 09:00:00;WINF25;C;2;140000;executada;entrada;2;140000;-;-;-',
        '2;02/01/2025 / 09:05:00;WINF25;V;2;140100;executada;saída;2;140100;200,00;0,07;200,00',
        '3;02/01/2025 / 10:00:00;WDOF25;C;1;5000;executada;entrada;1;5000;-;-;-',
        '4;02/01/2025 / 10:05:00;WDOF25;V;1;4950;executada;saída;1;4950;-50,00;-1,00;-50,00',
        '5;03/01/2025 / 09:00:00;WINF25;C;2;140000;executada;entrada;2;140000;-;-;-',
        '6;03/01/2025 / 09:05:00;WINF25;V;2;140050;executada;saída;2;140050;100,00;0,04;100,00',
    ]
    caminho = tmp_path / "win_wdo.csv"
    caminho.write_text(CABECALHO + "\n" + "\n".join(linhas) + "\n", encoding="utf-8")
    return carregar_ordens(caminho)


def test_portfolio_allocation_e_container_simples():
    alocacao = PortfolioAllocation(strategy_id="romanos", multiplier=1.5, active_from=date(2026, 1, 1))
    assert alocacao.strategy_id == "romanos"
    assert alocacao.multiplier == 1.5
    assert alocacao.active_from == date(2026, 1, 1)


def test_position_leg_e_strategy_sao_containers_simples():
    perna = PositionLeg(ativo_raiz="WIN", quantidade=2)
    assert perna.ativo_raiz == "WIN"
    assert perna.quantidade == 2

    estrategia = Strategy(id="romanos", nome="Romanos")
    assert estrategia.id == "romanos"


def test_configuracao_a_partir_da_deteccao_multi_ativo_estavel(tmp_path):
    ordens = _ordens_win_e_wdo_estaveis(tmp_path)
    config = configuracao_a_partir_da_deteccao(
        strategy_id="teste", ordens=ordens, valid_from=date(2025, 1, 2), minimum_margin=5000.0,
    )
    assert config.strategy_id == "teste"
    assert config.legs == (
        PositionLeg(ativo_raiz="WDO", quantidade=1),
        PositionLeg(ativo_raiz="WIN", quantidade=2),
    )
    assert config.contratos_totais == 3
    assert config.minimum_margin == 5000.0
    assert config.valid_from == date(2025, 1, 2)
    assert config.valid_to is None


def test_configuracao_a_partir_da_deteccao_dias_recentes_recupera_proporcao_atual():
    # mesmo CSV do teste abaixo (falha sobre o histórico inteiro), mas
    # restringindo aos últimos 90 dias -- recupera a proporção ATUAL
    # (3 WIN + 2 WDO), conferida por script antes deste teste.
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ordens = carregar_ordens("dados_exemplo/orders_roboraiz.csv")

    config = configuracao_a_partir_da_deteccao(
        strategy_id="robo-raiz", ordens=ordens, valid_from=date(2023, 2, 13),
        dias_recentes=90,
    )
    assert config.legs == (
        PositionLeg(ativo_raiz="WDO", quantidade=2),
        PositionLeg(ativo_raiz="WIN", quantidade=3),
    )
    assert config.contratos_totais == 5
    assert "90" in config.source


def test_configuracao_a_partir_da_deteccao_propaga_erro_quando_perna_muda_de_tamanho():
    # dados_exemplo/orders_roboraiz.csv: WDO nao tem quantidade dominante
    # (mudou de tamanho ao longo do historico) -- uma unica configuracao
    # para o periodo inteiro nao cabe, e isso deve ser levantado, nao
    # escondido atras de um numero forcado.
    import warnings

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        ordens = carregar_ordens("dados_exemplo/orders_roboraiz.csv")

    with pytest.raises(ValueError, match="contratos"):
        configuracao_a_partir_da_deteccao(
            strategy_id="robo-raiz", ordens=ordens, valid_from=date(2023, 2, 13),
        )


def test_data_quality_issue_e_container_simples():
    issue = DataQualityIssue(codigo="UNKNOWN_STATUS", mensagem="valor desconhecido", severidade="warning")
    assert issue.severidade == "warning"


def test_analysis_run_guarda_versoes_e_issues():
    from tradefolio.versions import VERSOES

    run = AnalysisRun(
        strategy_id="romanos",
        source_file="tests/fixtures/romanos_orders.csv",
        executed_at="2026-09-12T10:00:00",
        versoes=dict(VERSOES),
        issues=(DataQualityIssue(codigo="EXIT_WITHOUT_PNL", mensagem="26 linhas", severidade="warning"),),
    )
    assert run.versoes["validacao"] == VERSOES["validacao"]
    assert len(run.issues) == 1


def test_metric_result_e_container_simples():
    resultado = MetricResult(metric_id="max_drawdown", value=-177.0, origem="calculated")
    assert resultado.value == -177.0
    assert resultado.origem == "calculated"
