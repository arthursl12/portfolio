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
- [x] "Identificar linhas com P&L" como checagem própria — já coberto por
  `diagnostico_ingestao`'s `linhas_com_resultado`
  (`Resultado (R$).notna()`, não apenas `Tipo == "saída"`); item marcado
  como pendente por engano numa rodada anterior desta mesma tarefa

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
- [ ] Distância para o limiar — não implementada como função própria (seria
  só `limiar - retorno`, trivial dado o que a tarefa 4.2 já expõe), mas
  não colocada em `monthly.py` pelo mesmo motivo arquitetural de 4.2: exige
  um `limiar` real (que depende de `StrategyConfiguration.minimum_margin`,
  fora do pipeline funcional por decisão do Épico 2)
- [ ] Vapo elegível — ainda bloqueado, Épico 7 (vapo) não existe;
  documentado como exclusão deliberada em `monthly.py`

---

## Épico 4 — Motor básico de métricas

### Tarefa 4.1 — Métricas de retorno
- [x] Lucro bruto/líquido, retorno acumulado, retorno anualizado, média/
  mediana diária, % dias positivos — `report_data.calcular_pagina1`,
  `metrics.retorno_anualizado`
- [x] Média/mediana **mensal** e % de **meses positivos** — não precisaram
  de função nova: `monthly.agregar_mensal` ganhou a coluna
  `liquido_por_contrato` (soma mensal, mesma base de `melhor_dia`/`pior_dia`)
  e as funções genéricas de `metrics.py` (`.mean()`/`.median()`/
  `taxa_positivos`) já funcionam sobre ela (AGENTS.md §8.1) — verificado
  contra `tests/fixtures/romanos_orders.csv` (16 meses). Ainda não ligado a
  `report_data`/registro de métricas
- [x] Lucro **por ativo** — `calcular_pagina1(diario, ordens=...)` (parâmetro
  `ordens` opcional, `None` por padrão — não quebra `app.py` nem os testes
  existentes que só passam `diario`) agora inclui `"lucro_por_ativo"`
  (`{"WIN": ..., "WDO": ...}`, escala bruta, não por contrato — ver nota na
  entrada do `metric_registry`). Verificado contra `orders_roboraiz.csv`
  real: WDO=2.303,50 / WIN=15.648,50. Consumo na UI (`app.py`) não foi
  feito — mexer na camada Streamlit está fora deste passo (AGENTS.md/
  CLAUDE.md: não tocar `app.py` para implementar cálculo core sem pedido
  explícito); o dado já está disponível para quando isso for pedido
- [x] Lucro **por dia operado** — `report_data.calcular_pagina1`'s
  `media_diaria_dias_operados` (`serie[diario["operou"]].mean()`), com
  entrada no `metric_registry`. Verificado contra o mini-fixture: média
  geral -15,50 (5 pregões) vs. média só dos operados -19,375 (4 pregões,
  um NO_TRADE excluído do denominador)

### Tarefa 4.2 — RLT (retorno sobre o limiar)
- [x] `limiar.rlt_acumulado`/`rlt_mensal`/`rlt_anualizado`/`rlt_movel(...,
  janela_meses)` — funções puras que recebem um `limiar` (float) já
  calculado, não recalculado por janela. Decisão de escala confirmada com
  o usuário (nova pergunta feita após decompor_limiar já existir):
  `minimum_margin` é da POSIÇÃO TOTAL, não por contrato — então RLT usa
  `diario['liquido']` (total), não `liquido_por_contrato`, e o
  `drawdown_serie` passado a `decompor_limiar` também deve ser o da série
  total ao calcular o limiar real de um robô. Verificado contra
  `orders_roboraiz.csv`: limiar=13.495,00 (minimum_margin=10.000, P95
  sobre drawdown total), RLT acumulado=1,3303
- [ ] Não ligado a `calcular_pagina1/2/3` automaticamente — decisão
  arquitetural deliberada: calcular um `limiar` real exige
  `StrategyConfiguration.minimum_margin` (Épico 2), e a decisão do Épico 2
  foi manter `domain.py` aditivo, sem realimentar o pipeline funcional
  (`daily.py`/`report_data.py` continuam exatamente como estavam). Quem
  tiver as duas peças (uma `StrategyConfiguration` e a saída de
  `calcular_pagina1/3`) compõe as funções de `limiar.py` externamente

