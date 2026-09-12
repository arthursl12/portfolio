# Tasks — Épicos 0–6

Derived from `prompts/tarefas e epicos.pdf` (Épicos 0–6 only, per request) and
cross-checked against the current codebase so status reflects what's
actually implemented, not what's planned. `[x]` = done, `[~]` = partially
done (gap noted), `[ ]` = not started. File/function names point at the
existing implementation or the natural place to add new code.

---

## Épico 0 — Contratos e metodologia

### Tarefa 0.1 — Dicionário oficial de métricas
- [x] `MetricSpec` dataclass (id, nome, pagina, fórmula, frequência, unidade,
  origem, versao_etapa, campos_necessários, tratamento_dado_ausente,
  tratamento_custos, interpretação, limitações) — `src/tradefolio/metric_registry.py`
- [x] Um `MetricSpec` por métrica emitida por `calcular_pagina1/2/3`, com
  exclusões documentadas (`ARTEFATOS_DE_DADOS_EXCLUIDOS`) para chaves que são
  tabelas/séries brutas, não métricas nomeadas
- [x] Teste que falha se `calcular_pagina1/2/3` ganhar uma chave nova sem
  entrada correspondente no registro — `tests/test_metric_registry.py`
  (`test_toda_chave_de_pagina1/2/3_tem_entrada_no_registro...`), o critério
  de aceite "nenhuma métrica pode existir apenas no componente visual" já
  está imposto, não só prometido

### Tarefa 0.2 — Separar tipos de informação
- [x] `ORIGENS_VALIDAS` (observed/calculated/simulated/user_input/policy/
  recommendation) e campo `origem` em todo `MetricSpec` — `metric_registry.py`
- [ ] Aplicar a mesma distinção fora do registro de métricas: quando o limiar
  (Épico 6) e políticas de usuário existirem, garantir que value/origin nunca
  se misturem em nenhum dict retornado à UI (reforça o princípio, não é só
  um artefato do registro)

### Tarefa 0.3 — Versionar a metodologia
- [x] `VERSOES` dict com uma versão por etapa implementada, `None` explícito
  para etapas não implementadas — `src/tradefolio/versions.py`
- [ ] Adicionar versão nova (não sobrescrever) toda vez que uma fórmula
  mudar — processo a seguir daqui pra frente, não uma tarefa de código única

---

## Épico 1 — Ingestão e normalização

### Tarefa 1.1 — Parser para CSV da SmarttBot
- [x] Delimitador `;`, decimal BR, data/hora `dd/mm/yyyy / HH:MM:SS` —
  `src/tradefolio/loaders.py`
- [x] Distinguir entrada/saída, extrair quantidade executada, preservar `#`
  original, detectar duplicatas — `loaders.py` + `validation.py`
- [x] BOM UTF-8 (`encoding="utf-8-sig"`) e detecção de delimitador
  (`;`/`,`, fallback `;`) — `loaders.detectar_delimitador`
- [x] **Manter ordens canceladas** — `Status` (separado de `Tipo`) agora é
  coluna obrigatória; valores reais confirmados: `executada`/`cancelada`/
  `expirada` (`dados_exemplo/orders_roboraiz.csv`: 213 canceladas + 1
  expirada, verificado end-to-end). Ordens não executadas são mantidas em
  `ordens` mas excluídas de `agregar_diario`, `reconstruir_trades` (corrigido
  um bug real: uma ordem cancelada com posição já em 0 criava um trade
  fantasma de duração zero) e `detectar_contratos_referencia`
- [ ] "Identificar linhas com P&L" como checagem própria (hoje implícito em
  `Tipo == "saída"`, não uma validação/contagem explícita)

### Tarefa 1.2 — Perfis de importação
- [ ] Interface comum `OrderImporter` (`can_parse`/`parse`/`diagnostics`) —
  não existe; hoje `carregar_ordens` é uma função única específica da
  SmarttBot
- [ ] Importador genérico de CSV
- [ ] Importador de formato manual padronizado
- [ ] Critério de aceite: reimportar o mesmo arquivo não duplica ordens
  (depende de um identificador estável — `#` já serve para isso dentro de um
  arquivo, mas não há noção de "já importado antes" entre execuções)

