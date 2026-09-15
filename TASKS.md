# Tasks — Épicos 0–11

Derived from `prompts/tarefas e epicos.pdf` and cross-checked against the
current codebase so status reflects what's actually implemented, not what's
planned. `[x]` = done, `[~]` = partially done (gap noted), `[ ]` = not
started. File/function names point at the existing implementation or the
natural place to add new code.

Épicos 7–11 (vapo, Monte Carlo/robustez, run-up/barreiras, portfólio,
lâmina visual no Streamlit) are pure **planning** — nothing in them is
implemented yet. Each task below notes what already exists to build on,
what would need a genuine decision before any code is written (AGENTS.md
§8/§24: never invent a financial convention silently), and cross-épico
dependencies. Where `prompts/tarefas e epicos.pdf` gives a concrete
formula/example, it's cited directly instead of guessed at. Épicos 12+
(API para IA, camada de IA, score e triagem) were not requested and are not
covered here.

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
- [x] Interface comum `OrderImporter` (`can_parse`/`parse`/`diagnostics`) —
  `src/tradefolio/importers.py`, ABC (não Protocol -- `abstractmethod`
  garante em tempo de instanciação que uma subclasse implementa os três
  métodos). `SmarttbotOrderImporter` envolve `loaders.carregar_ordens` +
  `validation.diagnostico_ingestao` sem duplicar lógica; `can_parse` só lê
  o cabeçalho (reusa `loaders.ler_primeira_linha`, extraída de
  `detectar_delimitador` para não duplicar) e checa
  `COLUNAS_OBRIGATORIAS`, sem parsear o arquivo inteiro
- [ ] Importador genérico de CSV — não implementado: nenhum formato
  concreto foi especificado (AGENTS.md §8: não inventar um formato para
  preencher a tarefa)
- [ ] Importador de formato manual padronizado — mesmo motivo
- [ ] Critério de aceite: reimportar o mesmo arquivo não duplica ordens —
  bloqueado pelo Épico 1.4 (precisa de um "já importado antes" durável
  entre execuções, que é justamente a persistência ainda sem decisão de
  tecnologia); `#` já resolve duplicata DENTRO de um arquivo
  (`DUPLICATE_ORDER`), não entre execuções separadas

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
- [x] `configuracao_a_partir_da_deteccao` liga a `daily.contratos_referencia_por_ativo`
  — rodada POR PERNA (ativo_raiz), não sobre o CSV inteiro.
  **Achado real ao testar contra `orders_roboraiz.csv`**: mesmo por perna,
  WDO não tem quantidade dominante sobre o histórico INTEIRO (79,4%,
  abaixo do limiar de 90%) — esse robô mudou de tamanho de posição ao
  longo do histórico (confirmado pela própria "lâmina ideal.pdf":
  "Alteração de 1 WDO para 2 WDO"). A função propaga o erro em vez de
  forçar um número quando isso acontece.
