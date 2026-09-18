"""Portfolio Builder -- fluxo guiado de decisão (backlog de
`prompts/portfolioBuilder.pdf`, fora dos épicos do PDF-fonte).

Este módulo é uma camada de ORQUESTRAÇÃO sobre o engine já existente em
`tradefolio.portfolio`/`limiar`/`drawdowns`/`metrics`/`report_data` --
nenhuma fórmula financeira nova é definida aqui (AGENTS.md §8). A
distinção do resto do projeto ("Portfolio Lab"): o Lab responde "o que
consigo descobrir sobre esta carteira?" com métricas completas e
controles avançados; o Builder responde "que carteira devo considerar?"
coletando decisões progressivamente e devolvendo só as conclusões
necessárias em cada etapa -- a metodologia completa continua acessível
(cada função aqui documenta exatamente quais primitivas já existentes
ela reusa), só não é o padrão exibido.

Decisões confirmadas com o usuário antes de implementar (AGENTS.md §24):
- Reconciliar o orçamento de risco top-down do usuário contra o que o
  modelo de limiar já existente diz que a história realmente exige, em
  vez de aceitar silenciosamente um teto irrealista.
- Concentração por robô/cluster usa contribuição ao DRAWDOWN (não
  margem, não contagem de contratos) -- ver a extensão de
  `buscar_combinacoes_portfolio_com_filtros` em `tradefolio.portfolio`.
- Cenário de degradação por EA reaberto (estava excluído do Monte Carlo
  de portfólio em geral), mas só para o finalista JÁ ESCOLHIDO, não a
  grade inteira de busca -- custo é aceitável uma vez, não milhares de
  vezes.
- "Qualidade dos dados"/"infraestrutura compartilhada" -- OMITIDOS
  nesta versão. Nenhum dos dois conceitos existe no modelo de dados
  hoje (nenhuma coluna de CSV captura conta real vs. simulada, ou
  infraestrutura de execução); TASKS.md já sinaliza "qualidade dos
  dados" como Épico 14 do PDF-fonte, explicitamente fora de escopo.
  Inventar um score aqui violaria AGENTS.md §8/§10.
"""
import math

from tradefolio.deterioracao import reduzir_ganhos
from tradefolio.drawdowns import curva_equity, drawdown, maximo_drawdown, time_under_water_max
from tradefolio.portfolio import _metricas_de_alocacao, _sincronizar_alocacao
from tradefolio.report_data import calcular_pagina4


