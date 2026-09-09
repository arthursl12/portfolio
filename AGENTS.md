# AGENTS.md

## 1. Purpose

This file defines the mandatory workflow for AI coding agents working in this repository.

The project analyzes trading robots and portfolios using Python. It includes financial metrics, drawdowns, operating costs, position sizing, portfolio aggregation, simulations, optimization, notebooks, and a Streamlit interface.

The primary risk is not an application crash. The primary risk is producing plausible but incorrect financial results. Therefore, correctness, traceability, small changes, and automated tests take priority over speed or code volume.

## 2. Instruction priority

When working in this repository, follow instructions in this order:

1. The current user task or issue.
2. This `AGENTS.md` file.
3. Project methodology and documented conventions.
4. Existing public interfaces and tests.
5. General engineering preferences.

If instructions conflict, stop and report the conflict instead of making an assumption.

## 3. Mandatory development workflow

All changes to financial calculations, portfolio logic, costs, data validation, simulations, and optimization must follow Test-Driven Development.

The required cycle is:

1. Understand the task.
2. Inspect relevant code and tests.
3. State the calculation conventions.
4. Execute the relevant existing tests to establish a baseline.
5. RED: write a failing test before changing production code.
6. Confirm that the test fails for the intended reason.
7. GREEN: implement the minimum code required for the test to pass.
8. Execute the focused test set.
9. Execute the complete test suite.
10. REFACTOR only if useful and without changing behavior.
11. Execute the complete test suite again.
12. Summarize changes, evidence, risks, and remaining limitations.

Do not claim TDD if the test and implementation were created together without evidence that the test failed first.

## 4. Phase boundaries

### 4.1 PLAN

Before changing files:

- Read this file.
- Read the task specification completely.
- Inspect the relevant modules and tests.
- Identify the smallest behavior that satisfies the task.
- State which files are expected to change.
- State the formulas, units, frequencies, and edge-case conventions.
- Identify ambiguities before implementation.

Do not redesign unrelated parts of the project.

### 4.2 BASELINE

Before writing a new test, run the relevant existing tests.

Record:

- command executed;
- number of passing, failing, skipped, and errored tests;
- any pre-existing failures.

Do not silently fix unrelated pre-existing failures. Report them separately.

### 4.3 RED

During RED:

- Modify test files only, unless a minimal test fixture is also needed.
- Do not change production code.
- Use examples whose expected results can be verified manually.
- Cover the main behavior and relevant boundaries.
- Run the narrowest test command that demonstrates the missing behavior.
- Confirm that the failure is caused by the missing or incorrect behavior.

An import error, syntax error, broken fixture, or incorrect test setup is not valid RED evidence unless the task specifically concerns that failure.

Stop after RED if the task explicitly requests phased execution.

### 4.4 GREEN

During GREEN:

- Do not change expected values from RED.
- Do not weaken assertions or increase tolerances merely to pass.
- Implement only the behavior required by the tests and task.
- Preserve existing public interfaces unless the task explicitly changes them.
- Run focused tests first.
- Run the full suite afterward.

If a RED test is conceptually wrong, stop and explain the problem. Do not silently modify both the test and production code.

### 4.5 REFACTOR

Refactoring is optional and must occur only after GREEN.

During REFACTOR:

- Do not add new behavior.
- Do not change formulas or conventions.
- Do not change the public API without explicit authorization.
- Do not remove test coverage.
- Keep the refactor local to the task.
- Run the full suite after refactoring.

If the implementation is already clear and small, skip refactoring.

## 5. Scope control

Every task must be treated as a small, reviewable change.

Agents must:

- change only files required by the task;
- avoid opportunistic cleanup;
- avoid broad renaming;
- avoid formatting unrelated files;
- avoid dependency upgrades unrelated to the task;
- avoid changing notebook output unless required;
- avoid modifying the Streamlit interface when implementing core calculations, unless explicitly requested.

If additional work is discovered, report it as a follow-up instead of expanding scope.

