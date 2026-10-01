# Analytics de Portfólio de Estratégias Sistemáticas

Uma plataforma de pesquisa para importar históricos de robôs de trading
sistemático, medir seu risco e performance, e avaliar como eles se
comportam como componentes de um portfólio discreto (contratos inteiros)
— não apenas ranqueados individualmente.

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
· [🇺🇸 English](README.md)

**[Demo ao vivo](https://easportfolio.streamlit.app/)** · [Arquitetura](#arquitetura) · [Rodando localmente](#rodando-localmente)

> Projeto de pesquisa pessoal em desenvolvimento ativo. Criado para
> avaliar estratégias automatizadas de trading como componentes de um
> portfólio, não apenas pela performance isolada. Não é um serviço de
> sinais de trading — não executa ordens nem dá recomendação financeira.

*(GIF principal de demonstração em breve — veja [Módulos da aplicação](#módulos-da-aplicação)
abaixo para entender cada parte, ou abra direto a [demo ao vivo](https://easportfolio.streamlit.app/).)*

## Problema

Estratégias automatizadas de trading costumam ser avaliadas isoladamente
(retorno, Sharpe, drawdown, curva de capital individual). Mas uma boa
performance isolada não diz como uma estratégia muda o risco de um
*portfólio* — ela pode diversificar, ou pode só reproduzir um risco que
já existe.

Esta plataforma existe para responder perguntas como:

- Como adicionar uma estratégia muda o drawdown agregado do portfólio?
- Ela agrega diversificação, ou se correlaciona com o que já está no
  portfólio?
- Quais alocações são operacionalmente viáveis, dado que as estratégias
  só operam em contratos inteiros?
- Quão robusto é um resultado ao caminho histórico específico, versus
  variação simulada (Monte Carlo)?
- Toda métrica do resultado pode ser rastreada até o dado de ordem de
  origem e a fórmula que a produziu?

## Capacidades atuais

### Implementado

- Importação e validação de CSVs de execução de ordens da Smarttbot, com
  diagnósticos determinísticos de qualidade de dado (ordens duplicadas,
  saídas sem resultado, status desconhecido, datas/valores inválidos,
  mês incompleto, ...)
- Reconstrução de trades a partir de mudanças na posição líquida — não
  das linhas brutas de ordem — e construção de uma série diária de
  resultado alinhada ao calendário real de pregão da B3
- Métricas por trade e por dia: Profit Factor, taxa de acerto,
  sequências de ganho/perda (tamanho e R$), drawdown, Time Under Water,
  Ulcer Index, Sharpe/Sortino/Calmar, VaR/Expected Shortfall
- Um limiar de risco baseado em margem ("limiar") e um motor de retirada
  de capital ("vapo") avaliado contra esse limiar
- Simulação de robustez via Monte Carlo sobre a sequência de trades de
  uma estratégia
- Sincronização e comparação de múltiplas estratégias como portfólio:
  correlação móvel, clusters de risco, contribuição marginal ao risco do
  portfólio
- Um funil guiado para construir carteiras candidatas discretas
  (contratos inteiros) — orçamento de risco, limites de concentração,
  uma fronteira de Pareto discreta, comparação final de shortlist e um
  plano operacional
- Duas saídas: um relatório HTML autocontido ("lâmina") e um app
  Streamlit ao vivo com três modos — relatório de robô único, análise de
  portfólio (Lab) e Portfolio Builder

### Em andamento

- Políticas adicionais de retirada de capital (6 das 7 políticas
  nomeadas ainda precisam de uma fórmula explícita decidida antes de
  serem implementadas — ver `AGENTS.md` §8 sobre nunca inventar uma
  convenção financeira)
- Redesenho visual da "lâmina" no Streamlit (semáforo de status,
  anotações de dado ausente no gráfico) — o dado já existe, é
  reorganização de UI
- Um sinal independente de "dado ausente" no nível de portfólio
  (atualmente indistinguível de "esta estratégia ainda não existia")

### Não implementado

- Análise de run-up / barreiras de drawdown
- Formatos de importação genéricos (fora do padrão Smarttbot)
- Persistência de análises entre sessões
- Integração com corretora ou execução automática de ordens
- Pipeline de integração contínua (CI)

## Módulos da aplicação

### Relatório de robô único ("Lâmina")

Analisa o histórico de ordens de um robô isoladamente: curva de capital,
drawdown, sequências de trades e métricas de risco de cauda, renderizado
como um relatório HTML autocontido ou como o primeiro modo do app ao
vivo.

*(Screenshot em breve.)*

### Portfólio (Lab)

Sincroniza duas ou mais estratégias e mostra como elas se comportam
combinadas: correlação, clusters de risco e a contribuição marginal de
cada estratégia ao drawdown do portfólio.

*(Screenshot em breve.)*

### Portfolio Builder

Um funil guiado, passo a passo, que transforma uma shortlist de
estratégias em carteiras operacionalmente viáveis — orçamento de risco,
limites de concentração, uma fronteira de Pareto discreta sobre
combinações de contratos inteiros, e uma comparação final das carteiras
candidatas sob cenários históricos e de Monte Carlo.

*(Screenshot em breve.)*

## Destaques de engenharia

- **Alocação discreta de portfólio.** A busca de Pareto do Portfolio
  Builder só propõe combinações em contratos inteiros, então toda
  carteira candidata é uma que você conseguiria de fato executar — não
  um peso contínuo matematicamente bonito, porém inexequível.
- **Analytics isolado da interface.** `src/tradefolio/` e `report.py` não
  fazem nenhuma chamada ao Streamlit; `app.py` só importa e renderiza. As
  mesmas funções de cálculo rodam na CLI (`report.py`), na suíte de
  testes e no app ao vivo.
- **Tratamento explícito de dado ausente.** A série diária é reindexada
  no calendário real da B3; um dia sem dado é mantido distinto de um dia
  em que a estratégia legitimamente não operou.
- **Convenções de domínio validadas contra a plataforma de origem, não
  inventadas.** O modelo de custo, o capital de referência e a base do
  drawdown percentual foram reconciliados, exchange a exchange, contra o
  próprio relatório da plataforma Smarttbot
  (`tests/fixtures/romanos_expected.md`), não derivados do zero.
- **TDD em todo cálculo financeiro** — 454 testes automatizados,
  incluindo casos de regressão para bugs reais encontrados durante o
  desenvolvimento (ex: reconstrução de trades que mesclava trades entre
  instrumentos diferentes).

## Arquitetura

```text
CSV de ordens Smarttbot
        │
        ▼
Importação e validação          (loaders.py, validation.py)
        │
        ▼
Reconstrução de trades           (trades.py)
Série diária no calendário B3    (alignment.py, daily.py)
        │
        ▼
Métricas: drawdown, Ulcer Index, Sharpe/Sortino/Calmar, VaR/ES,
limiar de risco, motor de retirada, robustez Monte Carlo
        (metrics.py, drawdowns.py, limiar.py, vapo.py, monte_carlo.py, ...)
        │
        ▼
Sincronização multi-estratégia, correlação, alocação discreta
        (portfolio.py, portfolio_builder.py)
        │
        ▼
report_data.py (saída organizada por página)
        ├── report.py  → "lâmina" HTML estática
        └── app.py     → app Streamlit ao vivo
```

Ver `CLAUDE.md` para a arquitetura completa e as notas de convenção de
domínio, e `AGENTS.md` para o workflow obrigatório (TDD, regras de
convenção financeira, disciplina de escopo).

## Stack tecnológica

- **Python** — motor de domínio e cálculo
- **Pandas / NumPy** — transformação de séries temporais e agregação
  diária
- **pandas_market_calendars** — alinhamento ao calendário de pregão da B3
- **Matplotlib** — gráficos embutidos (PNG em base64) no relatório HTML
  estático
- **Plotly** — gráficos interativos no app Streamlit
- **Streamlit** — interface de pesquisa ao vivo
  ([implantado aqui](https://easportfolio.streamlit.app/))
- **Pytest** — suíte de testes de domínio e regressão (454 testes)

## Fluxo dos dados

1. Importa um ou mais CSVs de ordens da Smarttbot; valida e sinaliza
   problemas de qualidade de dado.
2. Reconstrói trades a partir de mudanças na posição líquida e constrói
   uma série diária de resultado alinhada ao calendário B3.
3. Calcula métricas por trade e por dia: drawdown, Ulcer Index,
   Sharpe/Sortino/Calmar, VaR/ES, limiar de risco, retiradas, robustez
   Monte Carlo.
4. Para um portfólio: sincroniza estratégias, analisa correlação e
   concentração, e gera alocações candidatas discretas (contratos
   inteiros).
5. Renderiza os resultados como uma "lâmina" HTML estática ou através do
   app Streamlit ao vivo.

## Rodando localmente

### Requisitos

- Python 3.10+
- Git

### Setup

```bash
git clone <repository-url>
cd Portfolio
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install -e .
```

(`requirements-dev.txt` inclui `requirements.txt` — pandas, numpy,
matplotlib, pandas_market_calendars — mais pytest. O `pip install -e .`
deixa o pacote `tradefolio` em `src/` importável de qualquer lugar do
projeto — sem ele, `import tradefolio` só funciona dentro do pytest.)

### Gerando um relatório para uma estratégia

```bash
.venv/bin/python report.py robo caminho/para/ordens.csv saida.html --minimum-margin 5000
```

`--minimum-margin` é obrigatório — `AGENTS.md` §8 proíbe inventar um
valor default de convenção financeira, então não há um. Rode
`report.py robo --help` / `report.py portfolio --help` para a lista
completa de parâmetros (Monte Carlo, cenário de deterioração, custo
mensal, janela de detecção multi-ativo, ...).

### Testando sem dados próprios

```bash
.venv/bin/python demo.py
```

Roda `report.py` sobre o histórico real de um robô de exemplo
(`dados_exemplo/orders_romanos2.csv`) e escreve `orders_romanos2.html`.

### Rodando o app ao vivo

```bash
.venv/bin/streamlit run app.py
```

Abre em `http://localhost:8501`. Ou use a versão hospedada:
https://easportfolio.streamlit.app/

## Testes

```bash
.venv/bin/python -m pytest
```

454 testes cobrindo: parsing de CSV e diagnósticos de qualidade de dado,
reconstrução de trades a partir da posição líquida (não das linhas
brutas de ordem), alinhamento da série diária ao calendário B3,
drawdown/Ulcer Index/Sharpe/Sortino/Calmar, agregação de custo e custo
mensal, cálculos de limiar de risco e política de retirada, robustez
Monte Carlo, sincronização multi-estratégia de portfólio e alocação
discreta, e casos de regressão para bugs reais encontrados durante o
desenvolvimento.

Ainda não há pipeline de CI — os testes rodam localmente antes de cada
mudança, não automaticamente a cada push (ver [Roadmap](#roadmap)).

## Decisões técnicas selecionadas

### Por que alocações em contratos inteiros em vez de pesos contínuos?

As estratégias aqui só operam em contratos inteiros. Um otimizador de
peso contínuo pode produzir uma alocação matematicamente atraente — por
exemplo, "2,37 contratos da Estratégia A" — que simplesmente não pode ser
executada como ordem. A busca de Pareto discreta do Portfolio Builder só
propõe combinações que são literalmente executáveis.

### Por que manter os cálculos por contrato em vez de por conta?

Todo valor em reais é normalizado pelo tamanho de posição de referência
do backtest. Generalizar ou esconder essa constante mudaria
silenciosamente o significado de um número entre robôs com tamanhos de
posição diferentes, então ela fica explícita em vez disso (ver
`CLAUDE.md`).

### Por que distinguir dado ausente de dia sem operação?

Um dia com resultado zero porque a estratégia legitimamente não operou
não é o mesmo que um dia sem dado por causa de uma lacuna na importação.
Confundir os dois subestimaria o risco silenciosamente justamente nos
dias que mais importam para drawdown e Ulcer Index, então a série diária
mantém uma flag explícita `operou` em vez de colapsar os dois casos em
zero.

## Limitações atuais

- Só o formato de exportação CSV da Smarttbot é suportado; ainda não há
  um importador genérico.
- As análises não são persistidas — cada sessão (CLI ou Streamlit) parte
  dos CSVs de origem.
- Não há pipeline de CI — os testes rodam localmente, não
  automaticamente a cada push.
- A sincronização de portfólio ainda não distingue "robô ainda não
  existia" de "dado do robô está ausente" — ambos aparecem hoje como
  `NaN`.
- 6 das 7 políticas nomeadas de retirada de capital não estão
  implementadas (fórmula literal ainda não decidida).
- Análise de run-up / barreiras de drawdown não está implementada.
- Resultados históricos e simulados não implicam performance futura; as
  saídas são artefatos de pesquisa, não recomendações financeiras.
- A plataforma não executa ordens nem se conecta a uma corretora.

## Roadmap

- [ ] Adicionar CI (testes automatizados em cada push/PR)
- [ ] Implementar as políticas de retirada restantes assim que suas
      fórmulas forem decididas
- [ ] Adicionar um sinal explícito de dado ausente no nível de portfólio
- [ ] Análise de run-up / barreiras de drawdown
- [ ] Persistir análises entre sessões

## Abordagem de desenvolvimento

Este projeto é desenvolvido com engenharia assistida por IA (Claude
Code). Ferramentas de IA apoiam a decomposição de requisitos,
implementação, criação de testes, revisão e documentação; definições de
domínio, convenções financeiras, critérios de validação e a aceitação
final continuam sendo minha responsabilidade.

O desenvolvimento segue um workflow de TDD obrigatório para qualquer
coisa que toque em cálculo financeiro (`AGENTS.md`): um teste que falha é
escrito primeiro, confirmado que falha pelo motivo certo, e só então a
implementação mínima é adicionada. Casos extremos descobertos pelo
caminho — como um bug de reconstrução de trades que mesclava trades entre
instrumentos diferentes — viram testes de regressão, não só um conserto
esquecido.

## Estrutura do repositório

- `src/tradefolio/` — biblioteca de cálculo (validação, custos,
  alinhamento de calendário, reconstrução de trades, métricas, drawdown,
  portfólio, orquestração). Ver `CLAUDE.md` para a arquitetura completa e
  as convenções de domínio.
- `report.py` — renderização do HTML/gráficos a partir dos dicts
  produzidos por `tradefolio.report_data`.
- `demo.py` — roda `report.py` sobre um histórico de ordens real de
  exemplo, sem precisar de dados próprios.
- `app.py` — app Streamlit ao vivo (upload/dados de exemplo, filtro de
  janela, simulação de contratos, modos Lab e Portfolio Builder).
- `dados_exemplo/` — CSVs de exemplo para o app Streamlit (separado de
  `tests/fixtures/`, que sustenta a suíte de testes).
- `sheet.py` — implementação original de referência (pré-`tradefolio/`);
  não é mais o caminho usado por `report.py`.
- `tests/` — suíte pytest (454 testes), incluindo `tests/fixtures/`
  (dados de exemplo e valores esperados, alguns conferidos manualmente
  contra o relatório nativo da Smarttbot).
- `AGENTS.md` — o workflow obrigatório para mudanças neste repositório
  (TDD, convenções financeiras, disciplina de escopo).
- `CLAUDE.md` — referência de arquitetura e convenções de domínio para
  assistentes de código com IA (e humanos).

## Licença

MIT — ver [LICENSE](LICENSE).
