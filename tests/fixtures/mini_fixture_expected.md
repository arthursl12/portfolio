# Fixture: mini_fixture_orders.csv — valores esperados (calculados manualmente)

Fixture mínima e determinística para testes unitários (RED). 5 trades ao longo de
5 pregões da B3 (02, 03, 06, 07 e 08/01/2025 — 07/01 não tem nenhuma ordem, é o
caso de "dia com pregão mas sem trade"). Contrato de referência: 2 (padrão de
backtest). Custo: R$0,25/contrato/perna.

## Trades (bruto, líquido = bruto − R$1,00 de custo por trade de 2 contratos)

| # | Data       | Bruto (R$) | Líquido (R$) |
|---|------------|-----------:|-------------:|
| 1 | 02/01/2025 |     200,00 |       199,00 |
| 2 | 03/01/2025 |     100,00 |        99,00 |
| 3 | 03/01/2025 |    -150,00 |      -151,00 |
| 4 | 06/01/2025 |    -300,00 |      -301,00 |
| 5 | 08/01/2025 |       0,00 |        -1,00 | ← resultado bruto zero, líquido negativo por custo

## Série diária (2 contratos / por contrato)

| Data       | Bruto  | Custo | Líquido (2c) | Líquido/contrato | Operou? |
|------------|-------:|------:|-------------:|------------------:|---------|
| 02/01/2025 | 200,00 | 1,00  | 199,00       | 99,50             | sim     |
| 03/01/2025 | -50,00 | 2,00  | -52,00       | -26,00            | sim (2 trades) |
| 06/01/2025 |-300,00 | 1,00  | -301,00      | -150,50           | sim     |
| 07/01/2025 |   0,00 | 0,00  | 0,00         | 0,00              | **não** (pregão sem ordem) |
| 08/01/2025 |   0,00 | 1,00  | -1,00        | -0,50             | sim (trade zero) |

## Métricas esperadas — nível diário (por contrato)

| Métrica | Valor esperado |
|---|---|
| pregões | 5 |
| lucro líquido (2 contratos) | -155,00 |
| lucro líquido por contrato | -77,50 |
| média diária | -15,50 |
| mediana diária | -0,50 |
| % dias positivos | 20% (1/5) |
| % dias negativos | 60% (3/5) |
| % dias neutros | 20% (1/5, o dia 07/01 sem trade) |
| gain médio | 99,50 |
| loss médio | -59,00 |
| payoff | 1,686441 (99,50 / 59,00) |
| expectância diária | -15,50 |
| profit factor diário | 0,562147 (99,50 / 177,00) |
| pior dia | -150,50 |
| melhor dia | 99,50 |
| equity acumulada (por contrato) | [99,50; 73,50; -77,00; -77,00; -77,50] |
| drawdown (por contrato) | [0; -26,00; -176,50; -176,50; -177,00] |
| Maximum Drawdown | -177,00 |
| Time Under Water máximo | 4 pregões (03/01 a 08/01, ainda não recuperado no fim da fixture) |
| Ulcer Index (R$) | 137,338633 |

> Sharpe/Sortino/Calmar e as versões em % (drawdown%, Ulcer%) **não são
> hand-verificáveis com precisão** nessa amostra de 5 pontos (dependem de
> anualização e do capital de referência R$1.000/contrato) — trate como
> **regressão** (congele o valor produzido pela implementação de referência,
> não recalcule na mão) em vez de asserção exata.

## Métricas esperadas — nível trade (líquido, 2 contratos)

| Métrica | Valor esperado |
|---|---|
| n trades | 5 |
| win rate | 40% (2/5) |
| profit factor (trade) | 0,657837 (298,00 / 453,00) |
| lucro médio por trade vencedor | 149,00 |
| prejuízo médio por trade perdedor | -151,00 |
| maior sequência positiva | 2 trades, R$298,00 (trades #1 e #2) |
| maior sequência negativa | 3 trades, R$-453,00 (trades #3, #4 e #5) |

## Casos de borda cobertos por esta fixture

- Dia com pregão na B3 mas **sem nenhuma ordem** (07/01) → deve entrar na série
  com resultado 0 e `operou=False`, não deve ser descartado nem confundido com
  dado faltante.
- Trade com **resultado bruto exatamente zero** → não é nem "ganho" nem
  "perda" antes do custo; depois do custo (R$1,00) vira prejuízo. Testa que a
  classificação positivo/negativo/neutro usa o valor líquido, e que zero não é
  silenciosamente jogado num dos dois lados.
- Sequência negativa de trades **atravessando um dia sem operação** (trade #4
  em 06/01, trade #5 em 08/01, com 07/01 vazio no meio) → a sequência não deve
  "quebrar" por causa do dia vazio, já que ele não é um trade.
- Drawdown **ainda não recuperado** ao final da amostra → `data_recuperacao`
  deve ser nulo/ausente, não uma data inventada.