## 6. Test integrity rules

Agents must never:

- delete a failing test to make the suite pass;
- skip, mark `xfail`, or disable a test without explicit authorization;
- weaken an assertion;
- replace an exact expected result with a vague assertion;
- increase numerical tolerance without a mathematical justification;
- mock the function under test;
- duplicate production logic inside a test merely to reproduce the same result;
- hide failures with broad exception handling;
- alter fixtures solely to make an implementation appear correct;
- change historical expected results without explaining the methodological change.

Tests should validate observable behavior, not internal implementation details.

## 7. Test design standards

### 7.1 Unit tests

Use unit tests for pure calculations such as:

- mean, median, percentiles, and frequency counts;
- win rate, average gain, average loss, payoff, and expectancy;
- Profit Factor;
- equity and drawdown series;
- Maximum Drawdown and drawdown episodes;
- Time Under Water;
- Ulcer Index;
- Sharpe, Sortino, Calmar, and Recovery Factor;
- Value at Risk and Expected Shortfall;
- skewness and kurtosis;
- winning and losing streaks;
- operational-unit scaling;
- monthly license cost by position-size band;
- transaction-cost calculations.

### 7.2 Integration tests

Use integration tests for flows such as:

```text
CSV import
-> validation
-> daily aggregation
-> position-size scaling
-> costs
-> net equity
-> performance report
```

Also test:

```text
multiple robot series
-> date alignment
-> portfolio aggregation
-> portfolio costs
-> portfolio metrics
```

### 7.3 Regression tests

Maintain small deterministic fixtures with manually verified expected outputs. Regression tests should detect unintended changes to:

- gross and net profit;
- total costs;
- Maximum Drawdown;
- Time Under Water;
- Ulcer Index;
- Expected Shortfall;
- portfolio aggregation;
- portfolio results with and without a robot.

### 7.4 Property and invariant tests

When appropriate, verify invariants such as:

- zero position size produces zero scaled P&L;
- scaling by an integer factor scales gross P&L linearly when the model explicitly assumes linear scaling;
- portfolio daily P&L equals the sum of scaled component P&Ls;
- drawdown is never positive;
- equity at a new high has zero drawdown;
- total costs are never negative unless rebates are explicitly modeled;
- net P&L equals gross P&L minus modeled costs;
- a missing observation is not automatically equal to zero;
- changing row order does not change results after valid chronological sorting.

## 8. Financial domain conventions

Financial conventions must be explicit and documented. Never infer a convention silently.

### 8.1 Primary analysis frequency

Unless a task states otherwise:

- portfolio risk metrics are calculated from daily P&L or daily returns;
- multiple trades on the same day are aggregated before portfolio-level risk analysis;
- trade-level and day-level metrics remain separate and clearly labeled.

### 8.2 Positive, negative, and neutral periods

- Positive result: value greater than zero.
- Negative result: value less than zero.
- Neutral result: value equal to zero.
- Missing data is not neutral data.

### 8.3 Payoff

Unless explicitly changed:

```text
payoff = average positive result / absolute value of average negative result
```

Always label the direction of the ratio. Avoid ambiguous descriptions such as `10:1` without stating whether it means gain-to-loss or loss-to-gain.

### 8.4 Expectancy

Unless explicitly changed:

```text
expectancy = win_probability * average_gain
             - loss_probability * absolute_average_loss
```

Zero results must not be silently classified as wins or losses.

### 8.5 Profit Factor

Unless explicitly changed:

```text
profit_factor = gross_positive_results / absolute_gross_negative_results
```

Define behavior for series with no losses or no gains before implementation.

### 8.6 Drawdown

Drawdown must be calculated from an equity curve relative to its running peak.

For portfolios:

1. scale each robot's daily P&L by its configured number of units;
2. aggregate daily P&L across robots;
3. build the portfolio equity curve;
4. calculate drawdown from the aggregated equity curve.