def montar_cartao_ea(
    diario,
    margem_por_contrato: float = None,
    percentil_cauda: int = 95,
    fracao_melhores_dias: float = 0.05,
    limiar_historico_curto_meses: float = 9,
) -> dict:
    """Passo 1 do Builder ("selecionar os EAs candidatos") -- um cartão
    curto por EA, cada campo reusando uma função já existente, nada
    inventado:

    - `pregoes`/`meses_historico`: do próprio índice de datas do
      `diario` (mesmo cálculo de `meses_historico` que
      `report_data.calcular_pagina4` já faz).
    - `mdd_por_contrato`/`pior_dia_por_contrato`/`tempo_max_recuperacao`:
      sobre `diario["liquido_por_contrato"]` (`drawdowns.*`, já
      existentes).
    - `dependencia_5_melhores_dias_pct`: mesma ideia de corte por
      quantil que `metrics.var_historico` usa para a cauda inferior,
      aqui aplicada ao lado SUPERIOR da série (`serie.quantile(1 -
      fracao_melhores_dias)`) -- `(lucro_total - resultado_sem_melhores)
      / lucro_total * 100`. Pode passar de 100% quando o resultado sem
      os melhores dias é negativo (a dependência é maior que o próprio
      lucro final) -- não é um erro, é informação real sobre
      concentração.
    - `rlt_por_contrato`: **só calculado se `margem_por_contrato` for
      informado** -- `report_data.calcular_pagina4` só existe na escala
      TOTAL (confirmado por leitura do próprio código/docstring dessa
      função); alimentá-la com o `diario` na escala de REFERÊNCIA
      (`liquido` = `liquido_por_contrato`) e a margem POR CONTRATO como
      `minimum_margin` faz sua saída já existente (`rlt_acumulado`) sair
      correta por-contrato -- é reconexão, não uma fórmula nova.
      `None` (nunca um número inventado) se a margem não foi informada
      ainda nesta etapa do fluxo.
    - `alerta_historico_curto`: usa o mesmo degrau de 9 meses já
      documentado em `limiar._DEGRAUS_INCERTEZA` (a convenção de
      "histórico curto" já existente no projeto), não um novo corte."""
    serie = diario["liquido_por_contrato"]
    dd = drawdown(curva_equity(serie))
    meses_historico = (serie.index.max() - serie.index.min()).days / 30.44

    limite_superior = serie.quantile(1 - fracao_melhores_dias)
    lucro_total = serie.sum()
    resultado_sem_melhores = serie[serie < limite_superior].sum()
    dependencia_pct = (lucro_total - resultado_sem_melhores) / lucro_total * 100

    rlt_por_contrato = None
    if margem_por_contrato is not None:
        diario_referencia = diario.copy()
        diario_referencia["liquido"] = diario["liquido_por_contrato"]
        rlt_por_contrato = calcular_pagina4(
            diario_referencia, minimum_margin=margem_por_contrato, percentil_cauda=percentil_cauda,
        )["rlt_acumulado"]

    return {
        "pregoes": len(diario),
        "meses_historico": meses_historico,
        "mdd_por_contrato": maximo_drawdown(dd),
        "pior_dia_por_contrato": serie.min(),
        "tempo_max_recuperacao": time_under_water_max(dd),
        "dependencia_5_melhores_dias_pct": dependencia_pct,
        "rlt_por_contrato": rlt_por_contrato,
        "alerta_historico_curto": meses_historico < limiar_historico_curto_meses,
    }


def orcamento_de_risco(
    capital_reservado: float,
    perda_maxima_aceitavel: float,
    margem_seguranca_pct: float,
    mdd_historico_referencia: float = None,
    limiar_referencia: float = None,
) -> dict:
    """Passo 2 do Builder ("definir o orçamento de risco") --
    `mdd_projeto = perda_maxima_aceitavel × (1 - margem_seguranca_pct/100)`
    (exemplo do documento-fonte: R$15.000 × 70% = R$10.500, reproduzido
    em teste). Puramente aritmético -- nenhuma fórmula nova.

    Reconciliação (**decisão confirmada com o usuário**, AGENTS.md §24 --
    não aceitar silenciosamente um teto irrealista): quem chama calcula,
    numa carteira de REFERÊNCIA (1 contrato de cada EA candidato, ainda
    sem escolha de contratos nesta etapa):
    - `mdd_historico_referencia`: o MDD histórico real dessa carteira de
      referência (`drawdowns.maximo_drawdown` sobre a série combinada,
      via `portfolio.metricas_agregadas`) -- comparado em MAGNITUDE
      contra `mdd_projeto` (`abaixo_do_historico=True` quando o teto do
      usuário é mais apertado do que o que já aconteceu historicamente
      com a alocação mínima).
    - `limiar_referencia`: o limiar de capital dessa mesma carteira de
      referência (`portfolio.limiar_agregado_portfolio`) -- comparado
      contra `capital_reservado` (`capital_insuficiente=True` quando o
      capital reservado é menor que o que o modelo de limiar já
      existente diz ser necessário).
    Ambos os campos ficam `None` (nunca inventados) quando a referência
    correspondente não foi informada."""
    mdd_projeto = perda_maxima_aceitavel * (1 - margem_seguranca_pct / 100)

    abaixo_do_historico = None
    if mdd_historico_referencia is not None:
        abaixo_do_historico = mdd_projeto < abs(mdd_historico_referencia)

    capital_insuficiente = None
    if limiar_referencia is not None:
        capital_insuficiente = capital_reservado < limiar_referencia

    return {
        "mdd_projeto": mdd_projeto,
        "mdd_historico_referencia": mdd_historico_referencia,
        "abaixo_do_historico": abaixo_do_historico,
        "limiar_referencia": limiar_referencia,
        "capital_insuficiente": capital_insuficiente,
    }


