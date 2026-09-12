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

Nada implementado. `VERSOES["monte_carlo"]` e `VERSOES["deterioracao"]` já
existem como `None`. `ORIGENS_VALIDAS` (metric_registry, épico 0.2) já
inclui `"simulated"` — a categoria de origem para tudo que este épico
produzir já está prevista, não precisa ser inventada agora.

### Tarefa 8.1 — Bootstrap diário sincronizado
- [ ] Sortear a LINHA diária inteira (não cada ativo/robô independente) —
  `daily.pivotar_liquido_por_ativo` já produz exatamente o formato
  necessário como entrada (uma linha por data, uma coluna por ativo, já
  alinhado no mesmo calendário) para manter WIN/WDO sincronizados por
  data. Para portfólio (Épico 10, não iniciado), o mesmo padrão se
  estenderia a colunas por robô.
- [ ] Decisão em aberto: reamostrar sobre o histórico inteiro ou uma
  janela mais recente? O PDF-fonte só diz "sortear a linha diária
  inteira", sem especificar o universo de amostragem — assumir histórico
  inteiro é razoável, mas deveria ser confirmado, não assumido em
  silêncio.

### Tarefa 8.2 — Circular block bootstrap
- [ ] Técnica padrão (blocos contíguos com wraparound), tamanhos de bloco
  5/10/20/40 pregões como OPÇÕES (não um valor fixo — mesmo espírito do
  toggle P95/P99 do limiar: AGENTS.md §8.1, não inventar uma escolha
  única quando o PDF-fonte já lista várias). Parâmetros obrigatórios do
  PDF: seed, trajetórias, horizonte, bloco, frequência, tratamento dos
  zeros.
- [ ] Seed deve ser sempre reportado junto do resultado, nunca fixado
  silenciosamente — mesmo princípio de proveniência já aplicado em
  `metric_registry` (nunca misturar dado observado com simulado sem
  rótulo).
- [ ] Tratamento dos zeros: dias NO_TRADE (operou=False) são histórico
  legítimo e deveriam ser reamostrados normalmente como qualquer outro
  dia — mas o PDF-fonte pede que isso seja um parâmetro explícito, não
  uma decisão silenciosa do código.

### Tarefa 8.3 — Cenários deteriorados
- [ ] Seis transformações independentes e compostáveis: redução dos
  ganhos, ampliação das perdas, aumento dos custos, slippage adicional,
  remoção dos melhores dias, duplicação dos piores dias — cada uma é uma
  função pura sobre a série diária.
- [ ] "Aumento de custos" reusa `costs.custo_b3` com um multiplicador —
  trivial uma vez que a grade de deterioração exista.
- [ ] A grade 0%/10%/20%/30% de "lâmina ideal.pdf" §10 (redução de ganhos
  × aumento de perdas) já dá um exemplo concreto de degraus a seguir, em
  vez de inventar uma grade nova.

### Tarefa 8.4 — Produzir percentis
- [ ] Agregação pura sobre as trajetórias simuladas (lucro P5/P25/P50/
  P75/P95; MDD P50/P90/P95/P99; pior mês; TUW; VLT; probabilidade de
  prejuízo/de tocar a margem/de terminar abaixo do limiar) —
  `metrics.percentil` já é genérico o suficiente para isso; uma vez que
  8.1-8.3 produzam uma tabela de trajetórias (linhas = trajetória,
  colunas = lucro total/MDD/etc.), esta tarefa é mecânica, sem fórmula
  nova.
- [ ] "Probabilidade de tocar a margem"/"terminar abaixo do limiar" usam
  a mesma decisão de escala já resolvida para o limiar (posição total,
  não por contrato) — não é uma ambiguidade nova.

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

Nada implementado — o maior gap arquitetural encontrado até agora: todo
`tradefolio.*` opera sobre UM `ordens`/`diario` por vez; não existe
nenhum conceito de carregar e sincronizar múltiplos robôs simultaneamente.
`domain.py` já lista `Portfolio`/`PortfolioAllocation` como deliberadamente
não implementados por dependerem deste épico (Épico 2, tarefa 2.1).
`VERSOES["portfolio"]` já existe como `None` (tarefa 0.3). Tarefa 10.1 é
pré-requisito de tudo o resto do épico.

### Tarefa 10.1 — Sincronizar estratégias por data
- [ ] Carregar N `ordens`/`diario` (um por robô) e alinhá-los num índice
  de datas comum, distinguindo por (robô, data): não operou (já existe,
  `operou=False`), robô não existia ainda naquela data (série daquele
  robô não cobre essa data) e dado ausente (MISSING_DATA -- mesma lacuna
  já documentada como não implementada em `alignment.py` por falta de um
  sinal independente, tarefa 3.3; agora relevante em escala de
  portfólio, onde esse sinal passaria a existir: um robô ausente do
  portfólio quando outros do mesmo período têm dado é evidência de
  MISSING_DATA, não de NO_TRADE).
- [ ] Lugar natural: generalizar o padrão de
  `daily.pivotar_liquido_por_ativo` (hoje "por ativo dentro de um robô")
  para "por robô dentro de um portfólio" -- mesmo reshape, escopo maior.

### Tarefa 10.2 — Suportar quantidades e multiplicadores
- [ ] `PortfolioAllocation(strategy_id, multiplier, active_from)` — mapeia
  quase 1:1 sobre `StrategyConfiguration` (`domain.py`, já resolvido no
  Épico 2 com `valid_from`/`valid_to`); seria um dataclass irmão, não uma
  reformulação do que já existe.