### Tarefa 4.4 — Normalizar risco pelo limiar
- [x] `limiar.normalizar_por_limiar(valor, limiar)` — mesma função
  genérica que `rlt_acumulado` usa por baixo (AGENTS.md §8.1), aplicada a
  MDD, Pior dia, ES95, Ulcer, Pior mês em vez de retorno. Mesma decisão de
  não-wiring automático que 4.2 (mesmo motivo). Verificado contra
  `orders_roboraiz.csv`: MDD/L=-24,84%, Pior dia/L=-5,91%, ES95/L=-3,93%,
  Ulcer/L=8,13%, Pior mês/L=-10,74%

### Tarefa 4.3 — Métricas de risco
- [x] MDD, pior dia, VaR histórico, ES, Ulcer Index, TUW, maior sequência
  negativa — `drawdowns.py`, `metrics.py`
- [x] **Drawdown corrente** — `drawdowns.drawdown_corrente` (último valor da
  série, distinto do MDD histórico — confirmado com valores diferentes
  contra dados reais: -48,5 vs. -1.441,50 de MDD em Romanos)
- [ ] **Pior semana móvel** — granularidade semanal não existe (só diária/
  mensal)
- [x] **Pior mês** — mesma solução de 4.1: `monthly.agregar_mensal()["liquido_por_contrato"].min()`,
  nenhuma função nova precisou ser escrita
- [x] **Desvio padrão** e **downside deviation** como métricas nomeadas —
  `metrics.desvio_padrao`/`metrics.downside_deviation`; `sortino` refatorado
  para reusar `downside_deviation` em vez de duplicar o cálculo
- [x] **Tempo de recuperação** — `drawdowns.tempo_recuperacao_mediano`
  (mediana de `duracao_total_pregoes` só entre episódios recuperados;
  verificado contra Romanos: 32 episódios, 31 recuperados, mediana 4
  pregões), a partir dos dados já existentes em `drawdowns.calcular_episodios_drawdown`

### Tarefa 4.5 — Métricas de qualidade
- [x] Profit Factor, Sharpe, Sortino, Calmar, Recovery Factor, ganho médio,
  perda média, payoff, taxa de acerto — `metrics.py`
- [x] "Expectativa por operação" — `expectancia_por_trade` em
  `calcular_pagina2` (`metrics.expectancia(trades["resultado_liquido"])`),
  com entrada no `metric_registry` — totalmente ligado, não só a função

---

## Épico 5 — Qualidade da curva

Implementado em `src/tradefolio/concentracao.py`. Nenhuma função nova
precisou tocar `report_data.py` (ainda não ligado lá — só as funções de
cálculo existem e estão testadas, mesmo padrão de 3.1/4.1).

### Tarefa 5.1 — Concentração positiva
- [x] `participacao_top_n(serie, n)` — genérica (AGENTS.md §8.1), serve para
  dias e meses. Deliberadamente NÃO limitada a [0,1]: >100% é sinal real de
  concentração patológica, não erro a esconder (a própria "lâmina ideal.pdf"
  §9 usa isso como exemplo de alerta). Verificado contra Romanos.

### Tarefa 5.2 — Resultado removendo eventos
- [x] `resultado_sem_top_n(serie, n)` (genérica, dia ou mês) e
  `resultado_antes_dos_ultimos_n_dias(serie, n)` (posicional, só dia —
  "últimos N dias" é cronológico, não por ranking de valor)

### Tarefa 5.3 — Detectar "curva salva recentemente"
- [x] `detectar_alertas_curva` — as 3 regras determinísticas do PDF
  (`NEGATIVE_BEFORE_LAST_60_DAYS`, `PROFIT_SAVED_BY_BEST_MONTH`,
  `TOP3_EXCEEDS_TOTAL_PROFIT`), schema de dict compatível com o épico 17
  (warning_code/severity/metric/observed_value/threshold/message).
  Confirmado que Romanos (robô real, saudável) não dispara nenhum alerta —
  guarda contra falso-positivo