def cenario_degradacao_finalista(
    diarios_referencia: dict,
    alocacao: dict,
    margens_por_contrato: dict,
    robo_degradado: str,
    fracao_degradacao: float,
    percentil_cauda: int = 95,
    fracao_reserva_operacional: float = 0.0,
    increment: float = None,
    usar_janela_comum: bool = True,
) -> dict:
    """Passo 6 do Builder ("cenário de degradação") -- **decisão
    confirmada com o usuário** (AGENTS.md §24): reabre o esquema D
    (degradação de edge), excluído do Monte Carlo de portfólio em geral
    (grade de busca inteira -- caro demais rodar por milhares de
    combinações), mas SÓ para o finalista JÁ ESCOLHIDO nesta etapa --
    custo aceitável uma vez.

    Recompute DETERMINÍSTICO, não Monte Carlo -- "se o EA X perder Y% da
    expectativa" é um único cenário (documento-fonte: "o retorno
    estimado cai X% e o drawdown sobe para R$Y"), não uma distribuição.
    Reusa `deterioracao.reduzir_ganhos` (já existente, já testado no
    modo Robô único) sobre a série de referência de UM robô só, dentro
    da `alocacao` já fixada -- nenhuma fórmula nova. `fracao_degradacao`
    mapeia direto para a linguagem do documento-fonte: `0.25` → "cai
    25%", `0.5` → "cai 50%", `1.0` → "vai a zero" (zera os dias
    positivos, só sobram as perdas), `>1.0` → "torna-se negativa"
    (`reduzir_ganhos` multiplica os dias positivos por `1 - fracao`, que
    fica negativo quando `fracao > 1` -- mesma função, nenhum caso
    especial).

    Reusa `_sincronizar_alocacao`/`_metricas_de_alocacao` de
    `tradefolio.portfolio` (mesmo pipeline por-alocação já usado por
    `buscar_combinacoes_portfolio_com_filtros`/`vizinhanca_local`/
    `shortlist_portfolio`) -- roda duas vezes (baseline e degradado) só
    para o robô/alocação indicados, não a grade inteira.

    Retorna `{"baseline": ..., "degradado": ..., "delta_lucro_total":
    ..., "delta_mdd": ..., "robo_degradado": ..., "fracao_degradacao":
    ...}` -- `baseline`/`degradado` no mesmo formato de resultado de
    `buscar_combinacoes_portfolio` (alocacao/lucro_total/mdd/es_95/
    limiar_ativo/rlt_acumulado/mdd_sobre_limiar).

    Levanta `KeyError` se `robo_degradado` não estiver em
    `diarios_referencia` -- não há o que degradar de um robô que não
    existe na alocação."""
    if robo_degradado not in diarios_referencia:
        raise KeyError(f"robo_degradado {robo_degradado!r} não está em diarios_referencia")

    def _avaliar(diarios: dict) -> dict:
        largo, margens_ativas = _sincronizar_alocacao(
            alocacao, diarios, margens_por_contrato, usar_janela_comum,
        )
        if largo is None:
            raise ValueError(
                "A alocação não tem janela comum ou é degenerada (0 contratos em todos os robôs)"
            )
        return _metricas_de_alocacao(
            alocacao, largo, margens_ativas, percentil_cauda, fracao_reserva_operacional, increment,
        )

    baseline = _avaliar(diarios_referencia)

    diarios_degradados = dict(diarios_referencia)
    diario_degradado = diarios_referencia[robo_degradado].copy()
    diario_degradado["liquido_por_contrato"] = reduzir_ganhos(
        diarios_referencia[robo_degradado]["liquido_por_contrato"], fracao_degradacao,
    )
    diarios_degradados[robo_degradado] = diario_degradado
    degradado = _avaliar(diarios_degradados)

    return {
        "baseline": baseline,
        "degradado": degradado,
        "delta_lucro_total": degradado["lucro_total"] - baseline["lucro_total"],
        "delta_mdd": degradado["mdd"] - baseline["mdd"],
        "robo_degradado": robo_degradado,
        "fracao_degradacao": fracao_degradacao,
    }


