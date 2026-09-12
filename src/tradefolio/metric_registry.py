"""Official metric dictionary (AGENTS.md épico 0, tarefas 0.1 e 0.2).

One `MetricSpec` per named metric emitted by `tradefolio.report_data`
(`calcular_pagina1/2/3`), keyed by the exact dict key those functions
return. This is deliberately a *separate, additive* registry rather than
wrapping each value in-place as `{"value": ..., "origin": ...}` the way
tarefa 0.2's example shows: doing that inline would change
`calcular_pagina1/2/3`'s return shape and break every existing consumer
(`report.py`, its tests) for a task that doesn't ask to touch presentation
code (AGENTS.md §4.4/§5). A consumer looks up a metric's origin/formula/
version by key instead.

`ARTEFATOS_DE_DADOS_EXCLUIDOS` lists dict keys that are NOT named metrics
but the raw table/series backing one (e.g. `piores_5` is the five-row
Series that `piores_5_media` averages) -- documented exclusions, not
silent omissions. `tests/test_metric_registry.py` enforces that every
other key `calcular_pagina1/2/3` emits has a registry entry, which is what
makes tarefa 0.1's acceptance criterion ("nenhuma métrica pode existir
apenas no componente visual") an enforced invariant instead of a promise.

`versao_etapa` references a key in `tradefolio.versions.VERSOES` rather
than duplicating a version string here, so the two can't drift apart.
"""
from dataclasses import dataclass

ORIGENS_VALIDAS = frozenset(
    {"observed", "calculated", "simulated", "user_input", "policy", "recommendation"}
)

ARTEFATOS_DE_DADOS_EXCLUIDOS = frozenset(
    {
        "trades", "episodios_drawdown", "piores_tuw", "serie", "piores_5", "melhores_5",
        # página 6 (comparação entre ativos): tabelas brutas, não métricas nomeadas --
        # correlacao_ativos é a matriz por trás de cada par lido individualmente;
        # compensacao_piores_dias é a tabela por trás da leitura "nos piores dias de
        # X, quanto Y ganhou" (não um único número).
        "correlacao_ativos", "compensacao_piores_dias",
    }
)


@dataclass(frozen=True)
class MetricSpec:
    id: str
    nome: str
    pagina: int
    formula: str
    frequencia: str
    unidade: str
    origem: str
    versao_etapa: str
    campos_necessarios: tuple
    tratamento_dado_ausente: str
    tratamento_custos: str
    interpretacao: str
    limitacoes: str


# -- textos compartilhados (evita repetir a mesma frase em ~50 entradas) --

_SESSAO_SEM_ORDEM = (
    "sessões B3 sem nenhuma ordem entram com resultado 0 e operou=False "
    "(tradefolio.alignment.preencher_calendario_b3); dado genuinamente "
    "ausente (MISSING_DATA) não é distinguído de dia sem operação "
    "(NO_TRADE) -- ver limitação conhecida no próprio módulo de alinhamento."
)
_MES_INCOMPLETO_NA = (
    "não aplicável neste nível -- a métrica opera sobre a série diária "
    "inteira, sem recorte por mês; ver tradefolio.monthly (mes_completo) "
    "para o nível mensal."
)
_TRATAMENTO_DIARIO_PADRAO = f"{_SESSAO_SEM_ORDEM} {_MES_INCOMPLETO_NA}"

_CUSTOS_LIQUIDO = "líquido de custos B3 (R$0,25/contrato/perna, cobrado em entrada e saída)."
_CUSTOS_BRUTO = "bruto -- não inclui custos B3 (ver a variante _liquido/_pct correspondente)."
_CUSTOS_ESTRUTURAL = "não aplicável -- métrica estrutural (contagem/intervalo de datas), não uma figura de resultado."

_CAMPOS_DIARIO = ("data", "bruto", "custo", "liquido", "liquido_por_contrato", "operou")
_CAMPOS_DIARIO_TOTAL = ("data", "bruto", "custo", "liquido", "operou")
_CAMPOS_ORDENS_TRADE = ("Data/Hora", "C/V", "Tipo", "Quantidade executada", "Resultado (R$)", "#")
_CAMPOS_ORDENS_POR_ATIVO = ("Data/Hora", "Ativo", "Status", "Tipo", "Quantidade executada", "Resultado (R$)")

_LIM_ROBO_UNICO = (
    "calculada sobre um único robô/CSV -- sem ajuste de portfólio, "
    "correlação ou diversificação (fora de escopo até o Épico 10)."
)
_LIM_SEM_LIMIAR = (
    "não normalizada pelo limiar (capital econômico) -- apenas em R$/R$-por-"
    "contrato/percentual do capital de referência fixo. Ver Épico 6 (fora "
    "de escopo desta fase)."
)


def _m(id, nome, pagina, formula, frequencia, unidade, origem, versao_etapa,
       campos_necessarios, interpretacao, limitacoes,
       tratamento_dado_ausente=_TRATAMENTO_DIARIO_PADRAO,
       tratamento_custos=_CUSTOS_LIQUIDO):
    return MetricSpec(
        id=id, nome=nome, pagina=pagina, formula=formula, frequencia=frequencia,
        unidade=unidade, origem=origem, versao_etapa=versao_etapa,
        campos_necessarios=campos_necessarios,
        tratamento_dado_ausente=tratamento_dado_ausente,
        tratamento_custos=tratamento_custos, interpretacao=interpretacao,
        limitacoes=limitacoes,
    )