### Tarefa 1.3 — Diagnóstico de ingestão
- [x] Todos os 8 códigos determinísticos do PDF: `INVALID_DATE`,
  `EXIT_WITHOUT_PNL`, `DUPLICATE_ORDER`, `UNKNOWN_STATUS`, `UNKNOWN_ASSET`,
  `QUANTITY_MISMATCH`, `INVALID_MONETARY_VALUE` (`validation.py`,
  `loaders.parse_valor_br`) e `INCOMPLETE_MONTH` (`monthly.py`) —
  verificado contra os 4 CSVs reais (só Romanos e Robô Raiz emitem
  `EXIT_WITHOUT_PNL`; nenhum emite os demais, que dependem de dados que
  não existem nas amostras atuais)
- [x] Função de relatório agregado — `validation.diagnostico_ingestao(ordens)`,
  verificado contra os 2 CSVs reais com resultado (Romanos e Robô Raiz);
  os números de exemplo do PDF-fonte não batem exatamente contra
  orders_roboraiz.csv em nenhuma definição testada (nem "só executadas" nem
  "todas as linhas") — tratado como ilustrativo, não perseguido

### Tarefa 1.4 — Armazenar original e processado
- [ ] Camadas `raw/` / `normalized/` / `analytics/` / `reports/` — não existe;
  hoje tudo é recomputado em memória a partir do caminho do CSV a cada
  chamada, nada é persistido
- [ ] Decisão de tecnologia (DuckDB/Parquet vs. arquivos simples) antes de
  implementar

---

## Épico 2 — Modelo de domínio

Escopo decidido com o usuário: camada fina de metadados (dataclasses)
aditiva sobre o pipeline funcional existente — `daily.py`/`metrics.py`/
`drawdowns.py`/etc. continuam exatamente como estão, nada foi reescrito.
`src/tradefolio/domain.py`.

### Tarefa 2.1 — Entidades fundamentais
- [x] `Strategy`, `StrategyConfiguration` (+ `PositionLeg`), `AnalysisRun`,
  `DataQualityIssue`, `MetricResult` — dataclasses simples (`frozen=True`),
  sem Pydantic (nada aqui precisa de validação de runtime além da que
  `tradefolio.validation` já faz rio acima)
- [ ] Deliberadamente não implementados (documentado em `domain.py`, não
  omitido): `StrategyVersion` (nada rastreia versão de código ainda),
  `Order`/`DailyResult`/`MonthlyResult` (já são os DataFrames existentes —
  envolvê-los duplicaria dado sem nova capacidade), `ThresholdPolicy`/
  `WithdrawalPolicy` (Épicos 6/7), `Portfolio`/`PortfolioAllocation`
  (Épico 10), `SimulationRun` (Épico 8)

### Tarefa 2.2 — Distinguir estratégia, versão e configuração
- [x] `StrategyConfiguration.legs` (uma `PositionLeg` por raiz de ativo, não
  um único `contratos_referencia` escalar — generaliza para robôs
  multi-ativo), `minimum_margin`, `valid_from`/`valid_to`
- [x] `configuracao_a_partir_da_deteccao` liga a `detectar_contratos_referencia`
  existente — rodada POR PERNA (ativo_raiz), não sobre o CSV inteiro.
  **Achado real ao testar contra `orders_roboraiz.csv`**: mesmo por perna,
  WDO não tem quantidade dominante (79,4%, abaixo do limiar de 90%) — esse
  robô mudou de tamanho de posição ao longo do histórico (confirmado pela
  própria "lâmina ideal.pdf": "Alteração de 1 WDO para 2 WDO"). A função
  propaga o erro em vez de forçar um número — uma única configuração para
  o período inteiro genuinamente não descreve esse robô; o próximo passo
  natural (não implementado) seria detectar os pontos de mudança e gerar
  múltiplas `StrategyConfiguration` com `valid_from`/`valid_to` diferentes

### Tarefa 2.3 — Períodos de validade
- [x] `valid_from`/`valid_to`/`recorded_at`/`source` em `StrategyConfiguration`
  — a única entidade das cinco implementadas que é genuinamente mutável ao
  longo do tempo; `AnalysisRun`/`DataQualityIssue`/`MetricResult` são
  registros pontuais (têm `executed_at`, não uma faixa de validade)

---

## Épico 3 — Reconstrução das séries

### Tarefa 3.1 — Consolidar P&L diário
- [x] Data, P&L total, quantidade, operou, número de trades, custos, líquido
  — `daily.agregar_diario` + `alignment.preencher_calendario_b3`