Never add or scale individual Maximum Drawdowns to estimate portfolio Maximum Drawdown.

Before implementing drawdown duration, define:

- whether recovery occurs when equity equals or exceeds the prior peak;
- whether duration counts observations or calendar days;
- whether the peak observation is included;
- how repeated equal peaks are handled;
- how an unrecovered drawdown at the end of the sample is represented.

### 8.7 Time Under Water

Time Under Water must be derived from documented drawdown episodes. State clearly whether it is measured in trading observations, calendar days, or another unit.

### 8.8 Ulcer Index

Unless explicitly changed:

```text
ulcer_index = square_root(mean(squared_percentage_drawdowns))
```

State whether percentage drawdowns are represented as decimals or percentage points.

### 8.9 Annualized ratios

For Sharpe, Sortino, volatility, and similar metrics:

- document the analysis frequency;
- document the annualization factor;
- document the risk-free rate or target return;
- do not annualize short or irregular samples without an explicit convention;
- do not round inside the calculation function.

### 8.10 Tail metrics

For Value at Risk and Expected Shortfall:

- document the quantile convention;
- document sign conventions;
- specify whether losses are returned as negative values or positive magnitudes;
- test small samples and boundary quantiles;
- avoid parametric assumptions unless explicitly requested.

## 9. Robot units and position sizing

Each robot has an operational unit that may be simple or composite.

Examples:

```text
Robot X: 1 unit = 1 WIN
Robot Y: 1 unit = 1 WIN + 2 WDO
Robot Z: 1 unit = 1 WIN
```

Rules:

- portfolio quantities must be non-negative integers unless fractional units are explicitly supported;
- scaling a composite unit must scale all components;
- commercial license units and market exposure units are separate concepts;
- do not assume that one unit has equal risk across robots;
- do not assume that P&L, slippage, or fees scale linearly unless configured;
- position-size limits must be validated.

## 10. Date alignment and missing data

Date handling is a critical domain rule.

Agents must distinguish:

- a valid day with no trades;
- a valid day with zero result;
- a missing record;
- a robot that was unavailable in that period;
- an incomplete CSV;
- a non-trading day.

Do not automatically fill missing robot observations with zero.

Portfolio analysis must support a clearly documented date policy, such as:

- intersection of valid robot periods;
- user-selected interval with completeness checks;
- another explicit policy.

Every portfolio report must record its start date, end date, and alignment policy.

## 11. Cost modeling

Costs must remain separate and traceable.

At minimum, support the distinction:

```text
gross P&L
- variable exchange and transaction costs
= P&L after variable costs
- robot licenses and other fixed costs
= net P&L
```

### 11.1 Brokerage

Brokerage is configurable. It may be zero, but it must not be globally hard-coded as universally zero.

### 11.2 Exchange fees

B3 and other exchange fees must:

- be parameterized rather than embedded as unexplained constants;
- be separated by product when required;
- support effective-date versioning when tariff tables change;
- distinguish exact costs from estimated costs;
- document whether entry and exit are counted separately;
- distinguish trades, contracts, and executed sides;
- account for partial executions when execution-level data exists.

Never invent a tariff value.

### 11.3 Monthly robot license

Robot license costs may depend on position-size bands.

Boundary values must be explicitly tested, including:

```text
zero units
first value in a band
last value in a band
first value in the next band
value above the configured maximum
```

The implementation must document:

- whether a partial month is charged fully or proportionally;
- when a position-size change affects billing;
- whether cost is booked on a specific date or allocated across trading days;
- whether the commercial quantity differs from the operational quantity.

### 11.4 Shared costs

VPS, platform, data, and other shared costs must have an explicit allocation policy. Keep both incremental-cost and fully-loaded views when requested.

## 12. Portfolio construction

Portfolio P&L must be built at the daily level:

```text
portfolio_pnl[date] = sum(
    robot_daily_pnl[robot, date] * configured_units[robot]
)
```

After daily aggregation, recalculate all portfolio metrics from the resulting portfolio series.

