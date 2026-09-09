# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

This is a trading-robot / portfolio performance analysis tool (in Portuguese). It parses order-execution
CSVs (Smarttbot export format), builds a daily P&L series aligned to the B3 trading calendar, computes
performance metrics (drawdown, Ulcer Index, Sharpe/Sortino/Calmar, VaR/Expected Shortfall, trade
sequences), and renders a single-page HTML report ("lâmina") with embedded matplotlib charts.

**Current state vs. `AGENTS.md`'s target architecture:** `AGENTS.md` (see below) describes a target
modular layout under `src/tradefolio/` (validation.py, metrics.py, drawdowns.py, costs.py, etc.) with a
pytest suite and ruff. None of that exists yet — the repository currently has only two flat scripts:

- `sheet.py` — all calculation logic: CSV parsing (`carregar_ordens`), daily aggregation against the B3
  calendar via `pandas_market_calendars` (`montar_dataframe_diario`), and the three metric blocks
  (`calcular_metricas_pagina1/2/3`: summary, drawdown/sequences, distribution/tail risk).
- `report.py` — renders `sheet.py`'s output into a self-contained HTML report (base64-embedded PNG
  charts from matplotlib, inline CSS).

There is no `requirements.txt`/`pyproject.toml`, no README, and no test suite yet. When adding tests or
splitting logic into modules, follow the `src/tradefolio/...` responsibility split in `AGENTS.md` §16
rather than inventing a different layout.

