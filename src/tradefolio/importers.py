"""Common order-import interface (AGENTS.md épico 1, tarefa 1.2).

Today there is exactly one format (Smarttbot) and one implementation,
`SmarttbotOrderImporter`, which wraps the already-existing
`loaders.carregar_ordens`/`validation.diagnostico_ingestao` -- it does not
duplicate or reimplement any parsing/validation logic. The interface
exists so a future importer (a generic CSV shape, a manual/standardized
format) can be added without report_data or any other caller needing to
know which format produced a given `ordens` DataFrame, as long as it has
the same columns `tradefolio.validation.COLUNAS_OBRIGATORIAS` requires.

Deliberately NOT implemented here (AGENTS.md §8: never invent a format
that doesn't exist to fill out a checklist):
- A generic-CSV or manual-standardized-format importer -- tarefa 1.2 asks
  for these but specifies no concrete shape for either; there is nothing
  to implement without guessing a format.
- The "reimporting a file doesn't duplicate orders" acceptance criterion
  -- that needs a notion of "already imported before" across separate
  runs, which is Épico 1.4 (persistence), still without a decided tech
  stack. `#` already gives a stable id *within* one file (used by
  `validation.validar_ordens_parseadas`'s DUPLICATE_ORDER check); cross-run
  dedup needs somewhere durable to remember what was seen before.
"""
from abc import ABC, abstractmethod

import pandas as pd

from tradefolio.loaders import carregar_ordens, detectar_delimitador, ler_primeira_linha
from tradefolio.validation import COLUNAS_OBRIGATORIAS, diagnostico_ingestao


class OrderImporter(ABC):
    """Common interface every order source implements: whether it can
    handle a given file, how to parse it into the standard `ordens`
    DataFrame shape, and how to summarize ingestion quality for it."""

    @abstractmethod
    def can_parse(self, csv_path) -> bool:
        """Cheap check (header only, not a full parse/validate) of
        whether this importer can handle `csv_path`."""

    @abstractmethod
    def parse(self, csv_path) -> pd.DataFrame:
        """Full parse + validation, same `ordens` DataFrame shape
        `tradefolio.loaders.carregar_ordens` already produces."""

    @abstractmethod
    def diagnostics(self, ordens: pd.DataFrame) -> dict:
        """Aggregate ingestion-quality summary for an already-parsed
        `ordens` DataFrame (AGENTS.md épico 1, tarefa 1.3)."""


class SmarttbotOrderImporter(OrderImporter):
    """Wraps the existing Smarttbot-specific parser/diagnostics -- no new
    parsing logic, just the common interface over what already exists."""

    def can_parse(self, csv_path) -> bool:
        try:
            delimitador = detectar_delimitador(csv_path)
            primeira_linha = ler_primeira_linha(csv_path)
        except OSError:
            return False
        colunas = {c.strip() for c in primeira_linha.strip().split(delimitador)}
        return set(COLUNAS_OBRIGATORIAS).issubset(colunas)

    def parse(self, csv_path) -> pd.DataFrame:
        return carregar_ordens(csv_path)

    def diagnostics(self, ordens: pd.DataFrame) -> dict:
        return diagnostico_ingestao(ordens)