- [x] **Resolvido (parcialmente, ver seção "Contratos de referência para
  robôs multi-ativo com proporção fixa" abaixo)**: `dias_recentes`
  opcional em `configuracao_a_partir_da_deteccao`/
  `contratos_referencia_por_ativo` restringe a detecção a uma janela
  recente, recuperando a proporção ATUAL (3 WIN + 2 WDO, 90 dias) sem
  precisar segmentar a história inteira. O próximo passo mais completo
  (não implementado) continua sendo detectar os pontos de mudança e
  gerar múltiplas `StrategyConfiguration` com `valid_from`/`valid_to`
  diferentes -- útil para analisar PERÍODOS PASSADOS com a config certa
  de cada um, não só "qual é a config de agora"

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

## Épico 7 — Motor de vapo

Tarefas 7.1/7.3/7.4 implementadas em `src/tradefolio/vapo.py`. Modelo do
motor resolvido sem precisar perguntar ao usuário: "saldo" é uma equity
corrente (carrega de mês para mês), e "déficit anterior" é uma leitura
derivada (`max(0, limiar - saldo_inicial)`) para exibição, já embutida em
`saldo_antes_do_vapo` -- verificado numericamente contra
`dados_exemplo/orders_roboraiz.csv` antes de fixar a interpretação (ver
docstring do módulo). `VERSOES["vapo"]` = `"vapo_v1"`.

### Tarefa 7.1 — Política de piso fixo
- [x] `PoliticaPisoFixo.calcular_vapo_bruto` = `max(0, saldo_antes_do_vapo
  - limiar)` -- a única das 7 políticas da tarefa 7.2 com fórmula literal
  no PDF-fonte ("100% do excedente" acima do limiar/piso)

### Tarefa 7.2 — Suportar políticas alternativas
- [x] Interface comum `PoliticaVapo` (ABC, mesmo padrão de
  `tradefolio.importers.OrderImporter`, épico 1.2) -- `gerar_serie_vapo`
  (7.3) compõe qualquer política sem conhecer sua fórmula interna
- [ ] As outras 6 políticas nomeadas no PDF-fonte (percentual do
  excedente; teto mensal; percentual do lucro; somente mês positivo;
  preservação do capital inicial; reserva tributária/acumulação para
  aumento de mão) — cada uma precisa de uma fórmula explícita decidida
  ANTES de codificar (AGENTS.md §8): "percentual do lucro", por exemplo,
  não diz se é lucro bruto ou líquido, mensal ou acumulado. Nenhuma foi
  implementada por não ter fórmula literal no PDF-fonte; adicionar
  implementando `PoliticaVapo` quando essas decisões forem tomadas.

### Tarefa 7.3 — Gerar série de vapo
- [x] `vapo.gerar_serie_vapo(mensal, limiar, politica, aliquota_fiscal=0.0,
  saldo_inicial=0.0)` -- motor mensal completo (saldo_inicial, P&L bruto/
  custos/líquido de `monthly.agregar_mensal`, saldo_antes_do_vapo,
  déficit_anterior, vapo_bruto via `PoliticaVapo`, provisão fiscal,
  vapo_líquido, saldo_final). `saldo_final` desconta o vapo BRUTO, não o
  líquido (a provisão fiscal sai da conta de trading, só o valor
  distribuível ao dono é menor). Escala TOTAL da posição (mesma decisão
  já resolvida para limiar/RLT). Verificado contra `orders_roboraiz.csv`
  com limiar=R$13.500: 44 meses, primeiro vapo só em 2026-03 (R$388,50),
  total de vapo bruto no período R$4.452,00 em 5 meses
- [x] Alíquota fiscal (`aliquota_fiscal`) tem default `0.0` explícito —
  nunca um imposto inventado; 0% é a escolha padrão honesta, não um
  placeholder

### Tarefa 7.4 — Criar métricas do vapo
- [x] `vlt_acumulado`/`vlt_mensal` — reuso direto de
  `limiar.rlt_acumulado`/`rlt_mensal` (mesma fórmula genérica valor/
  limiar, AGENTS.md §8.1), sem nenhuma fórmula nova
- [x] `frequencia_meses_com_vapo` — reuso de `metrics.taxa_positivos`
- [x] `maior_vapo` — `.max()` direto
- [x] `maior_sequencia_sem_vapo` — precisou de uma extração pequena:
  `metrics.maior_sequencia` só cobria `>0`/`<0`, não `==0` (vapo nunca é
  negativo, "sem vapo" é exatamente zero); extraído
  `metrics.maior_sequencia_mascara(mascara)` como o núcleo genérico
  (AGENTS.md §8.1), com `maior_sequencia` refatorado para chamá-lo —
  refactor comportamento-preservado, suite completa ainda verde
- [x] `meses_positivos_sem_vapo_por_deficit` — cruza `pnl_liquido > 0`
  com `vapo_bruto == 0` na série de 7.3 (o "um mês positivo não significa
  necessariamente dinheiro distribuível" da "lâmina ideal.pdf" §6);
  verificado: 28 dos 44 meses do Robô Raiz
- [x] `deficit_atual` — `max(0, limiar - saldo_final.iloc[-1])`, mesma
  normalização de 4.4

### Tarefa 7.5 — Criar calendário visual
- [ ] Camada de apresentação (app.py/report.py), bloqueada por 7.3/7.4
  terem dados para mostrar. O PDF-fonte sugere Plotly/streamlit-aggrid —
  isso seria uma dependência nova (AGENTS.md §18: mudança de dependência
  exige justificativa); avaliar primeiro se o `report.py`/matplotlib já
  usado no resto da lâmina dá conta de um calendário mensal colorido
  antes de adicionar uma biblioteca só para isso.

---

## Épico 8 — Monte Carlo e robustez

Tarefas 8.1/8.2/8.4 implementadas em `src/tradefolio/monte_carlo.py`.
`ORIGENS_VALIDAS` (metric_registry, épico 0.2) já incluía `"simulated"`
— a categoria de origem para tudo que este épico produz já estava
prevista, não precisou ser inventada agora. `VERSOES["monte_carlo"]` =
`"monte_carlo_v1"`.

### Tarefa 8.1 — Bootstrap diário sincronizado
- [x] `circular_block_bootstrap(dados, tamanho_bloco=1, ...)` — 8.1 é
  exatamente o caso especial `tamanho_bloco=1` de 8.2 (tarefa 8.2), uma
  função genérica só (AGENTS.md §8.1) em vez de duas implementações
  paralelas. Aceita `pd.Series` (um robô) ou `pd.DataFrame` (várias
  colunas sincronizadas na mesma linha sorteada -- ex.
  `daily.pivotar_liquido_por_ativo` para WIN+WDO; o mesmo padrão serve
  para portfólio, Épico 10, quando existir)
- [x] Universo de amostragem: decidido por composição, não hardcoded —
  a função reamostra o que quer que `dados` contenha; histórico inteiro
  vs. janela recente é escolha do chamador (o mesmo padrão já usado por
  `report_data.filtrar_por_janela` em todo o resto do código, nunca uma
  função de cálculo decide sua própria janela)

### Tarefa 8.2 — Circular block bootstrap
- [x] Blocos contíguos com wraparound (`% n`), tamanho de bloco como
  parâmetro livre (5/10/20/40 ou qualquer outro -- toggle, não um valor
  fixo, mesmo espírito do P95/P99 do limiar). Verificado que
  `tamanho_bloco == len(série)` produz uma rotação cíclica (não uma
  reamostragem i.i.d.), provando que a implementação preserva blocos
  contíguos de fato
- [x] `seed=None` gera uma semente verdadeira (`numpy.random.SeedSequence`)
  e a reporta em `ResultadoBootstrap.seed`, nunca escondida; reusar essa
  semente reproduz exatamente as mesmas trajetórias (verificado)
- [x] `incluir_dias_sem_operacao` (padrão `True`) — parâmetro explícito,
  não uma decisão silenciosa; para DataFrame, uma linha só é excluída se
  TODAS as colunas forem zero nela
- [x] Vetorizado com NumPy (sem laço Python por trajetória) — 5.000
  trajetórias × 252 pregões roda em ~17ms contra dados reais
  (`orders_roboraiz.csv`), bem abaixo do limite que motivaria a tarefa
  8.5 (processamento em background)

### Tarefa 8.3 — Cenários deteriorados
- [x] `src/tradefolio/deterioracao.py` — seis transformações
  independentes e compostáveis (Series in, Series out, sem função
  "combinada" especial — encadeiam por composição normal de Python):
  `reduzir_ganhos`, `ampliar_perdas`, `remover_melhores_dias`,
  `duplicar_piores_dias`, `aumentar_custos`, `aplicar_slippage`.
  `VERSOES["deterioracao"]` = `"deterioracao_v1"`.
- [x] `aumentar_custos(bruto, custo, fracao)` recebe as séries
  componentes (não o `diario` inteiro nem reusa `costs.custo_b3`
  diretamente — o "aumento" é sobre o custo já calculado, não sobre
  quantidade × tarifa) e recomputa o líquido — cobre os cenários
  "custos +50%/+100%" de "lâmina ideal.pdf" §10.
- [x] A grade 0%/10%/20%/30% de "lâmina ideal.pdf" §10 (redução de ganhos
  × aumento de perdas) é diretamente reproduzível encadeando
  `ampliar_perdas(reduzir_ganhos(serie, rg), ap)` e alimentando
  `monte_carlo.circular_block_bootstrap` — verificado contra
  `orders_roboraiz.csv` real: deterioração 0/0 → lucro mediano anual
  simulado +R$5.043 (6,7% prob. de prejuízo); 10/10 → +R$150 (48,6%);
  20/20 → -R$4.781 (92,1%) — o mesmo padrão qualitativo do exemplo do
  PDF-fonte (lucro caindo e virando negativo conforme a deterioração
  aumenta). O heatmap/tabela completo (16 células × Monte Carlo, com
  MDD P95/VLT mediano/meses com vapo por célula) não foi montado como
  função própria nesta rodada — só a composição em si foi verificada.
- [x] "Duplicação dos piores dias": decisão tomada e documentada (não
  deixada em aberto) — dobra o valor NO LUGAR (`× 2`), não insere uma
  data nova no calendário (que exigiria decidir onde ela entraria,
  quebrando o alinhamento com `alignment.preencher_calendario_b3`).

### Tarefa 8.4 — Produzir percentis
- [x] `resumo_trajetorias(resultado, minimum_margin=None, limiar=None)`
  — lucro P5/P25/P50/P75/P95 (direto, maior é melhor); MDD P50/P90/P95/
  P99 (reusa a MESMA convenção de `limiar.decompor_limiar`:
  `percentile(mdd, 100-p)`, não uma nova); probabilidade de prejuízo
  sempre calculada; probabilidade de tocar a margem/terminar abaixo do
  limiar só aparecem quando `minimum_margin`/`limiar` são informados
  (mesmo padrão do `ordens` opcional em `calcular_pagina1`). MDD por
  trajetória usa a mesma convenção peak-to-trough de `drawdowns.py`
  (`equity=cumsum`, `drawdown=equity-running_max`), vetorizada, não
  reimplementada
- [ ] Pior mês, TUW e VLT por trajetória NÃO implementados: "pior mês"
  precisaria de uma convenção nova para atribuir "meses" a uma
  trajetória sintética sem calendário real (candidato natural: blocos de
  21 pregões, já que `DIAS_UTEIS_ANO_PADRAO=252` implica 252/12=21 --
  mas isso não foi confirmado com o usuário); TUW por trajetória
  precisaria vetorizar `drawdowns.time_under_water_max` (hoje um laço
  por trajetória); VLT exigiria compor com o motor de vapo (Épico 7)
  sobre cada trajetória simulada. Deixados como próximo passo natural,
  não fórmulas inventadas às pressas

### Tarefa 8.5 — Processar em background
- [ ] Decisão de arquitetura, mesma categoria da Épico 1.4 (pilha de
  persistência) — genuinamente bloqueada até 1.4 ser decidido, já que
  "progresso salvo no DuckDB" (sugestão do próprio PDF) pressupõe a
  escolha de tecnologia de 1.4. Alternativa: um MVP descartável
  (`concurrent.futures.ProcessPoolExecutor`, cache em memória) marcado
  explicitamente como não-durável até 1.4 ser resolvido.

### Tarefa 8.6 — Cachear resultados
- [ ] A chave de cache (hash da série, versão do modelo, seed,
  trajetórias, horizonte, bloco, deterioração, custos, política de vapo)
  espelha o que `tradefolio.versions.VERSOES` já faz por etapa — extensão
  natural: quando 8.1-8.3 existirem, `VERSOES["monte_carlo"]` deixa de
  ser `None` e essa string entra na chave. Ainda bloqueada pela decisão
  de armazenamento de 8.5.

---

## Épico 9 — Run-up e barreiras

Nada implementado. Nenhuma etapa "run_up"/"barreiras" existe ainda em
`tradefolio.versions.VERSOES` (diferente de vapo/monte_carlo/deterioração,
que já têm o placeholder `None`) — precisa ser adicionada quando este
épico começar. 9.1/9.2 são calculáveis sobre dados históricos, sem
depender do Épico 8; 9.3/9.4 dependem do motor de Monte Carlo existir.

### Tarefa 9.1 — Implementar maximum run-up
- [ ] Imagem espelhada de `drawdowns.calcular_episodios_drawdown`: em vez
  de maior queda desde um pico, maior alta desde um fundo. Candidato
  forte a reuso sem fórmula nova: verificar algebricamente se
  `calcular_episodios_drawdown(-equity)` com o sinal invertido já produz
  os episódios de run-up corretos, antes de escrever uma função paralela
  do zero (mesmo espírito de reuso desta sessão, ex. `rlt_*`/
  `normalizar_por_limiar` compartilhando uma única fórmula genérica).

### Tarefa 9.2 — Calcular melhores janelas
- [ ] Retorno máximo em janela MÓVEL (não blocos fixos contíguos como
  `concentracao.dividir_em_subperiodos`) para 5/21/63/126/252 pregões —
  `serie.rolling(n).sum().max()` por tamanho de janela. Função nova mas
  simples, genérica sobre `n` (um parâmetro, não cinco funções fixas —
  mesmo padrão de `limiar.rlt_movel`/`concentracao.metricas_por_subperiodo`).

### Tarefa 9.3 — Implementar barreira dupla
- [ ] **Bloqueada pelo Épico 8.** As saídas do PDF-fonte (probabilidade de
  atingir a barreira positiva primeiro, a negativa primeiro, nenhuma,
  tempo mediano) são inerentemente um resultado de tempo-de-primeira-
  passagem sobre trajetórias SIMULADAS, não algo calculável a partir de
  uma única série histórica. Não tentar implementar antes de 8.1/8.2
  existirem.

### Tarefa 9.4 — Usar barreiras para aumento de mão
- [ ] Depende de 9.3 (bloqueada) + do limiar (Épico 6, já disponível) —
  uma camada de decisão de dimensionamento de posição sobre as
  probabilidades de barreira, uma vez que existam.

---

## Épico 10 — Portfólio

Tarefas 10.1/10.2/10.6/10.7, e parte de 10.3/10.4, implementadas em
`src/tradefolio/portfolio.py` -- o maior gap arquitetural do projeto até
esta rodada (todo `tradefolio.*` operava sobre UM `ordens`/`diario` por
vez). `VERSOES["portfolio"]` = `"portfolio_v1"`.

### Tarefa 10.1 — Sincronizar estratégias por data
- [x] `portfolio.sincronizar_portfolio({nome: diario, ...})` — generaliza
  o padrão de `daily.pivotar_liquido_por_ativo` (por ativo dentro de um
  robô) para "por robô dentro de um portfólio". `pd.DataFrame({nome:
  diario["liquido"], ...})` já faz o alinhamento certo sozinho: pandas
  une os índices e preenche com NaN onde um robô não tem dado -- não
  com 0 (que já significa NO_TRADE dentro do range de vida daquele
  robô). Distingue "não operou" (0) de "ainda não existia" (NaN) sem
  nenhuma lógica nova. Verificado contra dados reais (resgat + gridhedge
  + romanos2, começos em datas diferentes): antes de gridhedge/romanos2
  existirem, as colunas deles são `NaN`, não `0`.
- [ ] MISSING_DATA continua não implementado -- mesma lacuna da tarefa
  3.3 (falta um sinal independente); "robô ausente quando outros do
  mesmo período têm dado" SERIA esse sinal, mas não foi usado para
  inferir MISSING_DATA nesta rodada (ficaria indistinguível de "ainda
  não existia" por enquanto).

### Escopo temporal padrão (pedido de acompanhamento do usuário, fora dos épicos do PDF-fonte)
- [x] `portfolio.restringir_janela_comum(largo)` -- corta `largo` para o
  intervalo em que TODOS os robôs já existiam (`largo.dropna()`, que já
  produz exatamente esse intervalo contíguo porque `sincronizar_portfolio`
  só gera NaN antes/depois da existência de um robô, nunca no meio --
  dias sem operação são 0). Levanta `ValueError` se não houver nenhum
  período de coexistência.
- [x] `contribuicao_marginal`/`otimizar_portfolio` ganharam
  `usar_janela_comum: bool = True` -- agora restringem CADA comparação/
  candidato à SUA PRÓPRIA janela comum (não à janela comum do portfólio
  completo) antes de pontuar. Isso muda o DEFAULT numérico dessas duas
  funções -- por isso `VERSOES["portfolio"]` foi de `_v1` para `_v2`
  (ver `versions.py`). União ainda disponível via `usar_janela_comum=False`,
  testada explicitamente (`test_contribuicao_marginal_uniao_explicita_
  preserva_comportamento_antigo`, `test_otimizar_portfolio_uniao_
  explicita_preserva_comportamento_antigo`).
- [x] Wireado como o padrão em ambas as UIs: `app.py` ganhou um radio
  "Escopo temporal das métricas do portfólio" no topo da seção (com
  `captions=` por opção, já que `st.radio`/`st.segmented_control` só
  suportam um `help=` único para o grupo inteiro, não por item --
  `captions` foi a forma nativa mais próxima de "hover por opção"
  disponível no Streamlit 1.63); `report.py` ganhou `--escopo-temporal
  {janela_comum,todos_os_dias}` (padrão `janela_comum`). Ambos afetam
  lucro/MDD/ES/correlação (todas as 6 variantes, herdado automaticamente
  já que todas operam sobre o `largo` já restringido)/limiar/RLT/
  contribuição marginal/otimização.
- [x] `captions=` também adicionado ao seletor de 5 variantes de
  correlação já existente (pedido explícito do usuário: "add hover
  information on these options").
- [x] Verificado contra dados reais (resgat+gridhedge+romanos2): janela
  comum = 11/06/2025 a 08/09/2026 (312 pregões) vs. união = 13/03/2024 a
  08/09/2026 (623 pregões); lucro combinado cai de R$64.320,93 (união)
  para R$41.619,93 (janela comum) -- a diferença é inteiramente o
  período em que resgat operava sozinho, antes dos outros dois
  existirem. Números idênticos entre `app.py` (via `AppTest`) e
  `report.py` (execução real do CLI).

### Tarefa 10.2 — Suportar quantidades e multiplicadores
- [x] `PortfolioAllocation(strategy_id, multiplier, active_from)` em
  `domain.py` -- dataclass irmão de `StrategyConfiguration`.
- [x] `sincronizar_portfolio(..., multiplicadores={"robo": fator, ...})`
  escala o `liquido` de cada robô ANTES de sincronizar -- a parte
  funcional de "suportar multiplicadores" (a dataclass é só o registro).

### Tarefa 10.3 — Calcular métricas agregadas
- [x] `portfolio.metricas_agregadas(largo)` -- lucro total, MDD, ES95,
  TUW máximo, pior dia, pior mês e lucro mensal (Series), tudo sobre a
  série COMBINADA (`serie_combinada`, soma com `skipna=True`: um robô
  ainda inexistente contribui 0, não contamina o total com NaN). `lucro
  mensal` é `serie_combinada.resample("ME").sum()`, NÃO
  `monthly.agregar_mensal` -- essa exige `bruto`/`custo`/`n_trades`/
  `liquido_por_contrato`, colunas sem significado agregado coerente
  entre robôs heterogêneos (inventar valores violaria AGENTS.md §8).
  Reusa `drawdowns`/`metrics` diretamente, nenhuma fórmula nova.
- [x] `portfolio.rlt_e_risco_portfolio(largo, limiar)` -- RLT acumulado/
  anualizado/mensal médio-mediano/móvel 3-6-12m e risco normalizado
  (MDD/ES95/pior dia/pior mês sobre o limiar), mesma forma de
  `report_data.calcular_pagina4` mas sobre a série combinada; recebe o
  limiar agregado já decidido (não recalcula). Verificado contra dados
  reais (resgat+gridhedge+romanos2, R$5.000/contrato, limiar agregado
  R$52.500): RLT acumulado 122,52%, anualizado 49,23%.
- [x] Margem total -- decisão: não virou função própria (é um
  `sum(minimum_margins.values())` de uma linha, já usado dentro de
  `limiar_agregado_portfolio`; uma função só para isso seria abstração
  sem necessidade, AGENTS.md).
- [x] Custo mensal por robô e custo total agregado -- pedido de
  acompanhamento do usuário ("e o custo mensal dos robôs do portfólio?").
  Cada robô no modo Portfólio agora tem sua própria tabela de custo
  mensal (mesmo editor por faixas do modo Robô único no `app.py`; um
  valor fixo `--robo CSV MARGEM N_CONTRATOS CUSTO_MENSAL` no CLI,
  mesma simplicidade já adotada por `--custo-mensal` no modo robo).
  Decisão de escala (documentada, diferente do modo Robô único de
  propósito, não por descuido): debitado sobre `n_contratos_robo` (o
  tamanho SIMULADO no portfólio), não sobre `contratos_referencia` (o
  detectado) -- no modo Robô único isso é uma limitação aceita (o
  `diario` nunca é reescalado lá), mas no modo Portfólio o `diario` já É
  reescalado para `n_contratos_robo` antes de qualquer outra coisa, então
  cobrar pela faixa do tamanho simulado é o correto, não uma limitação.
  Custo mensal se propaga automaticamente para todas as métricas
  agregadas (embutido em `liquido` antes de `sincronizar_portfolio`,
  nenhuma lógica nova em `tradefolio.portfolio` -- mesmo princípio já
  documentado em `custo_mensal.py`: "todo cálculo downstream que já
  consome liquido/liquido_por_contrato pega o custo automaticamente").
  Verificado: R$100/mês (resgat, 31 meses) + R$50/mês (gridhedge, 16
  meses) + R$0 (romanos2) = R$3.900 total; lucro combinado cai de
  R$64.320,93 para R$60.420,93 -- exatamente a diferença.
- [ ] VLT — não mais bloqueado tecnicamente (Épico 7/vapo existe), mas
  precisaria compor `vapo.gerar_serie_vapo` sobre `lucro_mensal` com uma
  política e alíquota escolhidas para o PORTFÓLIO -- decisão de
  convenção nova, não tomada nesta rodada (nem pedida explicitamente).

### Tarefa 10.4 — Calcular correlações múltiplas
- [x] **Completa** -- 6 variantes (lâmina ideal.pdf §13 pede "pelo menos
  4"; tarefas e épicos.pdf soma "correlação de perdas" e "correlação
  móvel" às mesmas 4):
  1. `correlacao_portfolio(largo)` = `largo.corr()` -- todos os dias.
  2. `correlacao_dias_conjuntos(largo, sincronizar_operou(diarios))` --
     só datas em que TODOS os robôs operaram (não apenas existiam).
  3. `correlacao_piores_dias(largo, fracao=0.20)` -- piores `fracao`
     dias pela série COMBINADA (decisão de design documentada no
     docstring do módulo: não uma recombinação por par).
  4. `correlacao_volatilidade_alta(largo, janela=21, fracao=0.20)` --
     top `fracao` dias por desvio-padrão móvel (`janela` pregões) da
     série combinada. Nem PDF-fonte especifica janela/fração para "alta
     volatilidade" -- ambas expostas como parâmetro, não hardcoded.
  5. `correlacao_perdas(largo)` -- só datas com série combinada < 0.
  6. `correlacao_movel(largo, janela_pregoes)` -- correlação par-a-par
     recalculada dia a dia sobre uma janela deslizante, genérica sobre a
     janela (mesmo padrão de `limiar.rlt_movel`), uma coluna por par.
  Todas verificadas contra dados reais antes dos testes (ex.: correlação
  resgat×gridhedge cai de 0,069 "todos os dias" para -0,41 "piores 20%
  dias" -- diversificação de fato melhora nos dias ruins deste
  portfólio, não piora).

### Tarefa 10.5 — Calcular contribuição marginal
- [x] `portfolio.contribuicao_marginal(diarios, minimum_margins, ...)` --
  para cada robô, recomputa o portfólio COM e SEM ele (o portfólio dos
  N-1 restantes) e diferencia lucro/MDD/ES95/limiar (lâmina ideal.pdf
  §13 "Valor marginal do robô"). N+1 recomputações completas -- caro
  para N grande, mas barato para o número de robôs típico de um
  portfólio real (nenhuma otimização feita, "medir antes de otimizar").
  Exige 2+ robôs (`ValueError` caso contrário -- "sem ele" não é um
  conceito coerente para um portfólio de 1). VLT deliberadamente fora
  (mesma lacuna de `rlt_e_risco_portfolio`: precisa de uma política de
  vapo escolhida para o portfólio). Verificado contra dados reais
  (resgat+gridhedge+romanos2, R$5.000/robô): excluir resgat muda o
  lucro combinado em -R$34.974 (aditivo, exatamente o lucro do próprio
  resgat) mas o MDD só piora R$689,44 (não R$ o MDD isolado do resgat --
  reflete o efeito real da diversificação) e o limiar cai R$5.000 (não
  R$9.500, o limiar do resgat sozinho). Wireado em `app.py` (expander
  "Contribuição marginal por robô", junto do limiar agregado) e
  `report.py` (seção HTML na mesma área) -- ambos só quando toda margem
  foi informada, mesma condição do limiar agregado.

### Tarefa 10.6 — Calcular limiar agregado
- [x] `portfolio.limiar_agregado_portfolio(largo, minimum_margins, ...)`
  — literalmente `limiar.decompor_limiar` (a MESMA função do robô
  único), alimentada pela margem mínima SOMADA e pelo drawdown da série
  COMBINADA. O PDF-fonte avisa para NÃO somar os limiares individuais --
  aqui não se soma nada, `decompor_limiar` calcula um limiar novo a
  partir dos dados agregados. Verificado contra dados reais (resgat +
  gridhedge + romanos2, R$5.000 de margem cada): limiar agregado
  R$19.500 vs. soma dos limiares individuais R$25.500 -- um benefício de
  diversificação real de R$6.000.

### Tarefa 10.7 — Calcular benefício da diversificação
- [x] `portfolio.beneficio_diversificacao(soma_limiares_individuais,
  limiar_agregado)` — `soma - agregado`, em R$ e em % da soma. Trivial,
  nenhuma fórmula nova. Verificado com o exemplo real de 10.6 (R$6.000,
  23,5% da soma individual).

### UI wiring (app.py / report.py)
- [x] `app.py`: modo "Portfólio" (radio no topo da barra lateral, ao lado
  de "Robô único") — escolhe 2+ robôs (exemplo ou upload), roda a
  detecção de contratos de cada um independentemente (inclusive o
  fallback multi-ativo por perna), pede a margem mínima de cada um e
  mostra lucro/MDD/ES95 combinados, correlação par-a-par e limiar
  agregado + benefício da diversificação (só quando toda margem foi
  informada). Verificado via `streamlit.testing.v1.AppTest` com resgat +
  gridhedge + romanos2 -- números idênticos aos de `test_portfolio.py`.
- [x] `report.py`: CLI virou subcomandos (`robo` = comportamento
  original inalterado; `portfolio` = novo, `--robo CSV MARGEM N_CONTRATOS`
  repetido 2+ vezes) gerando um HTML próprio (`gerar_html_portfolio`/
  `gerar_secao_portfolio`), sem página 1-6 de robô único. Verificado via
  execução real com os mesmos três CSVs -- números idênticos.
- [x] Pedido de acompanhamento do usuário: margem por robô no modo
  Portfólio é POR CONTRATO (não posição total, diferente do modo robo
  único) e cada robô tem um "número de contratos simulado no portfólio"
  próprio (independente do `contratos_referencia` detectado no CSV) —
  para permitir testar dimensionamentos diferentes sem reinformar a
  margem. `diario['liquido']` de cada robô é reescalado
  (`liquido_por_contrato × n_contratos`, mesma convenção linear de
  `daily.escalar_por_contratos`) ANTES de sincronizar e antes de calcular
  o limiar individual (mesma base de comparação para "soma dos limiares
  individuais" vs. agregado). Uma tabela de composição (contratos de
  referência, contratos simulados, margem/contrato, margem total por
  robô) aparece em ambas as UIs. Verificado: dobrar `n_contratos` de um
  robô (resgat 6→12) dobra exatamente sua contribuição ao lucro
  combinado (34.974,00→69.948,00; total combinado 99.294,93) em
  `app.py`; CLI reproduz os mesmos agregados de antes quando
  `n_contratos` = referência detectada. Nenhuma fórmula nova em
  `tradefolio.portfolio` -- só reescala o `diario` de entrada antes de
  chamar as mesmas funções (AGENTS.md §16/17).
- [x] Custo mensal por robô dentro do modo Portfólio -- ver tarefa 10.3
  acima (não é mais uma lacuna).
- [ ] Janela de filtro/Monte Carlo por robô dentro do modo Portfólio
  ainda não implementados (fora do escopo funcional desta primeira
  fatia do Épico 10).
- [x] Tarefa 10.4 completa (6 variantes) + extensão de 10.3 (RLT/risco/
  TUW/pior dia/pior mês/lucro mensal) wireadas em ambas as UIs. `app.py`:
  expander "Correlação entre robôs" ganhou um seletor de variante (radio)
  + parâmetro de janela quando aplicável, e uma subseção "Correlação
  móvel" com `st.line_chart`; o expander "Limiar agregado" ganhou os
  blocos RLT/risco normalizado (só quando toda margem foi informada,
  mesma condição já usada para o limiar agregado). `report.py`: todas as
  6 variantes aparecem lado a lado no HTML estático (não um seletor --
  relatório estático mostra tudo); correlação móvel resumida por par
  (mínimo/mediana/atual) em vez de despejada linha a linha; novo flag
  `--janela-movel-correlacao` (padrão 63 pregões). Verificado via
  `AppTest` e execução real do CLI -- números idênticos entre as duas
  UIs e a `tests/test_portfolio.py`.

### Robustez (Monte Carlo) do portfólio (tarefas e épicos.pdf tarefa 8.1, "Para portfólio: Todos os robôs permanecem sincronizados pela data")
- [x] `portfolio.robustez_portfolio(largo, ...)` — pedido de acompanhamento
  do usuário ("do we have monte carlo for the portfolio?" → "yes, build
  it"). Nenhuma fórmula nova: `monte_carlo.circular_block_bootstrap`/
  `resumo_trajetorias` já foram construídas desde o Épico 8 para aceitar
  um `pd.DataFrame` multi-coluna e manter todas as colunas na MESMA
  linha/data sorteada (docstring do módulo já citava "Épico 10" como o
  caso de uso futuro) -- `resumo_trajetorias` já soma entre colunas por
  trajetória antes dos percentis, então o resultado já é diretamente o
  lucro/MDD/probabilidades do PORTFÓLIO combinado, preservando a
  correlação real entre robôs em cada bloco sorteado (não uma
  reamostragem independente por robô).
- [x] `largo.fillna(0.0)` antes de reamostrar -- mesma convenção de
  `serie_combinada`'s `skipna=True` (robô que ainda não existia não
  contribui, não quebra o bootstrap com NaN).
- [ ] Cenários de deterioração (Épico 8.3) deliberadamente NÃO incluídos
  -- precisariam de `diario['bruto']`/`['custo']`/`['n_trades']` por
  robô, sem significado agregado coerente entre robôs heterogêneos
  (mesma razão já documentada para `metricas_agregadas`'s `lucro_mensal`
  não reusar `monthly.agregar_mensal`).
- [x] Wireado em ambas as UIs: `app.py` ganhou sidebar "Robustez (Monte
  Carlo) do portfólio" (mesmos parâmetros do modo Robô único: bloco,
  trajetórias, horizonte, seed, incluir dias sem operação) + expander
  com o mesmo layout de métricas; `report.py` ganhou `--bloco
  --trajetorias --horizonte --seed-mc --excluir-dias-sem-operacao`
  (mesmos flags do modo robo) e reusa `gerar_secao_robustez` (já
  genérica o bastante, sem alteração). Verificado com dados reais
  (resgat+gridhedge+romanos2, seed=42): lucro P50 R$33.425,94, MDD P95
  R$-5.517,56 -- números idênticos entre `app.py` (via `AppTest`) e
  `report.py` (execução real do CLI).

### Tarefa 10.8 — Otimização de portfólio
- [x] `portfolio.otimizar_portfolio(diarios_referencia, margens_por_contrato,
  candidatos_contratos, objetivo, ...)` — busca discreta (não otimização
  contínua, conforme o PDF-fonte pede explicitamente) via
  `itertools.product` sobre candidatos de número de contratos por robô.
  Decisão de dependência (AGENTS.md §18): produto cartesiano puro
  (stdlib, sem SciPy/CVXPY/Optuna) -- o próprio PDF-fonte já indica essa
  opção como suficiente "para poucas estratégias", que é exatamente o
  caso de uso real deste app (2-10 robôs). `~6ms/combinação` medido
  contra dados reais; limite de 20.000 combinações com erro explícito
  acima disso (busca discreta não escala, reduza os candidatos).
  **`0` é um candidato de contratos válido -- pedido explícito de
  acompanhamento do usuário ("tirar um robô também é uma
  possibilidade"): exclui aquele robô inteiramente daquela combinação.**
  Verificado contra dados reais que isso realmente muda o resultado
  ótimo: para "maximizar RLT" com resgat/gridhedge/romanos2, a melhor
  combinação testada às vezes exclui 2 dos 3 robôs (só romanos2), não
  porque a busca "preferiu" excluir -- porque aquela combinação
  realmente teve o maior RLT entre as testadas.
- [x] Penalidade por múltiplas tentativas (aviso explícito do PDF-fonte,
  "nunca reportar só o melhor resultado da amostra"): a função retorna
  as `top_n` melhores combinações (não só a primeira) e
  `n_combinacoes_testadas`, exposto na UI como um aviso explícito de
  risco de sobreajuste -- não uma correção estatística formal (ex.
  Bonferroni), que seria inventar uma convenção nova não pedida; um
  aviso textual proporcional ao número de tentativas já cobre o espírito
  do requisito sem inventar um número.
- [x] 3 dos 6 objetivos do PDF-fonte implementados (os que não dependem
  de política de vapo para o portfólio, decisão ainda não tomada):
  "maximizar_rlt", "minimizar_mdd_sobre_limiar" (menor \|MDD\|/limiar, não
  o valor mais negativo), "maximizar_lucro_com_limite_mdd" (`limite_mdd`
  sempre obrigatório -- nunca inventado).
- [ ] Deliberadamente NÃO implementados: "maximizar VLT"/"maximizar vapo
  com limite de capital" (precisam de uma política de vapo escolhida
  PARA O PORTFÓLIO -- mesma lacuna de `rlt_e_risco_portfolio`) e
  "minimizar pior cenário deteriorado" (precisaria rodar Monte Carlo +
  deterioração para CADA combinação testada -- caro e uma decisão de
  escopo própria, não pedida ainda).
- [x] Custo mensal deliberadamente NÃO entra na busca (simplificação
  documentada na docstring de `otimizar_portfolio`, não escondida) --
  tornaria cada combinação dependente de uma tabela de faixas por robô;
  o objetivo desta primeira fatia é o dimensionamento puro. Aplicar a
  tabela de custo sobre a alocação vencedora fica por conta de quem
  consome o resultado.
- [x] Wireado só em `app.py` (expander "Otimização de portfólio", dentro
  do modo Portfólio, com candidatos configuráveis por robô na barra
  lateral -- máximo, passo, e um checkbox "permitir excluir da busca").
  **Decisão de escopo, não uma lacuna**: `report.py` (CLI) não recebeu
  essa função nesta rodada -- otimização é inerentemente uma ferramenta
  de exploração interativa (ajustar faixas, rodar, ver top 10, ajustar
  de novo), diferente das demais tarefas do Épico 10 (um cálculo único,
  fácil de virar flag de CLI). Adicionar suporte no CLI é possível se
  pedido, mas exigiria uma superfície de argumentos própria (faixas de
  candidatos por robô) em vez de reusar `--robo CSV MARGEM N_CONTRATOS
  CUSTO_MENSAL` como está.
- [x] Pedido de acompanhamento do usuário: busca (cara) e seleção por
  objetivo (barata) separadas em duas funções --
  `buscar_combinacoes_portfolio` (calcula lucro/MDD/ES95/limiar/RLT
  acumulado/MDD-sobre-limiar para TODAS as combinações, sem aplicar
  objetivo nenhum) e `selecionar_melhores_combinacoes` (ordena/filtra o
  que já foi calculado -- não recalcula nada). `otimizar_portfolio`
  virou um atalho que chama as duas em sequência (comportamento idêntico
  a antes, todos os testes antigos passam sem alteração -- refatoração
  comportamento-preservando). Em `app.py`, "Buscar combinações" roda a
  parte cara uma vez (dentro de `st.spinner`, guardada em
  `st.session_state`); trocar o objetivo (ou o limite de MDD) depois só
  reordena a tabela já pronta, sem recalcular -- um aviso aparece se os
  candidatos/margens/escopo mudarem desde a última busca, sem forçar
  recálculo automático. Threading avaliado e descartado para este caso:
  o modelo de execução do Streamlit (rerun síncrono do script inteiro a
  cada interação) não tem um jeito simples e robusto de manter uma
  thread rodando em background enquanto o resto da UI continua
  interativa (exigiria polling de `session_state` + propagação manual de
  contexto via `add_script_run_ctx`, um padrão avançado e frágil) --
  `st.spinner` (feedback honesto de que algo está rodando) + a separação
  busca/seleção (elimina quase todo recálculo desnecessário) resolve o
  problema real sem essa complexidade.
- [x] Fronteira de Pareto discreta (pedido de acompanhamento do usuário,
  fora dos épicos do PDF-fonte) -- `portfolio.fronteira_pareto(resultados,
  eixo_retorno, eixo_risco)`. Discutido com o usuário antes de
  implementar: Markowitz (fronteira eficiente contínua, variância como
  risco) foi considerado e descartado -- contratos são discretos neste
  domínio (uma alocação contínua exigiria arredondar depois, podendo
  violar a margem/limiar que a otimização deveria respeitar) e o projeto
  inteiro já usa MDD/ES/limiar como vocabulário de risco, não variância/
  Sharpe -- Markowitz seria bifurcar a filosofia de risco, não estendê-la.
  Uma fronteira de Pareto discreta não precisa de nenhuma convenção nova:
  roda sobre os resultados que `buscar_combinacoes_portfolio` JÁ
  calculou (nenhuma busca nova), identificando as combinações que nenhuma
  outra domina simultaneamente nos dois eixos escolhidos. Algoritmo
  skyline O(n log n) (não O(n²) par-a-par), relevante pelo limite de até
  20.000 combinações da busca. Convenção "maior é melhor" nos dois eixos
  -- os campos de risco já existentes (mdd/es_95/mdd_sobre_limiar) já são
  negativos nesta base de código, então "maior" = "menos negativo" =
  mais seguro, sem precisar inverter sinal.
  Wireado em `app.py` (dentro do expander de otimização, com 3 pares de
  eixos pré-definidos -- Lucro×MDD, Lucro×ES95, RLT×MDD/limiar --
  `st.scatter_chart` colorindo os pontos na fronteira, mais uma tabela
  só com as combinações não-dominadas). Verificado contra dados reais
  (resgat+gridhedge+romanos2): fronteira Lucro×MDD tem 4 das 11
  combinações testadas; fronteira RLT×MDD/limiar tem 5 -- ambas
  conferidas por script antes dos testes e idênticas ao resultado do
  `AppTest`.
- [ ] Monte Carlo P95/P99 (MDD ou ES) como objetivo/verificação do
  otimizador -- discutido, não implementado ainda. Rodar Monte Carlo em
  CADA combinação da busca é caro demais (mesma razão já documentada
  para "minimizar pior cenário deteriorado" em `otimizar_portfolio`);
  o caminho combinado com o usuário é rodar `robustez_portfolio` só nas
  poucas combinações que sobram depois da busca barata (ex. as que estão
  na fronteira de Pareto), não em todas. Também falta um gap concreto:
  `monte_carlo.resumo_trajetorias` hoje calcula percentis de MDD e lucro
  das trajetórias, mas não um percentil de ES -- precisaria ser
  adicionado se quisermos "ES simulado", não só "MDD simulado".

---

## Épico 11 — Lâmina visual no Streamlit

Reorganização/expansão de `app.py` -- não introduz cálculo novo por si só.
Vários itens dependem de dados que ainda não existem (vapo: Épico 7;
robustez: Épico 8; portfólio: Épico 10; "qualidade dos dados" como nota:
Épico 14 do PDF-fonte, fora do escopo pedido nesta rodada). Duas tarefas
(11.5, 11.6) não dependem de nenhum outro épico e podem ser feitas a
qualquer momento.

### Tarefa 11.1 — Criar página de resumo
- [ ] Nome, Período, Configuração, Margem, Limiar, RLT, MDD/L já são
  exibidos em `app.py` hoje (dispersos em vários `st.expander`s, não numa
  única "primeira dobra" compacta) — reorganização de UI, não cálculo
  novo.
- [ ] Status (verde/amarelo/laranja/vermelho/cinza, "lâmina ideal.pdf"
  §2) — os limiares de corte para cada cor nunca foram definidos
  numericamente em nenhum dos dois PDFs-fonte; decidir isso é uma
  convenção nova a confirmar, não a inventar.
- [ ] VLT — bloqueado pelo Épico 7.
- [ ] "Qualidade dos dados" (nota 0–100) — é o score do Épico 14 do
  PDF-fonte (não 10/11), fora do escopo desta lista; `app.py` hoje não
  tem nenhuma pontuação, só métricas brutas.

### Tarefa 11.2 — Criar gráfico principal
- [ ] Equity, high-water marks e drawdowns já existem
  (`report.montar_figura_curva_drawdown`, construído nesta sessão) -- em
  matplotlib, não Plotly como o PDF-fonte sugere. Trocar ou adicionar
  Plotly é uma dependência nova (AGENTS.md §18) a justificar antes de
  substituir o que já funciona.
- [ ] "Mudanças de mão" e "versões" como anotações no gráfico — mesma
  lacuna já documentada (Épico 2.2/3.2): não existe detecção de ponto de
  mudança de configuração, e inventar uma agora seria adivinhar.
- [ ] "Períodos sem dados" — depende de MISSING_DATA existir como sinal
  independente (não implementado, ver `alignment.py`), mesma lacuna da
  tarefa 3.3 (e agora também da 10.1, em escala de portfólio).

### Tarefa 11.3 — Criar abas
- [ ] Resumo/Curva/Risco/Qualidade/Ativos já têm dado pronto
  (`calcular_pagina1/4/5/6`) — é reorganizar `st.expander`s existentes em
  `st.tabs`, não computar nada novo.
- [ ] Ordens — trivial, `st.dataframe(ordens)` já bastaria; não
  implementado ainda por não ter sido pedido, não por dificuldade
  técnica.
- [ ] Vapo/Robustez/Portfólio — bloqueadas pelos Épicos 7/8/10
  respectivamente; aba ficaria vazia até lá.
- [ ] Auditoria ("lâmina ideal.pdf" §21: clicar em um valor e chegar às
  ordens que o compõem) — funcionalidade genuinamente nova de
  rastreabilidade linha-a-linha, não uma composição do que já existe.

### Tarefa 11.4 — Usar estado corretamente
- [ ] `app.py` hoje já usa um esquema manual de chaves por arquivo
  (`f"minimum_margin::{chave_arquivo}"`) — um precursor mais simples de
  `st.session_state` estruturado, não a mesma coisa. Migrar para o padrão
  completo (estratégia selecionada, portfólio, limiar escolhido, política
  de vapo, cenário, filtros, análise ativa) só faz sentido pleno quando
  existir mais de uma "análise ativa" para alternar (multi-página/
  multi-robô), o que hoje não existe.

### Tarefa 11.5 — Evitar recomputação total
- [ ] **Sem bloqueio de nenhum outro épico** — pode ser feito a qualquer
  momento: `@st.cache_data` nas funções de `report_data.calcular_pagina*`
  (chave por hash do CSV + parâmetros), `@st.cache_resource` se/quando
  houver conexão de banco (Épico 1.4). Candidato a próximo passo
  independente se performance virar um problema real.

### Tarefa 11.6 — Adicionar URLs reproduzíveis
- [ ] **Sem bloqueio de nenhum outro épico**, ao menos parcialmente:
  `st.query_params` já suportaria `?strategy=...&threshold=...` hoje;
  `&scenario=...` só faz sentido quando o Épico 8 (deterioração) existir.

---

## Lacunas transversais que aparecem em mais de um épico

- ~~**Coluna `Ativo` nunca lida**~~ — resolvido (`daily.agregar_diario_por_ativo`
  + `validation.extrair_raiz_ativo`); exposto em `report_data` (4.1,
  `lucro_por_ativo`) e consumido no Épico 12 da lâmina ideal
  (`calcular_pagina6`, ver seção "Lâmina ideal.pdf -- wiring" abaixo).
- ~~**Coluna `Status` nunca lida**~~ — resolvido (1.1: ordens canceladas mantidas
  e excluídas da agregação; `UNKNOWN_STATUS` em 1.3).
- **Nenhuma persistência** — Épico 1.4 é pré-requisito de fato para Épico 2
  (entidades com `AnalysisRun`/histórico) fazer sentido; hoje não há "onde"
  guardar uma `AnalysisRun`.

---

## Lâmina ideal.pdf — wiring em `app.py`/`report.py`

Até aqui, tudo dos Épicos 0–6 existia só como função testada, sem aparecer em
nenhuma das duas UIs (`app.py` ao vivo, `report.py` estático). Esta seção
liga o que já existe, seguindo a estrutura do `prompts/lamina ideal.pdf`
(27 páginas) na parte que é possível construir sem inventar convenção nova.
A maior parte do PDF (vapo §6, Monte Carlo/bootstrap §7-8, deterioração §10,
"mudanças de mão" §3, selo de tipo de histórico §11, score geral §19,
portfólio §13-14, schema JSON para IA §15-18) continua **fora de escopo**
— nenhum desses subsistemas existe no código, e cada um exigiria decidir uma
convenção nova sem base no PDF-fonte. Ambas as UIs mostram uma nota
"fora de escopo" explícita em vez de omitir isso em silêncio.

- [x] `daily.pivotar_liquido_por_ativo(ordens)` — reshape largo de
  `agregar_diario_por_ativo`, base para MDD/correlação por ativo
- [x] `report_data.calcular_pagina4` — limiar (P95 e P99 lado a lado,
  resolução do usuário "use both... toggle button somewhere"), RLT
  (acumulado/anualizado/mensal médio-mediano/móvel 3-6-12m), risco
  normalizado pelo limiar (MDD/L, pior dia/L, ES95/L, Ulcer/L, pior mês/L)
  — tudo em escala TOTAL da posição (`diario['liquido']`), não por
  contrato (decisão de escala confirmada nesta sessão)
- [x] `report_data.calcular_pagina5` — qualidade da curva: concentração
  (top N dias/meses), lucro removendo eventos, permanência abaixo de
  zero, os 3 alertas automáticos de `concentracao.detectar_alertas_curva`
- [x] `report_data.calcular_pagina6` — comparação entre ativos (só
  chamada para robôs multi-ativo): lucro/MDD por ativo, correlação
  (variante "todos os dias" apenas — as outras 3 do PDF §12 precisam de
  decisões de convenção extras, documentadas como deferidas), e
  "compensação nos piores dias" (responde à pergunta do próprio PDF:
  "nos piores dias do WIN, quanto o WDO ganhou?")
- [x] `metric_registry`/`versions` estendidos para páginas 4/5/6 (nova
  etapa `concentracao` adicionada a `VERSOES` — existia desde o Épico 5
  mas nunca tinha sido registrada)
- [x] `report.montar_figura_curva_drawdown` ganhou `episodios=None`
  opcional: sombreado de período submerso por faixa de duração (≤20/21-60/
  >60 pregões), marcação de high-water marks e do melhor/pior dia —
  compatível com versões antigas (default preserva o comportamento
  anterior), usado por `app.py` e `report.py`
- [x] `report.py`: `gerar_secao_pagina4/5/6` (mesmo estilo de
  `gerar_secao_pagina2/3`); `__main__` corrigido para receber CSV/saída/
  parâmetros de limiar via CLI (`argparse`) em vez do caminho
  `/mnt/user-data/...` hardcoded (`CLAUDE.md`'s "I/O paths are currently
  hardcoded")
- [x] `app.py`: sidebar "Limiar" (margem mínima -- sem valor padrão, nunca
  inventado; percentil/reserva/incremento com defaults editáveis),
  expanders "Limiar e RLT", "Qualidade da curva", "Comparação entre
  ativos" (só para CSV multi-ativo), drawdown corrente/tempo de
  recuperação mediano finalmente exibidos (já existiam desde 4.3, nunca
  mostrados), nota de "fora de escopo" no rodapé
- [x] **Limitação corrigida** (ver seção "Contratos de referência para
  robôs multi-ativo com proporção fixa" abaixo): `app.py`/`report.py` não
  travam mais para `orders_roboraiz.csv` -- "Comparação entre ativos"
  agora é alcançável na página ao vivo, verificado via `AppTest`.

---

## Custo mensal por faixa de contratos (fora dos épicos do PDF-fonte)

Pedido explícito do usuário: nenhum dos dois PDFs-fonte descreve um custo
mensal de plataforma/assinatura em degraus por número de contratos (só
existia o emolumento B3 por perna, linear e por ordem —
`tradefolio.costs`). Implementado em `src/tradefolio/custo_mensal.py`.
`VERSOES["custo_mensal"]` = `"custo_mensal_v1"`.

- [x] `FaixaCustoMensal(min_contratos, max_contratos, custo_mensal)` +
  `TabelaCustoMensal(faixas)` — faixas com AMBOS os limites inclusivos
  (`max_contratos=None` = sem teto); sobreposição entre faixas levanta
  `ValueError` na construção em vez de escolher um desempate silencioso
  para uma fronteira ambígua (o próprio exemplo do usuário, "1-5" e
  "5-8", se sobrepõe em 5 — a tabela força quem a define a resolver isso)
- [x] `custo_mensal_zero()` — convenience para o caso explícito de custo
  0 (uma faixa única cobrindo 1 a ∞ contratos a R$0) — nunca um valor
  inventado, 0 é uma escolha honesta como em `vapo.aliquota_fiscal`
- [x] `aplicar_custo_mensal(diario, tabela, contratos_referencia)` —
  debita o custo (da faixa correspondente ao número de contratos) no
  ÚLTIMO PREGÃO B3 de cada mês presente em `diario`, reusando a mesma
  convenção de apuração "último pregão do mês" já usada em
  `tradefolio.vapo`/"lâmina ideal.pdf" §6 (não uma nova inventada).
  Cobra mesmo em dia NO_TRADE e mesmo em mês parcial (mesmo
  comportamento que `tradefolio.monthly` já tem para mês incompleto).
  Nova coluna `custo_mensal`, separada de `custo` (que continua sendo só
  o emolumento B3) — `liquido = bruto - custo - custo_mensal`,
  `liquido_por_contrato` recomputado na mesma proporção
- [x] Escopo só no `diario` agregado do robô inteiro, não no breakdown
  por ativo (`daily.agregar_diario_por_ativo`) — uma assinatura de
  plataforma não é atribuível a uma perna específica; ratear isso seria
  uma convenção nova e arbitrária, não implementada
- [x] `report_data.montar_dataframe_diario` ganhou `tabela_custo_mensal=None`
  opcional (compatível com chamadas existentes) — quando informada,
  aplica o custo antes de retornar o `diario`; como só toca
  `liquido`/`liquido_por_contrato` (antes de qualquer drawdown/métrica/
  mensal/limiar/vapo rodar), TUDO que já consome essas colunas reflete o
  custo automaticamente, sem precisar mudar nenhum outro módulo —
  verificado por script: lucro líquido, Sharpe, MDD e a reagregação
  mensal mudam corretamente contra `tests/fixtures/romanos_orders.csv`
- [x] **Wireado em `app.py`**: sidebar "Custo mensal" com `st.data_editor`
  editável (linhas dinâmicas: min/máx contratos, custo mensal) — cobre
  tanto o caso tiered quanto "mesmo valor para todas as faixas"/"zero"
  pedidos pelo usuário. `construir_tabela_custo_mensal` converte a
  tabela editada, ignorando linhas totalmente vazias (usuário ainda
  digitando) e propagando erro de validação (faixas sobrepostas) via
  `st.error` + `st.stop()`, mesmo padrão das outras validações da
  sidebar. Aplicado sobre `contratos_referencia` REAL detectado, não
  sobre o "Número de contratos" simulado — mesma limitação de escala
  linear já documentada para a simulação de contratos (custo mensal em
  degraus não escala linearmente, então compor com a simulação
  hipotética herdaria essa imprecisão de qualquer forma). Caption no
  topo mostra a faixa ativa e o custo total já debitado no período.
- [x] **Wireado em `report.py`** (CLI): `--custo-mensal FLOAT` (padrão
  0.0) — só um valor único (mesmo custo para qualquer número de
  contratos), já que uma tabela em degraus completa via flags de linha
  de comando seria pouco prática; a tabela editável fica em `app.py`,
  mais adequada para isso.
- Ambas verificadas ponta-a-ponta por script e via `AppTest` do
  Streamlit (sem exceções, lucro líquido/Sharpe/MDD mudam corretamente
  quando um custo não-zero é aplicado).
- [x] **Correção**: o `st.column_config.NumberColumn` da coluna "Custo
  mensal (R$)" não aceitava decimal (`step=50.0` sem `format` explícito
  fazia o Streamlit tratar a coluna como inteira) — corrigido com
  `format="%.2f", step=0.01`. Verificado ponta-a-ponta com um custo
  fracionário (R$150,50) via `report.py` CLI.
- [x] **`custo_mensal.resumo_custo_mensal(diario)`** — pedido explícito
  do usuário ("quanto foi gasto no total, quanto o custo corroeu o
  lucro"): `custo_mensal_total`, `lucro_liquido_com_custo_mensal`,
  `lucro_liquido_sem_custo_mensal`, `fracao_erosao_do_lucro` (=
  `custo_mensal_total / lucro_liquido_sem_custo_mensal`, NaN quando o
  robô já seria deficitário mesmo sem o custo mensal — uma fração aí não
  teria leitura percentual sã), `meses_cobrados`,
  `custo_mensal_medio_por_mes_cobrado`. Nenhum limite de "saudável" é
  definido — não há uma convenção para isso em nenhum PDF-fonte nem foi
  combinado um valor com o usuário; o número é mostrado cru (nota
  explícita nas duas UIs) em vez de inventar um corte. Nova seção
  "Custo mensal" em `app.py` (expander) e `report.py`
  (`gerar_secao_custo_mensal`), ambas verificadas ponta-a-ponta.

---

## Robustez (Monte Carlo/deterioração) — wiring em `app.py`/`report.py`

`report_data.calcular_robustez` orquestra `tradefolio.deterioracao` +
`tradefolio.monte_carlo` (AGENTS.md épico 8) na mesma camada que já
monta `calcular_pagina1-6` -- as duas UIs chamam a mesma função, evitando
duplicar a ordem de composição (aumentar_custos → aplicar_slippage →
reduzir_ganhos → ampliar_perdas → remover_melhores_dias →
duplicar_piores_dias → bootstrap → percentis) em dois lugares.

- [x] **`app.py`**: sidebar "Robustez (Monte Carlo)" (tamanho do bloco,
  número de trajetórias até 50.000, horizonte, seed opcional, incluir/
  excluir dias sem operação) + um `st.expander` aninhado "Cenário de
  deterioração" com as 6 transformações de 8.3, todas com valor neutro
  por padrão (0 = sem efeito) — a mesma tela serve tanto para "só rodar
  o Monte Carlo puro" quanto para explorar a grade de deterioração
  interativamente, sem duas telas separadas. Seção de resultado mostra
  os percentis, a seed usada (sempre, para reprodutibilidade) e um aviso
  quando algum parâmetro de deterioração está ativo.
- [x] **`report.py`** (CLI): `--bloco/--trajetorias/--horizonte/--seed-mc/
  --excluir-dias-sem-operacao` + `--reducao-ganhos/--aumento-perdas/
  --aumento-custos/--slippage/--remover-melhores-dias/--duplicar-piores-dias`.
  `gerar_secao_robustez` no mesmo estilo das outras seções.
- [x] `probabilidade_toca_margem`/`probabilidade_termina_abaixo_do_limiar`
  em `app.py` mostram "—" quando a margem mínima ainda não foi informada
  (mesmo padrão de "Limiar e RLT"); em `report.py`, `--minimum-margin` já
  é obrigatório para todo o script, então essas duas sempre aparecem.
- [x] `FORA_DE_ESCOPO`/`_FORA_DE_ESCOPO` (nota de rodapé nas duas UIs)
  atualizada -- "Monte Carlo/bootstrap, grade de deterioração" removidos
  da lista do que falta, já que agora existem.
- Verificado ponta-a-ponta: `AppTest` do Streamlit (sem exceções, com e
  sem margem mínima informada, com um cenário de deterioração ativo) e
  `report.py` rodado via CLI com deterioração + seed fixa.
- [ ] Não incluído: o heatmap/tabela completo de 16 células (0/10/20/30%
  × 0/10/20/30%) sugerido por "lâmina ideal.pdf" §10 -- a UI atual deixa
  o usuário mover os dois eixos manualmente e ver UMA célula por vez, não
  a grade inteira de uma vez (rodar Monte Carlo para as 16 combinações
  a cada interação seria ~16x mais lento, ainda rápido o bastante, mas
  não foi pedido nem construído nesta rodada).

---

## Contratos de referência para robôs multi-ativo com proporção fixa (fora dos épicos do PDF-fonte)

Pedido explícito do usuário: Robô Raiz não tem "contratos" independentes
por ativo -- 1 unidade é um pacote fixo e indivisível (3 WIN + 2 WDO; o
próximo nível é 4 WDO + 6 WIN, não dá pra aumentar só um lado).
`daily.detectar_contratos_referencia` sobre o CSV inteiro (mistura WIN e
WDO numa única distribuição de 'Quantidade executada') não detecta nada
para esse robô -- e é por isso que `app.py` travava com erro para
`orders_roboraiz.csv` antes desta correção. Mesmo POR PERNA, o histórico
INTEIRO de WDO não é 90% dominante (mudou de proporção historicamente,
Épico 2.2) -- por isso a detecção é restrita a uma JANELA RECENTE (o
usuário escolheu esta abordagem entre três oferecidas: entrada manual,
janela recente, ou segmentação histórica completa).

- [x] `daily.contratos_referencia_por_ativo(ordens, dias_recentes=None)` —
  detecta a quantidade de referência (`detectar_contratos_referencia`)
  POR `ativo_raiz` separadamente; `dias_recentes` restringe aos últimos N
  dias corridos a partir da última data em `ordens`. Sem janela, dá
  exatamente o resultado por-perna que `domain.configuracao_a_partir_da_deteccao`
  já fazia (comportamento antigo preservado quando não há necessidade de
  restringir).
- [x] `daily.detectar_contratos_referencia_multi_ativo(ordens, dias_recentes=None)`
  — soma as pernas ("1 unidade" = o pacote inteiro, ex. 3+2=5). Para um
  robô de ativo único, dá exatamente o mesmo resultado de
  `detectar_contratos_referencia` (verificado).
- [x] Janela padrão de 90 dias -- conferida por script contra
  `orders_roboraiz.csv` antes de fixar: 30/60/90/120/180 dias todos
  recuperam WDO=2/WIN=3 corretamente; 365 dias já falha para WDO
  (proporção mudou há mais de um ano). O valor é ajustável pelo usuário
  (sidebar em `app.py`, `--dias-recentes-deteccao` em `report.py`), não
  fixado silenciosamente.
- [x] `domain.configuracao_a_partir_da_deteccao` refatorado para reusar
  `contratos_referencia_por_ativo` (elimina o laço por-perna duplicado)
  e ganhou o mesmo parâmetro `dias_recentes` opcional.
- [x] **`app.py`**: quando a detecção simples falha, tenta automaticamente
  por ativo sobre uma janela recente (input na sidebar, padrão 90 dias)
  antes de desistir. Uma nova legenda mostra a composição detectada (ex.
  "1 contrato aqui = 2 WDO + 3 WIN") para o usuário confirmar
  visualmente que a proporção está certa. `orders_roboraiz.csv` agora
  carrega a página inteira, incluindo "Comparação entre ativos"
  (verificado via `AppTest` -- antes desta correção, ambos travavam).
- [x] **`report.py`** (CLI): mesmo fallback automático + `--dias-recentes-deteccao`
  (padrão 90). Verificado rodando `orders_roboraiz.csv` via CLI (antes
  desta correção, o script quebrava com `ValueError` não tratado).
- [ ] Não implementado: segmentação histórica completa (múltiplas
  `StrategyConfiguration` com `valid_from`/`valid_to` diferentes para
  cada período com uma proporção distinta) -- a opção que o usuário NÃO
  escolheu desta vez. Continua sendo o próximo passo natural se algum
  dia for preciso analisar corretamente um período PASSADO (não só a
  configuração atual) de um robô que mudou de proporção.

---

## Formato de resultado diário agregado (robôs sem exportação order-level, fora dos épicos do PDF-fonte)

Pedido do usuário: um novo robô (TradingX,
`dados_exemplo/daily_tradingx.csv`) não tem exportação order-level --
só um resultado diário já agregado por pregão
(`Data;Mes;Pontos;Resultado_R$;Saldo_Acumulado_R$`, sem detalhe de
ordem/trade/contrato). Implementado em `src/tradefolio/daily_results.py`.
`VERSOES["ingestao_resultados_diarios"]` = `"daily_results_v1"`.

- [x] `carregar_resultados_diarios(csv_path)` -- lê o CSV (`;`, BOM
  UTF-8, `Data` dd/mm/yyyy, `Resultado_R$` já numérico), levanta erro
  para coluna obrigatória faltante ou datas duplicadas. `Mes`/`Pontos`/
  `Saldo_Acumulado_R$` são ignorados (não fazem parte do que o pipeline
  precisa).
- [x] `montar_diario_resultados(resultados)` -- constrói um `diario` no
  MESMO formato usado pelo resto do pipeline (`liquido`/
  `liquido_por_contrato`/`operou`), alinhado ao calendário B3 real
  (mesma convenção de `alignment.preencher_calendario_b3`; `operou`
  derivado da presença da linha no arquivo, não de `n_trades`, que não
  existe neste formato). Verificado contra o arquivo real: 174 linhas,
  2026-01-06 a 2026-09-15, sem nenhum pregão B3 ausente nesse intervalo.
- [x] `eh_formato_resultados_diarios(csv_path)` -- detecção pelo
  cabeçalho (mesmo espírito de
  `importers.SmarttbotOrderImporter.can_parse`), usada para escolher
  automaticamente o caminho de ingestão certo em `app.py`/`report.py`
  sem exigir um seletor de formato manual na UI.
- [x] **Decisões de escala/convenção** (documentadas, não inventadas --
  AGENTS.md §8):
  - `bruto`/`custo`/`n_trades` ficam `NaN` no `diario` -- genuinamente
    DESCONHECIDOS sem dado de ordem, nunca inventados como 0 (0 já
    significa "sem custo B3", um fato diferente de "não sabemos o
    custo"). Métricas que dependem deles (ex. `retorno_bruto_pct`)
    degradam honestamente para "—" na UI, não um número fabricado.
    Conferido: `Resultado_R$/Pontos` no arquivo real fica em torno de
    0,20 (valor do ponto do WIN) mas não é exato (0,1989–0,2069),
    consistente com algum custo/slippage já líquido em `Resultado_R$`
    -- por isso ele é tratado como `liquido` diretamente, sem tentar
    decompor mais.
  - `contratos_referencia=1` fixo, NÃO detectado (não há "Quantidade
    executada") -- **decisão confirmada com o usuário via
    AskUserQuestion**: a série já representa 1 contrato, permitindo
    escalar como os demais robôs (`daily.escalar_por_contratos`), não
    um valor fixo não-escalável.
  - Página 2 (métricas de trade -- Profit Factor, sequências, win rate)
    é estruturalmente impossível para este formato (sem trade
    reconstruído) -- nunca computada; `app.py` nunca mostrou página 2
    de qualquer forma (só `report.py`, que agora mostra uma nota "não
    disponível" no lugar). Página 6 (comparação entre ativos) também
    pulada -- série única, sem múltiplos ativos por construção.
  - Cenário de deterioração do Monte Carlo (`aumento_custos`/
    `slippage`) desabilitado para este formato -- ambos dependem de
    `bruto`/`custo`/`n_trades`; `report.py` levanta erro explícito se
    o usuário tentar usar `--aumento-custos`/`--slippage` com um robô
    deste formato, em vez de silenciosamente ignorar o parâmetro.
- [x] Wireado em `app.py` (modo Robô único E modo Portfólio -- detecção
  automática por arquivo, sem seletor de formato manual) e `report.py`
  (CLI `robo` e `portfolio`, mesma detecção automática). Verificado com
  o arquivo real: lucro líquido R$9.646,00 sozinho (via `AppTest` e CLI,
  números idênticos); combinado com `orders_resgat.csv` na janela comum
  (Épico 10): lucro R$14.472,00, MDD R$-2.512,00 -- conferido por script
  independente e idêntico entre `app.py`/`report.py`.