- [x] **P&L por ativo e quantidade por ativo** — `daily.agregar_diario_por_ativo`,
  agrupa por (data, raiz do ativo) via `validation.extrair_raiz_ativo`
  (raiz, não o código completo do contrato, para não quebrar a série por
  rolagem de vencimento). Soma por ativo reconcilia exatamente com o total
  de `agregar_diario` contra `dados_exemplo/orders_roboraiz.csv` (WIN+WDO
  reais), e o bruto total (R$19.781) bate com o exemplo numérico da própria
  "lâmina ideal.pdf" (seção 23) para esse robô -- confirmação cruzada
  independente. Ainda não ligado a `report_data`/`app.py` (só a função
  existe, nada consome o breakdown por ativo ainda -- ver Épico 12 da
  lâmina ideal para o próximo consumidor natural)

### Tarefa 3.2 — Calendário correto
- [x] Calendário oficial B3 via `pandas_market_calendars` (já além do MVP —
  isso já inclui feriados reais, não é só dias úteis genéricos) —
  `alignment.py`
- [x] Dias ausentes como zero, com flag `operou` — `alignment.py`
- [x] Mês incompleto sinalizado — `monthly.py`'s `mes_completo`
- [ ] Pregões especiais / mudanças de horário (versão madura, não MVP —
  depende de cobertura do `pandas_market_calendars`, não verificado)

### Tarefa 3.3 — Três tipos de zero
- [x] `NO_TRADE` (`operou=False`) e `ZERO_RESULT` (`operou=True` e
  `resultado_zero=True`, base `bruto`) — `alignment.py`
- [ ] `MISSING_DATA` — deliberadamente não implementado (documentado no
  próprio módulo): precisa de um sinal independente que hoje não existe
  para um único robô (ex.: janela de existência do robô a nível de
  portfólio, Épico 10)

### Tarefa 3.4 — Consolidar resultados mensais
- [x] P&L, custo, líquido, dias operados, trades, melhor/pior dia, mês
  completo/parcial — `monthly.agregar_mensal`
- [ ] Distância para o limiar, vapo elegível — bloqueados por Épico 6 (limiar)
  e Épico 7 (vapo), documentado como exclusão deliberada em `monthly.py`

---

## Épico 4 — Motor básico de métricas

### Tarefa 4.1 — Métricas de retorno
- [x] Lucro bruto/líquido, retorno acumulado, retorno anualizado, média/
  mediana diária, % dias positivos — `report_data.calcular_pagina1`,
  `metrics.retorno_anualizado`
- [ ] Média/mediana **mensal** (existe por mês em `monthly.py`, falta agregar
  a série mensal em si — `monthly_liquido.mean()`/`.median()`)
- [ ] % de **meses positivos** (mesma ideia, sobre a série de `monthly.py`)
- [ ] Lucro **por ativo** — dado-base pronto desde 3.1
  (`daily.agregar_diario_por_ativo`), falta expor como métrica nomeada em
  `calcular_pagina1/2/3` (ex. `agregar_diario_por_ativo(...).groupby("ativo_raiz")["liquido"].sum()`)
- [ ] Lucro **por dia operado** (excluindo dias sem trade do denominador —
  hoje `media_diaria` divide pelo total de pregões, não só pelos operados)

### Tarefa 4.2 — RLT (retorno sobre o limiar)
- [ ] Acumulado/mensal/anualizado/móvel 3-6-12m — bloqueado por Épico 6
  (não existe "limiar" ainda para servir de denominador)

### Tarefa 4.3 — Métricas de risco
- [x] MDD, pior dia, VaR histórico, ES, Ulcer Index, TUW, maior sequência
  negativa — `drawdowns.py`, `metrics.py`
- [ ] **Drawdown corrente** (último valor da série de drawdown, distinto do
  MDD histórico) — não exposto como métrica nomeada hoje
- [ ] **Pior semana móvel** — granularidade semanal não existe (só diária/
  mensal)
- [ ] **Pior mês** — trivial a partir de `monthly.py` (`liquido.min()`), mas
  ainda não é uma métrica nomeada em `calcular_pagina1/2/3`
- [ ] **Desvio padrão** e **downside deviation** como métricas nomeadas e
  testadas isoladamente (hoje usadas inline dentro de `sharpe`/`sortino`,
  não expostas)
- [ ] **Tempo de recuperação** como métrica de topo — os dados já existem em
  `drawdowns.calcular_episodios_drawdown` (`duracao_total_pregoes`), falta
  agregar/expor um número único (ex. mediana entre episódios recuperados)

### Tarefa 4.4 — Normalizar risco pelo limiar
- [ ] MDD/L, Pior dia/L, ES95/L, Ulcer/L, Pior mês/L — bloqueado por Épico 6

### Tarefa 4.5 — Métricas de qualidade
- [x] Profit Factor, Sharpe, Sortino, Calmar, Recovery Factor, ganho médio,
  perda média, payoff, taxa de acerto — `metrics.py`