def plano_operacional(
    alocacao_final: dict,
    margens_por_contrato: dict,
    capital_reservado: float,
    mdd_projeto: float,
    mdd_p95_estimado: float = None,
    pior_dia_historico: float = None,
    limite_risco_por_robo_pct: float = 45.0,
    faixas_pct: tuple = (0.50, 0.75, 1.0),
) -> dict:
    """Passo 7 do Builder ("produzir o plano operacional") -- formatação/
    bandas PURAS sobre números já calculados nos passos anteriores,
    nenhuma fórmula nova.

    `faixas_pct` (padrão 50%/75%/100% do `mdd_projeto`, positivo --
    mesma convenção de `orcamento_de_risco`) é um parâmetro EXPLÍCITO e
    ajustável, não um corte hardcoded escondido -- mesmo tratamento de
    todo outro "knob" de política já existente neste projeto
    (`fracao_reserva_operacional`, `tolerancia_robustez_pct`, etc.). Não
    é uma reprodução literal dos números de exemplo do documento-fonte
    (R$0-5.000/5.000-7.500/7.500-10.500 para um `mdd_projeto` de
    R$10.500 -- essas frações não são redondas, são só um exemplo
    ilustrativo, não uma fórmula declarada).

    `limite_risco_por_robo_pct` (padrão 45.0, o próprio número de
    exemplo do documento-fonte) alimenta a regra "um EA superar X% da
    contribuição de risco" -- se o usuário informou um limite diferente
    no Passo 3 (`limite_risco_por_robo_pct` de `buscar_combinacoes_
    portfolio_com_filtros`), passe-o aqui para a regra refletir a
    escolha real, não o exemplo do documento.

    Retorna `faixas` (lista de `{"min_dd", "max_dd", "acao"}`, valores
    numéricos puros -- formatação de moeda é responsabilidade de quem
    exibe, não deste módulo) e as regras de acompanhamento separadas em
    `regras_estaticas` (aplicam sempre) e `regras_nao_computadas` -- as
    duas do documento-fonte ("replicabilidade caiu abaixo de 95%",
    "comportamento saiu do envelope simulado") que exigiriam
    infraestrutura de acompanhamento AO VIVO (a seção "Monitor" que o
    próprio documento-fonte propõe como área separada, fora de escopo
    desta versão) -- nunca fingidas como sinal automático já calculado."""
    margem_maxima_estimada = sum(
        margens_por_contrato[nome] * n_contratos for nome, n_contratos in alocacao_final.items()
    )

    limites_dd = [0.0] + [f * mdd_projeto for f in faixas_pct]
    rotulos_acao = [
        "Operação normal.",
        "Não aumentar a mão.",
        "Reduzir e investigar.",
        "Suspender novas entradas e revisar o portfólio.",
    ]
    faixas = [
        {
            "min_dd": limites_dd[i],
            "max_dd": limites_dd[i + 1] if i + 1 < len(limites_dd) else math.inf,
            "acao": rotulos_acao[i],
        }
        for i in range(len(rotulos_acao))
    ]

    return {
        "alocacao_final": alocacao_final,
        "capital_reservado": capital_reservado,
        "mdd_projeto": mdd_projeto,
        "mdd_p95_estimado": mdd_p95_estimado,
        "pior_dia_historico": pior_dia_historico,
        "margem_maxima_estimada": margem_maxima_estimada,
        "faixas": faixas,
        "limite_risco_por_robo_pct": limite_risco_por_robo_pct,
        "regras_estaticas": [
            "Revisão mensal, sem alterar contratos diariamente.",
            "A correlação de cauda entre os EAs aumentar significativamente.",
        ],
        "regras_nao_computadas": [
            "A replicabilidade (retorno ao vivo vs. simulado) cair abaixo de 95%.",
            "O comportamento real sair do envelope simulado.",
        ],
    }