Portfolio analysis should preserve:

- component daily P&L;
- scaled component daily P&L;
- gross portfolio P&L;
- variable costs;
- fixed costs;
- net portfolio P&L;
- contribution of each robot to profit and major drawdowns.

Any comparison with and without a robot must use the same period, cost conventions, and date-alignment policy.

## 13. Simulation and optimization

Simulation and optimization are high-risk modules. Do not implement them before the input, metric, cost, and portfolio layers are tested.

### 13.1 Simulation

For Monte Carlo or bootstrap methods:

- use deterministic seeds in tests;
- document whether sampling occurs by trade, day, or block;
- when simulating a portfolio, resample synchronized robot rows together to preserve cross-robot dependence;
- distinguish simple shuffling, bootstrap, and block bootstrap;
- test output shape, reproducibility, and known edge cases;
- do not present simulated outcomes as guaranteed forecasts.

### 13.2 Optimization

Optimization must:

- use non-negative integer quantities when operational units are indivisible;
- use net results after modeled costs unless the task explicitly requests gross optimization;
- respect configured position, cost, drawdown, tail-risk, and concentration constraints;
- report infeasible problems clearly;
- avoid calling a historical solution universally optimal;
- record the objective, constraints, period, data version, and cost assumptions;
- separate calibration and validation periods when required;
- avoid evaluating a selected solution only on the same data used to select it.

Tests should use small search spaces that can be verified by exhaustive manual enumeration.

## 14. Data validation

Input validation must occur before analysis.

Validate, when applicable:

- required columns;
- date parsing;
- numeric parsing;
- duplicate records;
- operation identifiers;
- known products;
- positive quantities;
- entry and exit chronology;
- missing values;
- date coverage;
- unexpected currencies or units;
- inconsistent decimal separators;
- whether costs or slippage are already included.

Prefer explicit errors for invalid data and explicit warnings for uncertain but processable data.

Do not silently repair financial data unless the repair rule is documented and surfaced to the user.

## 15. Numerical standards

- Use appropriate numeric types for each calculation.
- Do not round inside core calculation functions unless rounding is part of the domain rule.
- Round only for display or export.
- Use `pytest.approx` or equivalent only with a justified tolerance.
- Handle division by zero explicitly.
- Define outputs for empty samples, all-zero samples, no-win samples, and no-loss samples.
- Avoid converting missing values to zero as a convenience.
- Keep currency values and percentage returns semantically distinct.

## 16. Architecture rules

Keep business logic separate from presentation.

Recommended responsibilities:

```text
src/tradefolio/validation.py    input validation
src/tradefolio/metrics.py       performance metrics
src/tradefolio/drawdowns.py     drawdown calculations
src/tradefolio/costs.py         cost calculation
src/tradefolio/alignment.py     calendar and series alignment
src/tradefolio/portfolio.py     portfolio aggregation
src/tradefolio/attribution.py   component contribution
src/tradefolio/simulation.py    Monte Carlo and bootstrap
src/tradefolio/optimization.py  portfolio search and optimization
app.py                          Streamlit interface only
```

Rules:

- do not place core financial formulas in `app.py`;
- notebooks may explore ideas but are not the source of truth;
- migrate accepted notebook logic into tested modules;
- avoid hidden global state;
- prefer pure functions for calculations;
- use typed, explicit interfaces where practical;
- keep I/O separate from calculations.

## 17. Streamlit rules

The Streamlit application is a presentation layer.

Agents may test manually or with lightweight interface tests, but calculation correctness must be protected below the UI layer.

The app must:

- clearly label synthetic demonstration data;
- distinguish gross and net results;
- display warnings for missing or estimated data;
- display the selected analysis period;
- display position sizes and composite units;
- avoid presenting results as financial advice;
- avoid exposing secrets or private trading data.

Do not add secrets, account identifiers, credentials, proprietary strategy code, or confidential CSVs to the repository.

## 18. Dependencies