### Tarefa 10.3 — Calcular métricas agregadas
- [ ] P&L, margem, MDD, ES, TUW, lucro mensal, custo total — a fórmula de
  cada uma já existe (`drawdowns.py`/`metrics.py`/`monthly.py`); a única
  coisa nova é aplicá-las à série COMBINADA das estratégias sincronizadas
  (10.1), não somar as métricas individuais (MDD de uma soma de séries
  não é a soma dos MDDs individuais).
- [ ] RLT — mesma composição de `limiar.rlt_*`, uma vez que exista um
  limiar agregado (tarefa 10.6).
- [ ] VLT — bloqueado pelo Épico 7 (vapo não existe).

### Tarefa 10.4 — Calcular correlações múltiplas
- [ ] "Correlação geral" é a mesma fórmula já usada em
  `report_data.calcular_pagina6` (Pearson sobre séries diárias
  sincronizadas), generalizada de ativos-dentro-de-um-robô para
  robôs-dentro-de-um-portfólio -- reuso direto do padrão, não uma fórmula
  nova.
- [ ] As outras 4 variantes (dias em que ambos operaram; piores 20%; alta
  volatilidade; perdas) são EXATAMENTE a mesma lacuna já documentada para
  `calcular_pagina6` (ver seção "Lâmina ideal.pdf — wiring" abaixo): cada
  uma exige decidir uma convenção extra (o que conta como "dia ruim"? qual
  limiar de volatilidade?) antes de codificar. Não é uma ambiguidade nova
  deste épico -- é a mesma adiada antes, reaparecendo em escala de
  portfólio.
- [ ] Correlação móvel (janela deslizante) — nova, mas mecânica uma vez
  que a correlação geral (par a par) exista.

### Tarefa 10.5 — Calcular contribuição marginal
- [ ] Para cada robô: recomputar o portfólio inteiro com e sem aquele
  robô (10.1–10.4) e diferenciar lucro/MDD/ES — mecânico uma vez que 10.1
  exista, mas caro computacionalmente (N+1 recomputações completas para N
  robôs; não otimizar prematuramente antes de medir).
- [ ] Diferença de limiar/VLT — herdam as dependências de 10.6 e do
  Épico 7 (VLT), respectivamente.

### Tarefa 10.6 — Calcular limiar agregado
- [ ] Fórmula dada explicitamente pelo PDF-fonte: `portfolio_threshold =
  total_minimum_margin + portfolio_tail_drawdown + uncertainty_premium +
  operational_reserve` — literalmente a mesma assinatura de
  `limiar.decompor_limiar`, só que alimentada pela margem mínima somada e
  pelo `drawdown_serie` da série COMBINADA (10.1/10.3) em vez de um único
  robô. Reuso direto, sem fórmula nova. O PDF-fonte avisa explicitamente
  para NÃO somar os limiares individuais -- o resultado agregado usa a
  MESMA função, só que sobre dados diferentes.

### Tarefa 10.7 — Calcular benefício da diversificação
- [ ] `soma dos limiares individuais - limiar agregado (10.6)`, em R$ e
  em % — trivial uma vez que 10.6 e a soma dos limiares individuais
  existam; nenhuma fórmula nova.

### Tarefa 10.8 — Otimização de portfólio
- [ ] Busca discreta (não otimização contínua, conforme o PDF-fonte pede
  explicitamente) sobre combinações de alocação, com objetivos
  configuráveis (maximizar RLT/VLT, minimizar MDD/L, maximizar lucro com
  limite de MDD, etc.) — decisão de dependência nova antes de começar
  (SciPy Optimize/CVXPY/Optuna/produto cartesiano discreto, AGENTS.md
  §18).
- [ ] O próprio PDF-fonte avisa para aplicar penalidade por múltiplas
  tentativas e nunca reportar só o melhor resultado da amostra (risco de
  sobreajuste de busca) — esse aviso deveria virar um requisito de teste
  (verificar que a busca não superajusta numa amostra sintética), não só
  uma nota de rodapé na implementação.

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
- [ ] **Limitação conhecida, não corrigida nesta rodada**: `app.py` já
  exigia `daily.detectar_contratos_referencia` funcionar sobre o CSV
  inteiro antes de mostrar qualquer página (`st.stop()` se falhar) —
  pré-existente, não introduzido aqui. Isso significa que a nova
  "Comparação entre ativos" fica, na prática, inatingível na página ao
  vivo para `orders_roboraiz.csv` (o único CSV de exemplo multi-ativo),
  porque esse CSV falha exatamente nessa checagem antiga (Épico 2.2:
  WDO não tem quantidade dominante). Verificado que a função/renderização
  em si funcionam corretamente via `report.py` (script direto) e via
  `AppTest` do Streamlit chamando `calcular_pagina6` fora desse guard.
  Corrigir isso exigiria decidir como `app.py` deveria se comportar sem
  um `contratos_referencia` único (ex.: permitir entrada manual) — fora
  do escopo pedido nesta rodada.

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
- [ ] **Não wireado em `app.py`/`report.py` nesta rodada** — o pedido foi
  sobre a lógica de cálculo ("deve ser contabilizado no lucro líquido e
  em seus indicadores derivados"), já satisfeito e verificado
  ponta-a-ponta a nível de biblioteca. Adicionar um input de UI (ex.
  `st.data_editor` para a tabela de faixas) é a extensão natural, mas é
  uma decisão de interface separada, não pedida ainda.
