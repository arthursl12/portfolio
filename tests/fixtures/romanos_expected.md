# Fixture: romanos_orders.csv — valores de regressão

CSV real exportado da Smarttbot (robô "Romanos", simulador pessimista,
11/06/2025 a 08/09/2026, 1645 linhas de ordem, 2 contratos padrão de backtest).
Não é hand-verificável linha a linha (grande demais) — os valores abaixo foram
conferidos contra o relatório nativo da própria plataforma Smarttbot para essa
mesma conta nesta sessão. Use como **teste de regressão**: se uma mudança de
código fizer esses números se afastarem do que está documentado aqui (fora da
tolerância anotada), é sinal de comportamento não intencional, não
necessariamente de "conta errada" — investigue antes de atualizar o fixture.

## Discrepância conhecida e aceita

O CSV reconstrói **822 trades**; a Smarttbot reporta **823** no histórico
completo do robô. A diferença bate exatamente com **1 trade perdedor de
R$424,00** que deve ter ocorrido antes de 11/06/2025 (fora da janela do
export) — não está no CSV, então não é reproduzível pelo nosso pipeline.
Todas as métricas de regressão abaixo foram calculadas **sobre o CSV como
está** (822 trades) e conferidas contra a Smarttbot ciente dessa diferença
constante de R$424,00 (~1 trade) nos totais brutos/líquidos absolutos.

## Convenções usadas nesta fixture

- Custo: R$0,25 por contrato por perna (entrada e saída cobradas
  separadamente) → R$0,50/contrato no round trip.
- Capital de referência: R$1.000/contrato (margem sugerida pelo autor do
  robô) = R$2.000,00 de "saldo inicial" para 2 contratos — usado para
  retorno % e como base do pico móvel do drawdown %.
- Trade reconstruído pela posição líquida (abre em 0, fecha em 0), agrupando
  fills parciais — não por contagem de linha "saída".
- Calendário de pregões: `pandas_market_calendars`, calendário `'B3'`.

## Valores validados contra o relatório nativo da Smarttbot (exatos)

| Métrica | Nosso pipeline | Smarttbot | Status |
|---|---:|---:|---|
| Custo operacional total | R$821,50 | R$821,50 | ✅ exato |
| Drawdown máximo % (capital R$1.000/contrato) | 35,36% | 35,36% | ✅ exato |
| Maior sequência de trades vencedores (comprimento) | 10 | 10 | ✅ exato |
| Maior sequência de trades perdedores (comprimento) | 12 | 12 | ✅ exato |
| Lucro total da sequência vencedora | R$2.442,00 | R$2.442,00 | ✅ exato |
| Prejuízo total da sequência perdedora | R$2.112,00 | R$2.112,00 | ✅ exato |

## Valores validados com diferença explicada (~1 trade / R$424,00)

| Métrica | Nosso pipeline | Smarttbot | Diferença |
|---|---:|---:|---|
| Nº de trades reconstruídos | 822 | 823 | -1 (trade fora da janela do CSV) |
| Lucro bruto total (2 contratos) | R$22.609,00 | R$22.185,00 | +R$424,00 |
| Lucro líquido total (2 contratos) | R$21.787,50 | R$21.363,50 | +R$424,00 |
| Retorno líquido % (capital R$2.000) | 1.089,38% | 1.068,18% | +21,2 p.p. (=424/2000) |
| Win rate (por trade, líquido) | 41,12% (338/822) | 40,95% (337/823) | ~consistente |
| Profit Factor (por trade, líquido) | 1,2766 | 1,27 | ~consistente |

## Outros valores de referência (não conferidos contra a Smarttbot, mas
## reproduzíveis e estáveis — trate como regressão pura)

| Métrica | Valor observado nesta sessão |
|---|---:|
| Pregões no período | 312 |
| Dias operados / sem trade | 294 / 18 |
| Payoff (diário) | 1,488982 |
| Skewness (diário) | +1,163 (cauda de ganhos mais pesada) |
| Kurtosis excesso (diário) | +1,956 |
| Maximum Drawdown (R$/contrato) | -1.441,50 |
| Time Under Water máximo | 52 pregões (episódio 08/09/2025 → 21/11/2025) |
| Maior episódio de drawdown (profundidade) | -R$1.441,50 (pico 02/07/2026 → fundo 21/07/2026 → recuperado 30/07/2026) |

## O que NÃO está coberto por esta fixture

- Página 4 (janelas móveis, consistência mensal/trimestral) — ainda não
  implementada.
- Página 5 (Monte Carlo / block bootstrap) — ainda não implementada.
- Portfólio (múltiplos robôs) — precisa dos outros 4 CSVs da Smarttbot.