### Tarefa 5.4 — Permanência abaixo do zero
- [x] `pct_dias_abaixo_de_zero`, `primeira_data_positiva`,
  `ultima_data_negativa`, `pregoes_desde_consolidacao_positiva` —
  verificado contra Romanos (4 de 312 dias negativos, consolidado há 300
  pregões) e um caso onde a amostra termina ainda negativa (retorna 0, não
  inventa uma consolidação que não aconteceu)

### Tarefa 5.5 — Dividir em subperíodos
- [x] `escolher_numero_de_blocos` (3 blocos 6-12m, 4 blocos 12-24m, semestres
  além disso) + `dividir_em_subperiodos` + `metricas_por_subperiodo`
  (lucro/MDD/PF/% dias positivos por bloco). Blocos por CONTAGEM DE
  PREGÕES, não mês-calendário. Três coisas do épico deliberadamente não
  implementadas (documentadas no código, não inventadas): alinhamento a
  "anos-calendário" (exigiria decidir o tratamento de ano parcial nas
  bordas), RLT por bloco (bloqueado pelo Épico 6), e "estabilidade" (termo
  nunca definido no PDF-fonte)

---

## Épico 6 — Motor de limiar

Completo dentro do que o usuário decidiu. Duas ambiguidades do PDF foram
resolvidas pelo usuário (não inventadas): percentil da cauda é um toggle
(P95 **e** P99 suportados, não um só hardcoded) e reserva operacional é
`% de minimum_margin` (não um valor fixo em R$). `src/tradefolio/limiar.py`.

### Tarefa 6.1 — Decomposição do limiar
- [x] `limiar.decompor_limiar(minimum_margin, drawdown_serie, meses_historico,
  percentil_cauda=95|99, fracao_reserva_operacional, increment=None)` —
  `limiar_bruto = minimum_margin + tail_drawdown_reserve + operational_reserve`,
  onde `tail_drawdown_reserve` já embute o prêmio por histórico curto
  (`uncertainty_premium` é exposto separado = a parte que o multiplicador
  soma acima do valor bruto do percentil). Verificado contra
  `orders_roboraiz.csv` real: P95=-1247,50 / P99=-1550,97 por contrato,
  42,8 meses de histórico → multiplicador 1.0 (sem prêmio)
- [x] `drawdown_serie` é recebida pronta (não recalculada aqui) — a decisão
  de qual série "deteriorada" ou não usar fica com o chamador; o motor de
  deterioração (Épico 8) não existe ainda, então só a série não-deteriorada
  está disponível hoje

### Tarefa 6.2 — Perfis de limiar
- [~] Não implementado como funções próprias — decisão deliberada (nenhuma
  abstração além do necessário): um "perfil" é só uma escolha fixa de
  `percentil_cauda`/`fracao_reserva_operacional` passada a `decompor_limiar`.
  Técnico ≈ `fracao_reserva_operacional=0`; Histórico ≈ `percentil_cauda=95`;
  Prudente ≈ `percentil_cauda=99` (+ série deteriorada quando o Épico 8
  existir); Personalizado ≈ os parâmetros livres já expostos. Quem montar o
  seletor de perfil na camada de relatório/UI mapeia nome → esses parâmetros
- [ ] Perfil "Prudente" com MDD deteriorado — bloqueado pelo Épico 8
  (deterioração), que não existe

### Tarefa 6.3 — Prêmio por histórico curto
- [x] `limiar.history_uncertainty_multiplier(months)` — os degraus exatos do
  PDF, documentado como política configurável, não "verdade estatística"

### Tarefa 6.4 — Arredondamento
- [x] `limiar.arredondar_limiar(valor_bruto, increment, margem=None)` —
  incremento absoluto (R$500/R$1.000) ou fração da margem

### Tarefa 6.5 — Explicar o resultado
- [x] `decompor_limiar` já retorna cada termo separado (minimum_margin,
  tail_drawdown_reserve, uncertainty_premium, uncertainty_multiplier,
  operational_reserve, limiar_bruto, limiar_recomendado se `increment`
  informado) — satisfaz "mostrar a decomposição, não só o número final"
  sem precisar de uma estrutura de exibição separada

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
