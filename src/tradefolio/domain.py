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
- ThresholdPolicy/WithdrawalPolicy -- Épicos 6/7 don't exist.
- Portfolio/PortfolioAllocation -- Épico 10 doesn't exist.
- SimulationRun -- Épico 8 doesn't exist.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

from tradefolio.daily import detectar_contratos_referencia
from tradefolio.validation import STATUS_EXECUTADA, extrair_raiz_ativo


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
) -> StrategyConfiguration:
    """Popula uma StrategyConfiguration chamando
    tradefolio.daily.detectar_contratos_referencia POR PERNA (ativo_raiz),
    não sobre o CSV inteiro -- um robô multi-ativo pode ter uma perna com
    quantidade estável e outra sem, e a detecção agregada across pernas
    misturaria as duas distribuições sem sentido. Se qualquer perna não
    tiver uma quantidade dominante (robô mudou de tamanho de posição
    naquela perna ao longo do período), o ValueError original de
    detectar_contratos_referencia se propaga -- uma única configuração
    para todo o período genuinamente não descreve esse robô."""
    ordens = ordens.copy()
    ordens["ativo_raiz"] = ordens["Ativo"].map(extrair_raiz_ativo)

    legs = tuple(
        PositionLeg(
            ativo_raiz=raiz,
            quantidade=detectar_contratos_referencia(ordens[ordens["ativo_raiz"] == raiz]),
        )
        for raiz in sorted(ordens["ativo_raiz"].unique())
    )

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
