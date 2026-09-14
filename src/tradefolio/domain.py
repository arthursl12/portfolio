"""Thin metadata/domain layer (AGENTS.md épico 2).

Describes WHICH strategy, WHICH configuration, WHEN a configuration was
valid, and WHAT happened in one analysis run. Does NOT replace the
existing functional DataFrame pipeline (daily.py, metrics.py, drawdowns.py,
...) -- those stay exactly as they are. A caller populates these from
pipeline outputs; they never compute anything themselves (pure data
holders, dataclasses over Pydantic since nothing here needs runtime
validation beyond what tradefolio.validation already does upstream).

Deliberately NOT implemented yet (AGENTS.md §8: never invent a convention
for a system that doesn't exist):
- StrategyVersion -- nothing tracks code-level version changes yet.
- Order/DailyResult/MonthlyResult -- already well-represented by the
  existing DataFrames (tradefolio.loaders/daily/monthly); wrapping them now
  would duplicate data with no new capability.
- ThresholdPolicy/WithdrawalPolicy -- tradefolio.limiar/tradefolio.vapo
  implement the actual formulas (épicos 6/7); no dataclass wraps a
  chosen policy as a named, storable record yet.
- Portfolio -- tradefolio.portfolio (épico 10) has the functional
  pipeline (sincronizar_portfolio, limiar_agregado_portfolio, etc.); no
  dataclass records "which robots, at which weights" as a named,
  storable portfolio yet (PortfolioAllocation below records one robot's
  allocation, not the whole named collection).
- SimulationRun -- tradefolio.monte_carlo (épico 8) has the functional
  pipeline; no dataclass records "which simulation, with which
  parameters" as a stored/citable run yet.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from tradefolio.daily import contratos_referencia_por_ativo


@dataclass(frozen=True)
class PositionLeg:
    ativo_raiz: str
    quantidade: int


@dataclass(frozen=True)
class Strategy:
    id: str
    nome: str


@dataclass(frozen=True)
class StrategyConfiguration:
    """AGENTS.md épico 2, tarefas 2.2/2.3: uma alteração de contratos não
    é necessariamente uma nova versão da estratégia, mas precisa de uma
    nova configuração temporal (`valid_from`/`valid_to`). `legs` (uma por
    ativo_raiz) generaliza o `contratos_referencia` escalar de
    tradefolio.daily para robôs multi-ativo."""

    strategy_id: str
    legs: tuple[PositionLeg, ...]
    minimum_margin: float | None
    valid_from: date
    valid_to: date | None
    recorded_at: str
    source: str

    @property
    def contratos_totais(self) -> int:
        return sum(leg.quantidade for leg in self.legs)


def configuracao_a_partir_da_deteccao(
    strategy_id: str,
    ordens: pd.DataFrame,
    valid_from: date,
    minimum_margin: float | None = None,
    valid_to: date | None = None,
    recorded_at: str = "",
    source: str = "daily.detectar_contratos_referencia",
    dias_recentes: int | None = None,
) -> StrategyConfiguration:
    """Popula uma StrategyConfiguration chamando
    `tradefolio.daily.contratos_referencia_por_ativo` -- POR PERNA
    (ativo_raiz), não sobre o CSV inteiro: um robô multi-ativo pode ter
    uma perna com quantidade estável e outra sem, e a detecção agregada
    across pernas misturaria as duas distribuições sem sentido. Se
    qualquer perna não tiver uma quantidade dominante (robô mudou de
    tamanho de posição naquela perna ao longo do período), o ValueError
    original de `detectar_contratos_referencia` se propaga -- uma única
    configuração para todo o período genuinamente não descreve esse robô.

    `dias_recentes` (opcional): restringe a detecção aos últimos N dias
    -- útil quando a proporção mudou historicamente (ex. Robô Raiz, "1
    WDO para 2 WDO") e só a configuração ATUAL importa. Ver docstring de
    `contratos_referencia_por_ativo` para a mesma ressalva: isso assume
    a proporção recente é a vigente, não segmenta a história inteira em
    múltiplas configurações."""
    por_ativo = contratos_referencia_por_ativo(ordens, dias_recentes)
    legs = tuple(
        PositionLeg(ativo_raiz=raiz, quantidade=quantidade)
        for raiz, quantidade in sorted(por_ativo.items())
    )
    if dias_recentes is not None:
        source = f"{source} (últimos {dias_recentes} dias)"

    return StrategyConfiguration(
        strategy_id=strategy_id,
        legs=legs,
        minimum_margin=minimum_margin,
        valid_from=valid_from,
        valid_to=valid_to,
        recorded_at=recorded_at,
        source=source,
    )


@dataclass(frozen=True)
class DataQualityIssue:
    """Espelha ErroValidacao/AvisoValidacao (tradefolio.validation) como um
    registro sem depender do mecanismo de warnings/exceptions do Python --
    útil para acumular numa AnalysisRun."""

    codigo: str | None
    mensagem: str
    severidade: str  # "error" | "warning"


@dataclass(frozen=True)
class AnalysisRun:
    """Um registro de uma execução do pipeline: qual arquivo, quando, com
    quais versões de cada etapa (tradefolio.versions.VERSOES) e quais
    problemas de qualidade de dado foram observados."""

    strategy_id: str
    source_file: str
    executed_at: str
    versoes: dict
    issues: tuple[DataQualityIssue, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MetricResult:
    """Uma métrica calculada, com proveniência -- o par (metric_id, value)
    de tradefolio.metric_registry.MetricSpec, mas para um valor concreto
    em vez da especificação da métrica."""

    metric_id: str
    value: float
    origem: str
    analysis_run_id: str | None = None


@dataclass(frozen=True)
class PortfolioAllocation:
    """Um robô dentro de um portfólio (AGENTS.md épico 10, tarefa 10.2):
    quanto dele (`multiplier`, escala o `liquido` -- ver
    `tradefolio.portfolio.sincronizar_portfolio`) e desde quando. Registra
    UMA alocação; um portfólio nomeado (a coleção inteira) ainda não tem
    dataclass própria (ver docstring do módulo)."""

    strategy_id: str
    multiplier: float
    active_from: date