**Known gap:** `report.py` imports from a module named `lamina_fase1`, but no such file exists — the
actual module with those names (`montar_dataframe_diario`, `calcular_metricas_pagina1/2/3`,
`carregar_ordens`, `CSV_PATH`) is `sheet.py`. Running `report.py` as-is currently fails with
`ModuleNotFoundError` until this is reconciled (rename vs. fix import is a decision for whoever picks up
that task — don't silently choose one).

## Governing workflow: `AGENTS.md`

`AGENTS.md` in the repo root is the mandatory workflow document for this project and takes priority over
general engineering habits (see its §2 instruction-priority order). Read it in full before doing
non-trivial work here. Highlights that matter most:

- **TDD is mandatory** for any change touching financial calculations, portfolio logic, costs, data
  validation, simulation, or optimization: RED (failing test first) → confirm it fails for the right
  reason → GREEN (minimal implementation) → run focused then full suite → REFACTOR only if useful. See
  §3–§4 for the full cycle and the required RED/GREEN/REFACTOR completion-report format (§22).
- **Never invent financial conventions.** Formulas for payoff, expectancy, profit factor, drawdown,
  Ulcer Index, annualized ratios, VaR/ES, etc. must follow §8's explicit definitions unless a task states
  otherwise, and any deviation must be documented (units, sign convention, annualization factor,
  missing-data behavior).
- **Never invent a cost/tariff value** (§11) or silently fill missing robot observations with zero (§10)
  — missing data, a valid zero-result day, and a non-trading day are three different things.
- **Scope discipline** (§5): change only files required by the task, no opportunistic cleanup/renaming,
  no dependency changes without justification (§18).
- **Never modify the Streamlit interface when implementing core calculations** unless explicitly asked,
  and never put core formulas in `app.py`/presentation code (§16–§17) — this matters once a UI layer is
  added.
- **Test integrity** (§6): never weaken assertions, delete/skip a failing test, mock the function under
  test, or loosen tolerances to make something pass.
- **Do not create git commits** unless explicitly instructed (§21).
- **Stop and ask** rather than guess when a financial convention, cost rule, or optimization objective is
  ambiguous (§24) — this repo treats "plausible but wrong" financial output as the primary risk, not
  crashes.

## Domain conventions actually implemented in `sheet.py` (worth knowing before changing it)

- All per-day/per-trade currency figures are normalized **per contract**, dividing by
  `CONTRATOS_REFERENCIA = 2` (the backtest's reference position size) — `AGENTS.md` §9 flags composite
  units and non-linear scaling as things to never assume, so don't generalize this constant without
  checking.
- B3 cost model: flat `CUSTO_POR_CONTRATO_PERNA = 0.25` (R$) applied per executed contract, per leg
  (entry AND exit), not just on exit.
- Daily series is reindexed onto the B3 trading calendar (`pandas_market_calendars.get_calendar("B3")`);
  days with no trade are filled with 0, and a boolean `operou` column distinguishes "no trade" from
  "traded" days.
- Trades are reconstructed from net position changes (`reconstruir_trades` in `sheet.py`), grouping
  partial fills between the position leaving zero and returning to zero — not a 1:1 mapping to raw order
  rows.
- Equity-based drawdown % and Ulcer Index % use an assumed starting balance of
  `CAPITAL_POR_CONTRATO = R$1000`/contract (documented in `sheet.py` as matching Smarttbot's convention),
  separate from the raw R$ drawdown series.
- Sharpe/Sortino annualize with `DIAS_UTEIS_ANO = 252`.
- I/O paths are currently hardcoded (`CSV_PATH` in `sheet.py`, the output path in `report.py`'s
  `__main__` block) to `/mnt/user-data/...` — a Claude-analysis-environment convention, not a
  general-purpose path. Treat as needing parameterization if this becomes a reusable tool.

## Commands

No dependency manifest exists yet. The code imports `pandas`, `numpy`, `matplotlib`, and
`pandas_market_calendars` — install what's missing before running.

Running the scripts directly (note the `lamina_fase1` import gap above must be resolved first for
`report.py`):

```bash
python sheet.py     # prints computed metrics to stdout
python report.py     # writes the HTML lâmina report (currently broken — see Known gap)
```

`AGENTS.md` §20 gives the intended test/lint commands for once a test suite and `src/tradefolio/`
package exist:

```bash
python -m pytest
python -m pytest tests/test_metrics.py -v
python -m pytest --cov=tradefolio --cov-report=term-missing
ruff check .
ruff format --check .
```

Do not claim any command succeeded without actually having run it in this environment (`AGENTS.md` §20).

## Domain conventions validated against the Smarttbot platform

The conventions below were derived and cross-checked, exchange by exchange,
against the Smarttbot platform's own report during exploratory analysis of
the "Romanos" robot (pessimistic simulator). They are not arbitrary
implementation choices — they were picked specifically because they reproduce
the platform's numbers. Treat them as the documented convention required by
`AGENTS.md` section 8, not as something to re-derive from first principles.
See `tests/fixtures/romanos_expected.md` for the full reconciliation.

### CSV format (Smarttbot order export)

- Semicolon-separated, `;` delimiter, comma as decimal separator
  (`"1.234,56"`), dot as thousands separator. `Data/Hora` format:
  `dd/mm/yyyy / HH:MM:SS`.
- The file is **order-level, not trade-level**: every closed position
  produces one `entrada` row (no result) and one or more `saída` rows
  (carrying `Resultado (R$)`). A `saída` can be split into multiple partial
  fills (observed at end-of-day forced closes), so **do not count `saída`
  rows as trades** — reconstruct trades from net position (see below).
- `Ativo` changes over time due to futures contract roll (e.g. `WINV25` →
  `WINZ25`) — treat this as a continuous series, not a break.

### Trade reconstruction

A trade is not one row and not one `saída` row — it is the span from when
net position leaves zero to when it returns to zero. Reconstruct by walking
orders in chronological order, tracking net position (`+qty` on `C`, `-qty`
on `V`), and summing every `saída` leg's `Resultado (R$)` encountered while
position stays open. This is required to get correct Profit Factor, win
rate, and win/loss streaks — counting raw `saída` rows overstates trade
count whenever a position closes via multiple partial fills.

### Costs (B3 emolumentos)

- **R$0.25 per contract, per leg** (entry and exit are each charged
  separately) → **R$0.50 per contract on a full round trip**.
- Apply the cost to **every order row** (both `entrada` and `saída`), not
  only to `saída` rows, since both legs of a round trip incur the fee.
- No brokerage commission on this platform (user-confirmed) — B3 emolumento
  is the only cost component.

### Reference capital / percentage basis

Smarttbot's own report uses **R$1,000.00 per contract** (the margin
suggested by the robot's author) as the "saldo inicial" for percentage-based
figures. This is not a real account balance, just the denominator used for
%-scaled metrics:

- `patrimonio_t = R$1,000 × contratos + resultado_liquido_acumulado_t`
- **Return % (bruto/líquido)**: divide by the **fixed** initial capital
  (`R$1,000 × contratos`).
- **Drawdown % and Ulcer Index %**: divide by the **moving peak** of
  `patrimonio`, not the fixed initial capital — this is what reproduces the
  platform's reported drawdown % exactly. Confirmed: our max drawdown % of
  35.36% matches the Smarttbot report exactly using this method.
- **Basis consistency matters more than which basis you pick**, since drawdown %/Ulcer % are
  scale-invariant ratios: `1,000 × contratos` applied to the *total* accumulated result and a fixed
  `1,000` applied to the *per-contract* accumulated result give identical %s (verified algebraically
  and by cross-checking `tradefolio.drawdowns` against `tests/fixtures/romanos_orders.csv` — both
  reproduce 35.36% exactly). `tradefolio.drawdowns` works entirely on the per-contract basis (matching
  `liquido_por_contrato` elsewhere in the codebase), so it uses the fixed `R$1,000` form — mixing a
  total-account capital with a per-contract equity series (or vice versa) breaks the ratio and was the
  one wrong intermediate result hit while building it.
- Sharpe and Sortino are scale-invariant (mean/std ratio), so they come out
  identical whether computed on raw R$ or on %-of-capital daily results —
  no special handling needed there.

### Trade-level vs. day-level metrics (see AGENTS.md §8.1 — this confirms it)

- **Trade-level** (net of per-trade cost): Profit Factor, win rate, average
  win/loss, winning/losing streaks (length **and** R$ total — a streak of N
  trades worth R$50 is a different animal from one worth R$5,000, report
  both). Multiple trades in one day are independent bets on the strategy's
  edge and should not be netted together before classifying win/loss.
- **Day-level** (net of same-day aggregated cost): equity curve, drawdown,
  drawdown episodes (peak/trough/recovery dates), Time Under Water, Ulcer
  Index, Sharpe/Sortino/Calmar. Same-day trades are not independent from a
  risk standpoint — they can share the same market-regime shock — so risk
  metrics must be computed on the daily-aggregated series, never per trade.
- Never silently pick one when a metric name is ambiguous (e.g.
  "expectância", "sequência") — label which basis was used, exactly as
  AGENTS.md §8 requires.

### Trading calendar

Use `pandas_market_calendars`, calendar name `'B3'`, to generate the full
set of trading sessions between the first and last date **present in the
data** (not into the future) and reindex the daily series onto it, filling
missing days with 0 and flagging them (`operou=False`) so "no trade that
day" is distinguishable from "no data for that day" (AGENTS.md §14/§15 —
missing data must never collapse silently into zero-activity).