_ENTRADAS = [
    # -- página 1: métricas diárias (tradefolio.report_data.calcular_pagina1) --
    _m("periodo", "Período coberto", 1,
       "(min(data), max(data)) da série diária alinhada ao calendário B3",
       "estática por relatório", "data", "observed", "calendario_b3", _CAMPOS_DIARIO,
       "Intervalo de datas que o relatório cobre -- não se estende além dos dados presentes no CSV.",
       "não indica se há lacunas de dado dentro do intervalo (ver operou/resultado_zero).",
       tratamento_custos=_CUSTOS_ESTRUTURAL),
    _m("pregoes", "Pregões no período", 1,
       "len(diario) -- contagem de sessões B3 entre a primeira e a última data dos dados",
       "estática por relatório", "contagem", "observed", "calendario_b3", _CAMPOS_DIARIO,
       "Quantos pregões B3 (operados ou não) o período contém.",
       "conta pregões calendário, não dias efetivamente operados (ver pct_dias_positivos/negativos/neutros).",
       tratamento_custos=_CUSTOS_ESTRUTURAL),
    _m("lucro_liquido_2c", "Lucro líquido total", 1,
       "sum(diario['liquido'])", "acumulada no período", "R$", "calculated",
       "agregacao_diaria", _CAMPOS_DIARIO,
       "Resultado líquido total no período, na escala de contratos de referência detectada do CSV (não necessariamente 2, apesar do nome histórico).",
       "o nome ('_2c') é um artefato histórico do código-fonte original -- não implica que o robô sempre opera com 2 contratos; ver lucro_liquido_por_contrato para a base normalizada."),
    _m("lucro_liquido_por_contrato", "Lucro líquido por contrato", 1,
       "sum(diario['liquido_por_contrato']) = sum(diario['liquido']) / contratos_referencia",
       "acumulada no período", "R$/contrato", "calculated", "agregacao_diaria", _CAMPOS_DIARIO,
       "Resultado líquido normalizado por contrato -- base usada por Sharpe/Sortino/Calmar/drawdown.",
       "assume escala linear em contratos (AGENTS.md §9) -- não vale para robôs com custos/slippage não lineares."),
    _m("media_diaria", "Média diária", 1, "mean(liquido_por_contrato)", "diária",
       "R$/contrato", "calculated", "metricas", _CAMPOS_DIARIO,
       "Resultado líquido médio por pregão (inclui dias sem operação como 0).", _LIM_SEM_LIMIAR),
    _m("media_diaria_dias_operados", "Média diária (dias operados)", 1,
       "mean(liquido_por_contrato onde operou=True)", "diária", "R$/contrato",
       "calculated", "metricas", _CAMPOS_DIARIO,
       "Resultado líquido médio só nos pregões em que houve trade -- exclui NO_TRADE do denominador, ao contrário de media_diaria (AGENTS.md épico 4.1).",
       "não distingue ZERO_RESULT (operou mas fechou zerado) de um dia realmente vencedor/perdedor -- ver resultado_zero para isso."),
    _m("mediana_diaria", "Mediana diária", 1, "median(liquido_por_contrato)", "diária",
       "R$/contrato", "calculated", "metricas", _CAMPOS_DIARIO,
       "Menos sensível a outliers que a média diária.", _LIM_SEM_LIMIAR),
    _m("pct_dias_positivos", "% de dias positivos", 1,
       "count(liquido_por_contrato > 0) / total de dias", "diária (agregada)", "fração [0,1]",
       "calculated", "metricas", _CAMPOS_DIARIO,
       "Fração de pregões com resultado líquido estritamente positivo.",
       "trata dia sem operação (resultado 0) como neutro, não como positivo nem negativo -- ver pct_dias_neutros."),
    _m("pct_dias_negativos", "% de dias negativos", 1,
       "count(liquido_por_contrato < 0) / total de dias", "diária (agregada)", "fração [0,1]",
       "calculated", "metricas", _CAMPOS_DIARIO,
       "Fração de pregões com resultado líquido estritamente negativo.", "ver pct_dias_positivos."),
    _m("pct_dias_neutros", "% de dias neutros", 1,
       "count(liquido_por_contrato == 0) / total de dias", "diária (agregada)", "fração [0,1]",
       "calculated", "metricas", _CAMPOS_DIARIO,
       "Fração de pregões com resultado líquido exatamente zero -- mistura NO_TRADE e ZERO_RESULT (AGENTS.md §10, tradefolio.alignment.resultado_zero).",
       "não distingue dia sem operação de dia operado que fechou exatamente zerado; use resultado_zero por dia para separar os dois."),
    _m("gain_medio", "Ganho médio", 1, "mean(liquido_por_contrato onde > 0)", "diária",
       "R$/contrato", "calculated", "metricas", _CAMPOS_DIARIO,
       "Tamanho médio dos dias vencedores.", "NaN quando não há nenhum dia positivo."),
    _m("loss_medio", "Perda média", 1, "mean(liquido_por_contrato onde < 0)", "diária",
       "R$/contrato", "calculated", "metricas", _CAMPOS_DIARIO,
       "Tamanho médio dos dias perdedores (valor negativo).", "NaN quando não há nenhum dia negativo."),
    _m("payoff", "Payoff diário", 1, "AGENTS.md §8.3: gain_medio / abs(loss_medio)",
       "diária (agregada)", "razão adimensional (ganho:perda)", "calculated", "metricas",
       _CAMPOS_DIARIO,
       "Quantas unidades de ganho médio por unidade de perda média absoluta.",
       "+inf sem perdas, 0.0 sem ganhos, NaN sem nenhum dos dois (convenção explícita, não implícita)."),
    _m("expectancia_diaria", "Expectância diária", 1,
       "AGENTS.md §8.4: win_prob*gain_medio - loss_prob*abs(loss_medio); algebricamente igual a mean(liquido_por_contrato)",
       "diária", "R$/contrato", "calculated", "metricas", _CAMPOS_DIARIO,
       "Resultado esperado por pregão, mesma base de trade-level vs day-level (AGENTS.md §8.1) -- este é o nível dia.",
       "idêntica numericamente a media_diaria; mantida como métrica separada porque nomeia explicitamente a convenção de expectância do domínio."),
    _m("profit_factor_diario", "Profit Factor diário", 1,
       "AGENTS.md §8.5: soma dos dias positivos / abs(soma dos dias negativos)",
       "diária (agregada)", "razão adimensional", "calculated", "metricas", _CAMPOS_DIARIO,
       "Quantos R$ ganhos por R$ perdido, agregando por dia (não por trade) -- ver profit_factor_trades para a base trade-level.",
       "+inf sem dias negativos, NaN sem nenhum dia com resultado não-zero."),
    _m("pior_dia", "Pior dia", 1, "min(liquido_por_contrato)", "diária", "R$/contrato",
       "calculated", "metricas", _CAMPOS_DIARIO, "Maior perda líquida em um único pregão.",
       "um único outlier extremo domina esta métrica; ver piores_5_media (página 3) para uma leitura menos sensível a um único dia."),
    _m("melhor_dia", "Melhor dia", 1, "max(liquido_por_contrato)", "diária", "R$/contrato",
       "calculated", "metricas", _CAMPOS_DIARIO, "Maior ganho líquido em um único pregão.",
       "um único outlier extremo domina esta métrica; ver melhores_5_media (página 3)."),
    _m("max_drawdown", "Maximum Drawdown (R$)", 1,
       "AGENTS.md §8.6: min(equity - running_max(equity)), equity = cumsum(liquido_por_contrato)",
       "diária (agregada)", "R$/contrato (valor ≤ 0)", "calculated", "drawdowns", _CAMPOS_DIARIO,
       "Maior queda da equity líquida acumulada desde um pico anterior.",
       "calculado sobre equity realizada (fechamentos diários), não considera posições em aberto intradiárias."),
    _m("max_drawdown_pct", "Maximum Drawdown (%)", 1,
       "min((patrimonio - running_max(patrimonio)) / running_max(patrimonio)) * 100, "
       "patrimonio = R$1.000/contrato (fixo) + equity_por_contrato",
       "diária (agregada)", "pontos percentuais (valor ≤ 0)", "calculated", "drawdowns",
       _CAMPOS_DIARIO,
       "MDD relativo ao pico móvel do patrimônio (não ao capital inicial fixo) -- convenção que reproduz o MDD% reportado pela própria Smarttbot (ver tests/fixtures/romanos_expected.md).",
       "R$1.000/contrato é uma convenção de referência da Smarttbot, não o capital real de conta do usuário."),
    _m("retorno_bruto_pct", "Retorno bruto (%)", 1,
       "sum(diario['bruto']) / contratos_referencia / R$1.000 * 100",
       "acumulada no período", "%", "calculated", "drawdowns", _CAMPOS_DIARIO,
       "Retorno bruto sobre o capital de referência fixo (R$1.000/contrato) -- não inclui custos B3.",
       _LIM_SEM_LIMIAR, tratamento_custos=_CUSTOS_BRUTO),
    _m("retorno_liquido_pct", "Retorno líquido (%)", 1,
       "sum(liquido_por_contrato) / R$1.000 * 100", "acumulada no período", "%", "calculated",
       "drawdowns", _CAMPOS_DIARIO,
       "Retorno líquido sobre o capital de referência fixo (R$1.000/contrato) -- base FIXA, diferente de max_drawdown_pct que usa o pico MÓVEL (AGENTS.md/CLAUDE.md: basis consistency).",
       _LIM_SEM_LIMIAR),
    _m("time_under_water_max_pregoes", "Time Under Water máximo", 1,
       "maior sequência contígua de pregões com drawdown < 0", "diária (agregada)", "pregões",
       "calculated", "drawdowns", _CAMPOS_DIARIO,
       "Quantos pregões seguidos, no pior caso, a equity ficou abaixo do pico anterior.",
       "medido em pregões (sessões B3), não em dias corridos nem em unidade de tempo relógio."),
    _m("ulcer_index_rs", "Ulcer Index (R$)", 1,
       "AGENTS.md §8.8: sqrt(mean(drawdown_rs**2))", "diária (agregada)", "R$/contrato",
       "calculated", "drawdowns", _CAMPOS_DIARIO,
       "Penaliza profundidade e duração do drawdown simultaneamente, ao contrário do MDD que só olha o pior ponto.",
       "sensível ao comprimento total da série -- não comparável diretamente entre períodos de duração muito diferente."),
    _m("ulcer_index_pct", "Ulcer Index (%)", 1,
       "sqrt(mean(drawdown_pct**2)) * 100, mesma base de patrimônio (pico móvel) de max_drawdown_pct",
       "diária (agregada)", "pontos percentuais", "calculated", "drawdowns", _CAMPOS_DIARIO,
       "Versão percentual do Ulcer Index, na mesma base de patrimônio de max_drawdown_pct.",
       "mesma ressalva de max_drawdown_pct sobre R$1.000/contrato ser uma convenção de referência."),
    _m("sharpe", "Sharpe", 1,
       "AGENTS.md §8.9: mean(liquido_por_contrato) / std(liquido_por_contrato) * sqrt(252)",
       "diária, anualizada", "adimensional", "calculated", "metricas", _CAMPOS_DIARIO,
       "Retorno médio por unidade de risco (desvio padrão total), anualizado por 252 pregões/ano.",
       "sem taxa livre de risco subtraída (equivalente a assumir risk-free=0); não recomendado para amostras curtas ou irregulares sem essa ressalva explícita."),
    _m("sortino", "Sortino", 1,
       "mean(liquido_por_contrato) / std(dias negativos) * sqrt(252)", "diária, anualizada",
       "adimensional", "calculated", "metricas", _CAMPOS_DIARIO,
       "Como Sharpe, mas penaliza só a volatilidade dos dias perdedores (downside deviation).",
       "downside deviation requer >=2 dias negativos para ter desvio padrão definido; NaN caso contrário."),
    _m("calmar", "Calmar", 1,
       "retorno_anualizado(liquido_por_contrato) / abs(max_drawdown)", "diária/anual",
       "adimensional", "calculated", "metricas", _CAMPOS_DIARIO,
       "Retorno anualizado por unidade de Maximum Drawdown -- mede retorno ajustado ao pior tombo histórico.",
       "retorno_anualizado usa dias corridos/365,25 (não dias úteis) para anualizar; NaN se max_drawdown for 0."),
    _m("recovery_factor", "Recovery Factor", 1,
       "sum(liquido_por_contrato) / abs(max_drawdown)", "acumulada no período", "adimensional",
       "calculated", "metricas", _CAMPOS_DIARIO,
       "Lucro total gerado por unidade de Maximum Drawdown sofrido.",
       "NaN se max_drawdown for 0; não anualizado (ao contrário de Calmar)."),
    _m("lucro_por_ativo", "Lucro líquido por ativo", 1,
       "groupby(ativo_raiz).liquido.sum() -- AGENTS.md épico 3.1/4.1, tradefolio.daily.agregar_diario_por_ativo",
       "acumulada no período", "R$ (escala bruta, não por contrato)", "calculated",
       "agregacao_diaria", _CAMPOS_ORDENS_POR_ATIVO,
       "Quebra do lucro líquido total por raiz de ativo (ex. WIN vs. WDO num robô multi-ativo) -- em calcular_pagina1 só aparece quando `ordens` é passado; em calcular_pagina6 é sempre calculada (lâmina ideal.pdf §12).",
       "escala bruta, não normalizada por contrato: um robô multi-ativo pode não ter uma única referência de contratos estável por ativo (ver tarefa 2.2/TASKS.md, caso real do WDO no Robô Raiz) -- dividir por contratos_referencia aqui misturaria escalas diferentes.",
       tratamento_dado_ausente="um (ativo) sem nenhuma ordem no período simplesmente não aparece no dict -- não é preenchido com zero (diferente do nível diário agregado, onde uma sessão sem ordem existe no calendário)."),

    # -- página 2: trades (tradefolio.report_data.calcular_pagina2) --
    _m("n_trades", "Número de trades", 2,
       "len(reconstruir_trades(ordens)) -- trades reconstruídos por posição líquida, não linhas de saída",
       "acumulada no período", "contagem", "calculated", "reconstrucao_trades",
       _CAMPOS_ORDENS_TRADE,
       "Quantos trades (entrada até posição líquida voltar a zero) o robô fez -- não é a contagem de linhas 'saída' (uma saída pode ser parcial/fracionada).",
       _LIM_ROBO_UNICO, tratamento_dado_ausente=_MES_INCOMPLETO_NA,
       tratamento_custos=_CUSTOS_ESTRUTURAL),
    _m("win_rate_trades", "Win rate (trades)", 2,
       "count(resultado_liquido do trade > 0) / total de trades", "acumulada no período",
       "fração [0,1]", "calculated", "metricas", _CAMPOS_ORDENS_TRADE,
       "Fração de trades individualmente vencedores -- base trade-level (AGENTS.md §8.1), não day-level.",
       "múltiplos trades no mesmo dia são apostas independentes na estratégia e não são nettados antes desta métrica (CLAUDE.md).",
       tratamento_dado_ausente=_MES_INCOMPLETO_NA),
    _m("profit_factor_trades", "Profit Factor (trades)", 2,
       "soma dos trades com resultado positivo / abs(soma dos trades com resultado negativo)",
       "acumulada no período", "razão adimensional", "calculated", "metricas",
       _CAMPOS_ORDENS_TRADE,
       "Profit Factor na base trade-level -- ver profit_factor_diario para a base day-level (podem divergir).",
       "+inf sem trades perdedores, NaN sem nenhum trade com resultado não-zero.",
       tratamento_dado_ausente=_MES_INCOMPLETO_NA),
    _m("lucro_medio_trade", "Lucro médio por trade", 2, "mean(resultado_liquido dos trades vencedores)",
       "acumulada no período", "R$", "calculated", "metricas", _CAMPOS_ORDENS_TRADE,
       "Tamanho médio de um trade vencedor, líquido de custos B3 do trade.", "NaN sem nenhum trade vencedor.",
       tratamento_dado_ausente=_MES_INCOMPLETO_NA),
    _m("prejuizo_medio_trade", "Prejuízo médio por trade", 2,
       "mean(resultado_liquido dos trades perdedores)", "acumulada no período", "R$",
       "calculated", "metricas", _CAMPOS_ORDENS_TRADE,
       "Tamanho médio de um trade perdedor (valor negativo), líquido de custos B3 do trade.",
       "NaN sem nenhum trade perdedor.", tratamento_dado_ausente=_MES_INCOMPLETO_NA),
    _m("expectancia_por_trade", "Expectância por operação", 2,
       "mean(resultado_liquido de todos os trades) -- AGENTS.md épico 4.5",
       "acumulada no período", "R$", "calculated", "metricas", _CAMPOS_ORDENS_TRADE,
       "Resultado esperado de um trade médio, líquido de custos B3; matematicamente idêntico à "
       "decomposição win_prob*ganho_medio - loss_prob*|perda_media| (ver tradefolio.metrics.expectancia).",
       "não pondera pelo tamanho da posição de cada trade.", tratamento_dado_ausente=_MES_INCOMPLETO_NA),
    _m("maior_sequencia_positiva_trades", "Maior sequência positiva (trades)", 2,
       "maior corrida de trades consecutivos com resultado_liquido > 0; retorna comprimento, valor_total e datas de início/fim do próprio trade",
       "acumulada no período", "composto (contagem, R$, datas)", "calculated",
       "reconstrucao_trades", _CAMPOS_ORDENS_TRADE,
       "Sequência vencedora mais longa e quanto ela valeu -- um streak de N trades a R$50 é diferente de um a R$5.000 (CLAUDE.md).",
       _LIM_ROBO_UNICO, tratamento_dado_ausente=_MES_INCOMPLETO_NA,
       tratamento_custos=_CUSTOS_LIQUIDO),
    _m("maior_sequencia_negativa_trades", "Maior sequência negativa (trades)", 2,
       "como maior_sequencia_positiva_trades, para resultado_liquido < 0",
       "acumulada no período", "composto (contagem, R$, datas)", "calculated",
       "reconstrucao_trades", _CAMPOS_ORDENS_TRADE,
       "Sequência perdedora mais longa e quanto ela custou.", _LIM_ROBO_UNICO,
       tratamento_dado_ausente=_MES_INCOMPLETO_NA),
    _m("maior_sequencia_positiva_dias", "Maior sequência positiva (dias)", 2,
       "maior corrida de pregões consecutivos com liquido_por_contrato > 0",
       "diária (agregada)", "composto (contagem, R$, datas)", "calculated", "metricas",
       _CAMPOS_DIARIO,
       "Sequência vencedora mais longa na base day-level (AGENTS.md §8.1) -- ver a versão _trades para a base trade-level.",
       "um dia exatamente zerado quebra a sequência em ambos os sentidos."),
    _m("maior_sequencia_negativa_dias", "Maior sequência negativa (dias)", 2,
       "como maior_sequencia_positiva_dias, para liquido_por_contrato < 0", "diária (agregada)",
       "composto (contagem, R$, datas)", "calculated", "metricas", _CAMPOS_DIARIO,
       "Sequência perdedora mais longa na base day-level.",
       "um dia exatamente zerado quebra a sequência em ambos os sentidos."),

    # -- página 3: distribuição e cauda (tradefolio.report_data.calcular_pagina3) --
    _m("media", "Média diária (distribuição)", 3, "mean(liquido_por_contrato)", "diária",
       "R$/contrato", "calculated", "metricas", _CAMPOS_DIARIO,
       "Idêntica a media_diaria da página 1 -- repetida aqui como base da seção de distribuição.",
       _LIM_SEM_LIMIAR),
    _m("mediana", "Mediana diária (distribuição)", 3, "median(liquido_por_contrato)", "diária",
       "R$/contrato", "calculated", "metricas", _CAMPOS_DIARIO,
       "Idêntica a mediana_diaria da página 1.", _LIM_SEM_LIMIAR),
    _m("desvio_padrao", "Desvio padrão diário", 3, "std(liquido_por_contrato)", "diária",
       "R$/contrato", "calculated", "metricas", _CAMPOS_DIARIO,
       "Dispersão total dos resultados diários -- denominador do Sharpe.", _LIM_SEM_LIMIAR),
    _m("skewness", "Assimetria (skewness)", 3, "pandas .skew() -- Fisher-Pearson amostral ajustada",
       "diária (agregada)", "adimensional", "calculated", "metricas", _CAMPOS_DIARIO,
       "Assimetria da distribuição diária -- negativa indica cauda de perdas mais longa que a de ganhos.",
       "sensível a outliers extremos em amostras pequenas."),
    _m("kurtosis", "Curtose em excesso", 3, "pandas .kurt() -- curtose em excesso amostral ajustada (normal = 0)",
       "diária (agregada)", "adimensional", "calculated", "metricas", _CAMPOS_DIARIO,
       "Peso das caudas da distribuição diária em relação à normal.",
       "sensível a outliers extremos em amostras pequenas."),
    _m("percentis", "Percentis da distribuição diária", 3,
       "percentile(liquido_por_contrato, p) para p em {1,5,10,25,50,75,90,95,99}, interpolação linear",
       "diária (agregada)", "R$/contrato", "calculated", "metricas", _CAMPOS_DIARIO,
       "Família de percentis da distribuição diária -- um dict {p: valor}, não um único número.",
       "interpolação linear padrão pandas/numpy; percentis extremos (1/99) são instáveis em amostras curtas."),
    _m("piores_5_media", "Média dos 5 piores dias", 3, "mean(5 menores valores de liquido_por_contrato)",
       "diária (agregada)", "R$/contrato", "calculated", "metricas", _CAMPOS_DIARIO,
       "Leitura de cauda menos sensível a um único outlier extremo que pior_dia.",
       "com menos de 5 pregões no período, a média é sobre menos de 5 dias (não é erro, mas reduz a robustez do número)."),
    _m("melhores_5_media", "Média dos 5 melhores dias", 3, "mean(5 maiores valores de liquido_por_contrato)",
       "diária (agregada)", "R$/contrato", "calculated", "metricas", _CAMPOS_DIARIO,
       "Leitura de concentração positiva menos sensível a um único outlier extremo que melhor_dia.",
       "com menos de 5 pregões no período, a média é sobre menos de 5 dias."),
    _m("var_95", "Value at Risk 95%", 3, "AGENTS.md §8.10: quantile(liquido_por_contrato, 0.05)",
       "diária (agregada)", "R$/contrato (valor com sinal, perda negativa)", "calculated",
       "metricas", _CAMPOS_DIARIO,
       "Perda que não deveria ser superada em 95% dos pregões, histórico (não paramétrico).",
       "amostra pequena torna quantis extremos instáveis; sem suposição de distribuição paramétrica."),
    _m("var_99", "Value at Risk 99%", 3, "quantile(liquido_por_contrato, 0.01)",
       "diária (agregada)", "R$/contrato (valor com sinal, perda negativa)", "calculated",
       "metricas", _CAMPOS_DIARIO, "Como var_95, para o quantil de 99%.",
       "mais sensível ainda que var_95 ao tamanho da amostra."),
    _m("es_95", "Expected Shortfall 95%", 3, "mean(liquido_por_contrato onde <= var_95)",
       "diária (agregada)", "R$/contrato (valor com sinal, perda negativa)", "calculated",
       "metricas", _CAMPOS_DIARIO,
       "Perda média condicional nos piores 5% dos pregões (cauda além do VaR 95%).",
       "em amostras pequenas pode coincidir com pior_dia (poucos pontos além do VaR)."),
    _m("es_99", "Expected Shortfall 99%", 3, "mean(liquido_por_contrato onde <= var_99)",
       "diária (agregada)", "R$/contrato (valor com sinal, perda negativa)", "calculated",
       "metricas", _CAMPOS_DIARIO, "Como es_95, para o quantil de 99%.",
       "em amostras pequenas, frequentemente coincide com pior_dia."),
    _m("n_dias_negativos", "Número de dias negativos", 3, "count(liquido_por_contrato < 0)",
       "acumulada no período", "contagem", "calculated", "metricas", _CAMPOS_DIARIO,
       "Quantos pregões fecharam com resultado líquido negativo.",
       "não distingue magnitude -- um dia com -R$1 conta igual a um dia com -R$10.000; ver var/es para magnitude de cauda."),

    # -- página 4: limiar e RLT (tradefolio.report_data.calcular_pagina4) --
    # Escala TOTAL (diario['liquido']), não por contrato -- minimum_margin é da
    # posição total (lâmina ideal.pdf §4/5/7; decisão de escala confirmada
    # nesta sessão, ver tradefolio.limiar).
    _m("meses_historico", "Meses de histórico", 4,
       "(max(data) - min(data)).days / 30,44", "estática por relatório", "meses",
       "observed", "agregacao_diaria", _CAMPOS_DIARIO_TOTAL,
       "Duração aproximada do histórico coberto -- alimenta history_uncertainty_multiplier.",
       "aproximação por dias corridos/30,44, não meses-calendário exatos.",
       tratamento_custos=_CUSTOS_ESTRUTURAL),
    _m("limiar_p95", "Decomposição do limiar (P95)", 4,
       "tradefolio.limiar.decompor_limiar com percentil_cauda=95 -- dict com "
       "minimum_margin/tail_drawdown_reserve/uncertainty_premium/operational_reserve/limiar_bruto/limiar_recomendado",
       "estática por relatório", "R$ (posição total)", "recommendation", "limiar",
       _CAMPOS_DIARIO_TOTAL,
       "Decomposição completa do limiar usando o percentil de cauda 95% -- mostrada sempre ao lado de limiar_p99 para comparação (resolução do usuário: mostrar os dois, não fixar um).",
       "depende de minimum_margin (user_input) e fracao_reserva_operacional (policy) fornecidos pelo chamador -- não é uma verdade estatística única.",
       tratamento_custos=_CUSTOS_ESTRUTURAL),
    _m("limiar_p99", "Decomposição do limiar (P99)", 4,
       "Como limiar_p95, com percentil_cauda=99", "estática por relatório",
       "R$ (posição total)", "recommendation", "limiar", _CAMPOS_DIARIO_TOTAL,
       "Decomposição completa do limiar usando o percentil de cauda 99% -- cauda mais conservadora que P95.",
       "mesma limitação de limiar_p95.", tratamento_custos=_CUSTOS_ESTRUTURAL),
    _m("percentil_cauda_ativo", "Percentil de cauda ativo", 4,
       "parâmetro escolhido pelo chamador (95 ou 99)", "estática por relatório",
       "percentil", "policy", "limiar", _CAMPOS_DIARIO_TOTAL,
       "Qual dos dois limiares (P95 ou P99) alimenta limiar_ativo/RLT/normalizações de risco desta página.",
       "escolha do usuário, não uma inferência do modelo.", tratamento_custos=_CUSTOS_ESTRUTURAL),
    _m("limiar_ativo", "Limiar ativo", 4,
       "limiar_p95 ou limiar_p99 (conforme percentil_cauda_ativo), arredondado se increment foi informado",
       "estática por relatório", "R$ (posição total)", "recommendation", "limiar",
       _CAMPOS_DIARIO_TOTAL,
       "O número único usado como denominador de RLT e das normalizações de risco desta página.",
       "herda as limitações de limiar_p95/limiar_p99.", tratamento_custos=_CUSTOS_ESTRUTURAL),
    _m("rlt_acumulado", "RLT acumulado", 4, "sum(liquido) / limiar_ativo",
       "acumulada no período", "razão (limiares)", "calculated", "limiar", _CAMPOS_DIARIO_TOTAL,
       "Retorno total do período expresso em múltiplos do limiar -- a métrica central sugerida pela lâmina ideal (§5/§24).",
       "sensível à escolha de percentil_cauda_ativo/fracao_reserva_operacional -- não compare RLT de robôs calculados com parâmetros de limiar diferentes."),
    _m("rlt_anualizado", "RLT anualizado", 4, "retorno_anualizado(liquido) / limiar_ativo",
       "anualizada", "razão (limiares) por ano", "calculated", "limiar", _CAMPOS_DIARIO_TOTAL,
       "Ritmo anualizado de geração de retorno relativo ao limiar.",
       "herda a limitação de metrics.retorno_anualizado (dias corridos/365,25, não dias úteis)."),
    _m("rlt_mensal_medio", "RLT mensal médio", 4, "mean(liquido_mensal / limiar_ativo)",
       "mensal (agregada)", "razão (limiares)", "calculated", "limiar", _CAMPOS_DIARIO_TOTAL,
       "Média dos RLTs mensais -- sensível a poucos meses excepcionais.",
       "ver rlt_mensal_mediano para uma leitura menos sensível a outliers."),
    _m("rlt_mensal_mediano", "RLT mensal mediano", 4, "median(liquido_mensal / limiar_ativo)",
       "mensal (agregada)", "razão (limiares)", "calculated", "limiar", _CAMPOS_DIARIO_TOTAL,
       "Mediana dos RLTs mensais -- menos sensível a um único mês excepcional que a média.",
       "com poucos meses de histórico, a mediana é instável."),
    _m("rlt_movel_3", "RLT móvel 3 meses", 4, "sum(últimos 3 liquido_mensal) / limiar_ativo (último valor da série)",
       "móvel mensal", "razão (limiares)", "calculated", "limiar", _CAMPOS_DIARIO_TOTAL,
       "Ritmo recente (3 meses) de RLT -- mais sensível a mudanças recentes que o acumulado.",
       "NaN se houver menos de 3 meses de histórico."),
    _m("rlt_movel_6", "RLT móvel 6 meses", 4, "Como rlt_movel_3, janela de 6 meses",
       "móvel mensal", "razão (limiares)", "calculated", "limiar", _CAMPOS_DIARIO_TOTAL,
       "Ritmo recente (6 meses) de RLT.", "NaN se houver menos de 6 meses de histórico."),
    _m("rlt_movel_12", "RLT móvel 12 meses", 4, "Como rlt_movel_3, janela de 12 meses",
       "móvel mensal", "razão (limiares)", "calculated", "limiar", _CAMPOS_DIARIO_TOTAL,
       "Ritmo recente (12 meses) de RLT -- aproxima uma leitura anual sem esperar o ano-calendário fechar.",
       "NaN se houver menos de 12 meses de histórico."),
    _m("mdd_total", "Maximum Drawdown (total)", 4,
       "Como max_drawdown (página 1), mas sobre diario['liquido'] (escala total, não por contrato)",
       "diária (agregada)", "R$ (posição total, valor ≤ 0)", "calculated", "drawdowns",
       _CAMPOS_DIARIO_TOTAL, "MDD na mesma escala de minimum_margin, para compor mdd_sobre_limiar.",
       "mesma limitação de max_drawdown -- equity realizada, não posições intradiárias em aberto."),
    _m("mdd_sobre_limiar", "MDD / limiar (MDD/L)", 4, "mdd_total / limiar_ativo",
       "diária (agregada)", "razão (limiares, valor ≤ 0)", "calculated", "limiar",
       _CAMPOS_DIARIO_TOTAL,
       "Quanto do capital operacional recomendado o pior tombo histórico consumiria -- lâmina ideal §24.",
       "herda as limitações de mdd_total e do limiar escolhido."),
    _m("pior_dia_total", "Pior dia (total)", 4, "min(liquido) (escala total)",
       "diária", "R$ (posição total)", "calculated", "metricas", _CAMPOS_DIARIO_TOTAL,
       "Maior perda líquida em um único pregão, na escala total.",
       "um único outlier extremo domina esta métrica."),
    _m("pior_dia_sobre_limiar", "Pior dia / limiar", 4, "pior_dia_total / limiar_ativo",
       "diária", "razão (limiares)", "calculated", "limiar", _CAMPOS_DIARIO_TOTAL,
       "O pior pregão histórico expresso como fração do limiar.",
       "herda as limitações de pior_dia_total."),
    _m("es95_total", "Expected Shortfall 95% (total)", 4,
       "Como es_95 (página 3), mas sobre diario['liquido']", "diária (agregada)",
       "R$ (posição total, valor com sinal)", "calculated", "metricas", _CAMPOS_DIARIO_TOTAL,
       "Perda média condicional nos piores 5% dos pregões, escala total.",
       "mesma limitação de es_95 -- amostra pequena torna a cauda instável."),
    _m("es95_sobre_limiar", "ES95 / limiar", 4, "es95_total / limiar_ativo",
       "diária (agregada)", "razão (limiares)", "calculated", "limiar", _CAMPOS_DIARIO_TOTAL,
       "Perda esperada de cauda expressa como fração do limiar -- ES/L sugerido pela lâmina ideal §24.",
       "herda as limitações de es95_total."),
    _m("ulcer_total", "Ulcer Index (total)", 4,
       "Como ulcer_index_rs (página 1), mas sobre diario['liquido']", "diária (agregada)",
       "R$ (posição total)", "calculated", "drawdowns", _CAMPOS_DIARIO_TOTAL,
       "Penalidade de drawdown profundo e prolongado, escala total.",
       "mesma limitação do Ulcer Index padrão -- não distingue um drawdown raso e longo de um fundo e curto com a mesma área."),
    _m("ulcer_sobre_limiar", "Ulcer / limiar", 4, "ulcer_total / limiar_ativo",
       "diária (agregada)", "razão (limiares)", "calculated", "limiar", _CAMPOS_DIARIO_TOTAL,
       "Ulcer Index expresso como fração do limiar.", "herda as limitações de ulcer_total."),
    _m("pior_mes_total", "Pior mês (total)", 4, "min(liquido mensal), escala total",
       "mensal (agregada)", "R$ (posição total)", "calculated", "consolidacao_mensal",
       _CAMPOS_DIARIO_TOTAL, "Pior resultado líquido mensal, escala total.",
       "um único mês atípico domina esta métrica."),
    _m("pior_mes_sobre_limiar", "Pior mês / limiar", 4, "pior_mes_total / limiar_ativo",
       "mensal (agregada)", "razão (limiares)", "calculated", "limiar", _CAMPOS_DIARIO_TOTAL,
       "Pior mês histórico expresso como fração do limiar.", "herda as limitações de pior_mes_total."),

    # -- página 5: qualidade da curva (tradefolio.report_data.calcular_pagina5) --
    _m("top1_dia", "Participação do melhor dia", 5, "concentracao.participacao_top_n(liquido, 1)",
       "acumulada no período", "fração do lucro total", "calculated", "concentracao",
       _CAMPOS_DIARIO_TOTAL,
       "Quanto do lucro total veio de um único melhor dia -- sinal de concentração (lâmina ideal §9).",
       "não limitada a [0,1] -- se o total for pequeno/negativo, a fração pode passar de 100% (sinal genuíno de concentração patológica, não erro)."),
    _m("top5_dias", "Participação dos 5 melhores dias", 5, "concentracao.participacao_top_n(liquido, 5)",
       "acumulada no período", "fração do lucro total", "calculated", "concentracao",
       _CAMPOS_DIARIO_TOTAL, "Como top1_dia, para os 5 melhores dias.", "ver top1_dia."),
    _m("top10_dias", "Participação dos 10 melhores dias", 5, "concentracao.participacao_top_n(liquido, 10)",
       "acumulada no período", "fração do lucro total", "calculated", "concentracao",
       _CAMPOS_DIARIO_TOTAL, "Como top1_dia, para os 10 melhores dias.", "ver top1_dia."),
    _m("melhor_mes_share", "Participação do melhor mês", 5, "concentracao.participacao_top_n(liquido_mensal, 1)",
       "acumulada no período", "fração do lucro total", "calculated", "concentracao",
       _CAMPOS_DIARIO_TOTAL, "Quanto do lucro total veio de um único melhor mês.", "ver top1_dia."),
    _m("top3_meses_share", "Participação dos 3 melhores meses", 5, "concentracao.participacao_top_n(liquido_mensal, 3)",
       "acumulada no período", "fração do lucro total", "calculated", "concentracao",
       _CAMPOS_DIARIO_TOTAL, "Como melhor_mes_share, para os 3 melhores meses.", "ver top1_dia."),
    _m("lucro_sem_melhor_dia", "Lucro sem o melhor dia", 5, "concentracao.resultado_sem_top_n(liquido, 1)",
       "acumulada no período", "R$ (posição total)", "calculated", "concentracao",
       _CAMPOS_DIARIO_TOTAL,
       "Lucro total removendo o melhor dia isolado -- se ficar negativo, o robô depende de um único evento.",
       "remover um evento não simula o que teria acontecido sem ele (a estratégia poderia ter operado diferente)."),
    _m("lucro_sem_top5_dias", "Lucro sem os 5 melhores dias", 5, "concentracao.resultado_sem_top_n(liquido, 5)",
       "acumulada no período", "R$ (posição total)", "calculated", "concentracao",
       _CAMPOS_DIARIO_TOTAL, "Como lucro_sem_melhor_dia, para os 5 melhores dias.", "ver lucro_sem_melhor_dia."),
    _m("lucro_sem_melhor_mes", "Lucro sem o melhor mês", 5, "concentracao.resultado_sem_top_n(liquido_mensal, 1)",
       "acumulada no período", "R$ (posição total)", "calculated", "concentracao",
       _CAMPOS_DIARIO_TOTAL, "Lucro total removendo o melhor mês isolado.", "ver lucro_sem_melhor_dia."),
    _m("lucro_sem_top3_meses", "Lucro sem os 3 melhores meses", 5, "concentracao.resultado_sem_top_n(liquido_mensal, 3)",
       "acumulada no período", "R$ (posição total)", "calculated", "concentracao",
       _CAMPOS_DIARIO_TOTAL, "Como lucro_sem_melhor_mes, para os 3 melhores meses.", "ver lucro_sem_melhor_dia."),
    _m("lucro_antes_dos_ultimos_60_dias", "Lucro antes dos últimos 60 dias", 5,
       "concentracao.resultado_antes_dos_ultimos_n_dias(liquido, 60)", "acumulada no período",
       "R$ (posição total)", "calculated", "concentracao", _CAMPOS_DIARIO_TOTAL,
       "Se positivo, o robô já era lucrativo antes do período recente -- detecta 'curva salva recentemente'.",
       "posicional (cronológico), não por ranking de valor -- NaN se a série tiver 60 dias ou menos."),
    _m("pct_dias_abaixo_de_zero", "% de pregões com equity negativa", 5,
       "concentracao.pct_dias_abaixo_de_zero(equity)", "acumulada no período", "fração [0,1]",
       "calculated", "concentracao", _CAMPOS_DIARIO_TOTAL,
       "Fração do histórico em que a equity acumulada (não relativa ao pico) esteve negativa.",
       "equity acumulada desde o início da amostra, não desde um capital inicial arbitrário."),
    _m("ultima_data_negativa", "Última data com equity negativa", 5,
       "concentracao.ultima_data_negativa(equity)", "estática por relatório", "data",
       "observed", "concentracao", _CAMPOS_DIARIO_TOTAL,
       "Há quanto tempo o robô está consolidado em território positivo.",
       "None se a equity nunca ficou negativa na amostra -- não confundir com 'sem dados'.",
       tratamento_custos=_CUSTOS_ESTRUTURAL),
    _m("pregoes_desde_consolidacao_positiva", "Pregões desde a consolidação positiva", 5,
       "concentracao.pregoes_desde_consolidacao_positiva(equity)", "acumulada no período",
       "contagem de pregões", "calculated", "concentracao", _CAMPOS_DIARIO_TOTAL,
       "Quantos pregões se passaram desde a última vez que a equity esteve negativa.",
       "0 se a amostra ainda termina negativa (não recuperou) -- não inventa uma consolidação que não aconteceu."),
    _m("alertas", "Alertas automáticos de qualidade da curva", 5,
       "concentracao.detectar_alertas_curva -- 3 regras determinísticas do PDF-fonte",
       "estática por relatório", "lista de alertas estruturados", "calculated", "concentracao",
       _CAMPOS_DIARIO_TOTAL,
       "NEGATIVE_BEFORE_LAST_60_DAYS, PROFIT_SAVED_BY_BEST_MONTH, TOP3_EXCEEDS_TOTAL_PROFIT -- schema warning_code/severity/metric/observed_value/threshold/message (lâmina ideal §17).",
       "só as 3 regras com limiar numérico explícito no PDF-fonte -- os demais warning_code do §17 (SHORT_HISTORY, QUANTITY_CHANGE, etc.) não têm limiar definido e não foram implementados.",
       tratamento_custos=_CUSTOS_ESTRUTURAL),

    # -- página 6: comparação entre ativos (tradefolio.report_data.calcular_pagina6) --
    # só chamada para robôs multi-ativo (lâmina ideal.pdf §12); "lucro_por_ativo" é
    # a mesma entrada já registrada para a página 1.
    _m("ativos", "Ativos do robô", 6, "list(tradefolio.daily.pivotar_liquido_por_ativo(ordens).columns)",
       "estática por relatório", "lista de raízes de ativo", "observed", "agregacao_diaria",
       _CAMPOS_ORDENS_POR_ATIVO, "Quais raízes de ativo (ex. WIN, WDO) compõem o robô.",
       "raiz do contrato, não o código completo -- não distingue vencimentos.",
       tratamento_custos=_CUSTOS_ESTRUTURAL),
    _m("mdd_por_ativo", "Maximum Drawdown por ativo", 6,
       "drawdowns aplicado à série pivotada de cada ativo_raiz isoladamente",
       "diária (agregada)", "R$ por ativo (valor ≤ 0)", "calculated", "drawdowns",
       _CAMPOS_ORDENS_POR_ATIVO,
       "MDD de cada perna do robô isolada -- responde 'o MDD conjunto é menor que a soma?' (lâmina ideal §12) quando comparado ao MDD total.",
       "calculado como se cada ativo fosse operado isoladamente -- ignora qualquer efeito de margem/custo conjunto entre pernas."),
]

REGISTRO: dict[str, MetricSpec] = {spec.id: spec for spec in _ENTRADAS}