- [ ] "Expectativa por operação" como métrica de página 2 nomeada (hoje
  calculável via `metrics.expectancia(trades["resultado_liquido"])` mas não
  incluída no dict de `calcular_pagina2`)

---

## Épico 5 — Qualidade da curva

Nenhuma tarefa implementada — módulo novo, sugestão: `src/tradefolio/concentracao.py`.

### Tarefa 5.1 — Concentração positiva
- [ ] Participação do melhor dia, 5 melhores dias, 10 melhores dias, melhor
  mês, 3 melhores meses, últimos 60 dias (todos como % do lucro total)

### Tarefa 5.2 — Resultado removendo eventos
- [ ] Lucro sem melhor dia / sem 5 melhores dias / sem melhor mês / sem 3
  melhores meses / sem últimos 60 dias

### Tarefa 5.3 — Detectar "curva salva recentemente"
- [ ] Regras determinísticas: `NEGATIVE_BEFORE_LAST_60_DAYS`,
  `PROFIT_SAVED_BY_BEST_MONTH`, `TOP3_EXCEEDS_TOTAL_PROFIT` — depende de
  5.1/5.2 primeiro (precisa dos números de concentração para avaliar os
  limiares das regras)

### Tarefa 5.4 — Permanência abaixo do zero
- [ ] % de dias com equity acumulada negativa, primeira passagem para
  positivo, última passagem por negativo, dias desde a consolidação
  positiva — dados-base (`equity`) já existem em `drawdowns.curva_equity`,
  falta a função de agregação específica

### Tarefa 5.5 — Dividir em subperíodos
- [ ] Blocos de tamanho semelhante conforme duração do histórico (3 blocos
  p/ 6-12m, 4 trimestres p/12m, semestres, anos-calendário) mostrando lucro/
  MDD/PF/meses positivos/RLT/estabilidade por bloco — RLT bloqueado por
  Épico 6, o resto é composição do que já existe em `report_data.py`
  aplicado a cada bloco

---

## Épico 6 — Motor de limiar

Nada implementado — bloqueia partes de 4.2, 4.4, 5.5 e de todo o Épico 7
(vapo) adiante. Sugestão: `src/tradefolio/limiar.py`.

### Tarefa 6.1 — Decomposição do limiar
- [ ] `limiar = margem_minima + reserva_drawdown_cauda + premio_incerteza + reserva_operacional`
- [ ] Decisão prévia obrigatória (AGENTS.md §8/§24): fonte de cada termo —
  P95/P99 de qual série, deteriorado ou não, arredondamento — antes de
  codificar (não adivinhar a fórmula concreta a partir do esqueleto do PDF)

### Tarefa 6.2 — Perfis de limiar
- [ ] Técnico (só margem mínima)
- [ ] Histórico (margem + MDD P95 histórico)
- [ ] Prudente (margem + MDD P99 deteriorado + arredondamento)
- [ ] Personalizado (percentil/horizonte/deterioração/reserva/arredondamento/
  custos configuráveis pelo usuário)

### Tarefa 6.3 — Prêmio por histórico curto
- [ ] `history_uncertainty_multiplier(months)` com os degraus do PDF —
  documentar explicitamente como política configurável, não "verdade
  estatística" (o próprio PDF exige isso)

### Tarefa 6.4 — Arredondamento
- [ ] `recommended_threshold = ceil(raw_threshold / increment) * increment`,
  incrementos configuráveis (R$500, R$1.000, % da margem)

### Tarefa 6.5 — Explicar o resultado
- [ ] Estrutura de decomposição para exibição (margem técnica / MDD P99
  deteriorado / reserva operacional / total) — camada de apresentação, só
  depois que 6.1–6.4 existirem

---

## Lacunas transversais que aparecem em mais de um épico

- ~~**Coluna `Ativo` nunca lida**~~ — resolvido (`daily.agregar_diario_por_ativo`
  + `validation.extrair_raiz_ativo`); ainda falta expor em `report_data`
  (4.1) e consumir no Épico 12 da lâmina ideal (comparação de ativos internos).
- ~~**Coluna `Status` nunca lida**~~ — resolvido (1.1: ordens canceladas mantidas
  e excluídas da agregação; `UNKNOWN_STATUS` em 1.3).
- **Nenhuma persistência** — Épico 1.4 é pré-requisito de fato para Épico 2
  (entidades com `AnalysisRun`/histórico) fazer sentido; hoje não há "onde"
  guardar uma `AnalysisRun`.