Do not add or upgrade dependencies without justification.

Before adding a dependency:

1. confirm the standard library or an existing dependency cannot solve the problem reasonably;
2. explain why the dependency is required;
3. check its compatibility with the supported Python version and deployment environment;
4. update dependency files consistently;
5. add or update tests;
6. document deployment implications.

Never place API keys or credentials in source code, tests, notebooks, fixtures, or committed configuration files.

## 19. Documentation requirements

Any change to a financial formula or convention must update the relevant documentation.

Documentation must state:

- formula;
- input frequency;
- units;
- sign convention;
- annualization rule;
- missing-data behavior;
- edge-case behavior;
- known limitations.

Code comments should explain why a non-obvious financial convention exists, not merely restate the code.

## 20. Commands

Prefer commands defined by the repository. If the project has not yet defined them, use the following conventions where available:

```bash
python -m pytest
python -m pytest tests/test_metrics.py -v
python -m pytest --cov=tradefolio --cov-report=term-missing
ruff check .
ruff format --check .
```

Do not claim that a command succeeded unless it was actually executed in the current environment.

If a command cannot run because of missing dependencies or environment limitations, report the exact blocker and do not fabricate results.

## 21. Git and commit rules

Agents must not create commits, push branches, force-push, merge, or rewrite history unless explicitly instructed.

Recommended commit structure when the user requests commits:

```text
test(metrics): define payoff behavior
feat(metrics): implement payoff calculation
refactor(metrics): simplify payoff calculation
```

Commits should be small and scoped to one behavior.

Do not include unrelated generated files, large datasets, secrets, or private trading records.

## 22. Required completion report

At the end of each phase, report evidence using this format.

### RED report

```text
Scope:
- behavior under test

Files changed:
- tests/...

Manual examples:
- input
- expected calculation
- expected output

Command executed:
- exact command

Observed failure:
- failing test name
- concise failure reason

RED validity:
- why the failure demonstrates the missing behavior
```

### GREEN report

```text
Implementation:
- concise description

Files changed:
- src/...
- tests/...

Focused tests:
- command
- result

Full suite:
- command
- result

Limitations or follow-ups:
- remaining items, if any
```

### REFACTOR report

```text
Refactor:
- what changed structurally
- why it is safer or clearer

Behavior changes:
- none

Full suite:
- command
- result
```

## 23. Definition of done

A task is complete only when all applicable items are true:

- the task has a narrow, explicit scope;
- formulas and conventions are documented;
- relevant baseline tests were run;
- a new or changed test failed for the intended reason before production implementation;
- the minimum implementation made the test pass;
- focused tests pass;
- the complete suite passes, or pre-existing failures are clearly reported;
- no assertions were weakened;
- no unrelated files were modified;
- no secrets or private data were added;
- documentation was updated where required;
- the final report includes commands and actual results;
- remaining uncertainties are explicit.

## 24. Stop conditions

Stop and ask for direction, or clearly report the blocker, when:

- a financial convention is ambiguous;
- expected values cannot be verified independently;
- existing tests contradict the task;
- completing the task requires changing an unrelated public interface;
- the tariff or cost rule is missing;
- missing data cannot be distinguished from zero activity;
- the requested optimization objective is undefined;
- required files or dependencies are unavailable;
- a test fails for a reason unrelated to the intended RED phase;
- production or confidential data may be exposed;
- the only way to pass is to weaken a test or validation rule.

Do not guess in these situations.

## 25. Default agent prompt behavior

When no phase is specified, the agent should:

1. inspect and plan;
2. run the baseline;
3. execute RED;
4. report RED evidence;
5. continue to GREEN only if the task explicitly authorizes autonomous end-to-end completion;
6. run the full suite;
7. refactor only if clearly beneficial;
8. provide the required completion report.

For high-risk changes involving costs, drawdowns, missing data, portfolio aggregation, simulation, or optimization, prefer an explicit checkpoint between RED and GREEN.
