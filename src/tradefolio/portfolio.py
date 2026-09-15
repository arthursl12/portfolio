"""Portfolio engine (AGENTS.md épico 10).

Maior gap arquitetural do projeto até esta fatia: tudo em `tradefolio.*`
opera sobre UM `ordens`/`diario` por vez. Este módulo generaliza o
padrão já usado em `daily.pivotar_liquido_por_ativo` (por ativo dentro
de um robô) para "por robô dentro de um portfólio" -- reusando as
mesmas funções de `drawdowns`/`metrics`/`limiar` já existentes sobre a
série COMBINADA, não reimplementando nada.

Escopo desta primeira fatia (tarefas 10.1/10.2/10.3-parcial/10.4-parcial/
10.6/10.7): sincronização, métricas agregadas básicas (lucro/MDD/ES),
correlação geral (mesma variante "todos os dias" de
`report_data.calcular_pagina6`), limiar agregado e benefício da
diversificação. Deliberadamente NÃO implementadas aqui: contribuição
marginal por robô (10.5 -- mecânica, mas cara: N+1 recomputações
completas), as outras 3 variantes de correlação (10.4 -- mesma lacuna já
documentada para `calcular_pagina6`, precisam de convenções extras),
RLT/VLT/lucro mensal/custo total agregados (10.3 -- compõem-se
diretamente com `limiar.rlt_*`/`vapo.*`/`monthly.agregar_mensal` sobre a
série combinada, mas não foram montados como função própria nesta
rodada), e otimização de portfólio (10.8 -- decisão de dependência nova,
SciPy/CVXPY/Optuna).

Decisões de design (documentadas, não escondidas -- AGENTS.md §8):

- `sincronizar_portfolio` recebe um dict `{nome: diario}` já pronto --
  cada `diario` já construído com o `contratos_referencia` certo daquele
  robô (inclusive multi-ativo com proporção fixa, ver
  `daily.detectar_contratos_referencia_multi_ativo`). Não recalcula
  nada, só sincroniza. `pd.DataFrame({nome: diario["liquido"], ...})` já
  faz o alinhamento certo: pandas une os índices e preenche com NaN onde
  um robô simplesmente não tem dado -- não com 0, que já significa
  NO_TRADE dentro do range de vida daquele robô (embutido no `diario` de
  cada um). Isso distingue "robô não operou" (0) de "robô ainda não
  existia" (NaN) sem nenhuma lógica nova.
- `serie_combinada` soma com `skipna=True`: um robô que ainda não
  existia contribui 0 para o portfólio naquele dia (não contamina o
  total com NaN) -- decisão explícita.
- `multiplicadores` (opcional, tarefa 10.2) escala cada robô ANTES de
  sincronizar, cobrindo "suportar quantidades e multiplicadores" sem uma
  segunda função.
- `correlacao_portfolio` é só `largo.corr()` -- pandas já calcula
  correlação par-a-par usando só as datas em que AMBOS os robôs têm
  dado (pairwise complete observations), que já é o comportamento certo
  para robôs com históricos de tamanhos diferentes.
- `limiar_agregado_portfolio` reusa `limiar.decompor_limiar` -- a MESMA
  função do robô único, alimentada com a margem SOMADA e o drawdown da
  série COMBINADA. O PDF-fonte avisa para NÃO somar os limiares
  individuais -- aqui não se soma nada, `decompor_limiar` calcula um
  limiar genuinamente novo a partir dos dados agregados.
"""
import itertools
import math

import pandas as pd

from tradefolio import limiar as limiar_mod
from tradefolio import metrics
from tradefolio.drawdowns import curva_equity, drawdown, maximo_drawdown, time_under_water_max
from tradefolio.monte_carlo import circular_block_bootstrap, resumo_trajetorias


def sincronizar_portfolio(diarios: dict, multiplicadores: dict = None) -> pd.DataFrame:
    """`diarios`: `{nome_do_robo: diario}`, cada `diario` já construído
    (ex. `report_data.montar_dataframe_diario`) com o `contratos_referencia`
    certo daquele robô. `multiplicadores` (opcional, tarefa 10.2):
    `{nome_do_robo: fator}` -- escala o `liquido` daquele robô antes de
    sincronizar (ex. rodar um robô a 2x o tamanho de referência dentro
    do portfólio)."""
    multiplicadores = multiplicadores or {}
    return pd.DataFrame({
        nome: diario["liquido"] * multiplicadores.get(nome, 1.0)
        for nome, diario in diarios.items()
    })


def serie_combinada(largo: pd.DataFrame) -> pd.Series:
    """Soma todos os robôs por data, `skipna=True` -- um robô que ainda
    não existia (NaN) contribui 0 para o portfólio naquele dia."""
    return largo.sum(axis=1, skipna=True)


def metricas_agregadas(largo: pd.DataFrame) -> dict:
    """Lucro total, MDD, ES95, TUW, pior dia/mês e lucro mensal sobre a
    série COMBINADA (tarefa 10.3, ver docstring do módulo para o que
    ainda falta: margem/VLT/custo total). Reusa `drawdowns`/`metrics`
    diretamente, nenhuma fórmula nova.

    `lucro_mensal` é `serie_combinada.resample("ME").sum()` -- NÃO
    `monthly.agregar_mensal` (que exige `bruto`/`custo`/`n_trades`/
    `liquido_por_contrato`, colunas que não têm um significado agregado
    coerente entre robôs heterogêneos; inventar valores para elas violaria
    AGENTS.md §8). Isso dá o lucro mensal do portfólio sem forçar as
    colunas mais ricas de um único robô sobre a série combinada."""
    combinada = serie_combinada(largo)
    equity = curva_equity(combinada)
    dd = drawdown(equity)
    lucro_mensal = combinada.resample("ME").sum()
    return {
        "lucro_total": combinada.sum(),
        "mdd": maximo_drawdown(dd),
        "es_95": metrics.expected_shortfall(combinada, 0.95),
        "tuw_max": time_under_water_max(dd),
        "pior_dia_total": combinada.min(),
        "pior_mes_total": lucro_mensal.min(),
        "lucro_mensal": lucro_mensal,
    }


def restringir_janela_comum(largo: pd.DataFrame) -> pd.DataFrame:
    """Restringe a série sincronizada ao intervalo em que TODOS os robôs
    já existiam -- do início do robô mais recente até o fim do mais
    antigo, se os históricos terminam em datas diferentes (pedido de
    acompanhamento do usuário: métricas de portfólio devem, por padrão,
    considerar só o período em que todos coexistiam, não a união inteira
    -- caso contrário anos de um robô sozinho entram na mesma média que o
    período em que todos já operavam juntos).

    Diferente de `correlacao_dias_conjuntos`: aqui a janela é definida
    por EXISTÊNCIA (não-NaN em `largo`), não por terem OPERADO naquele
    dia -- um dia sem operação (0, já preenchido por
    `alignment.preencher_calendario_b3` em cada diario) dentro da janela
    comum continua incluído, só os dias antes/depois da coexistência são
    cortados. `largo.dropna()` já produz exatamente esse intervalo
    contíguo, porque `sincronizar_portfolio` só produz NaN antes do robô
    existir ou depois de acabar -- nunca no meio (dias sem operação são
    0, não NaN)."""
    comum = largo.dropna()
    if comum.empty:
        raise ValueError("Os robôs não têm nenhum período em que todos coexistiram (janela comum vazia)")
    return comum


def robustez_portfolio(
    largo: pd.DataFrame,
    tamanho_bloco: int = 20,
    n_trajetorias: int = 2000,
    horizonte: int = 252,
    seed: int = None,
    incluir_dias_sem_operacao: bool = True,
    minimum_margin: float = None,
    limiar: float = None,
) -> dict:
    """Robustez (Monte Carlo) do PORTFÓLIO (tarefas e épicos.pdf tarefa
    8.1: "Para portfólio: Todos os robôs permanecem sincronizados pela
    data"). Nenhuma fórmula nova -- reusa `monte_carlo.
    circular_block_bootstrap`/`resumo_trajetorias` diretamente, que já
    foram construídas desde o Épico 8 para aceitar um `pd.DataFrame`
    multi-coluna e manter todas as colunas na MESMA linha/data sorteada
    (ver docstring de `tradefolio.monte_carlo`) -- isso preserva a
    correlação real entre os robôs em cada bloco sorteado, em vez de
    reamostrar cada um independentemente. `resumo_trajetorias` já soma
    entre colunas por trajetória antes de calcular os percentis, então
    o resultado é diretamente o lucro/MDD/probabilidades do PORTFÓLIO
    combinado, mesma forma de `report_data.calcular_robustez` para um
    robô único.

    `largo` é preenchido com 0 antes de reamostrar (`largo.fillna(0.0)`)
    -- um robô que ainda não existia (NaN, só ocorre se `largo` vier do
    escopo "união"; o escopo "janela comum", padrão do módulo, já não
    tem NaN) não pode contribuir nada para aquele dia sorteado, mesma
    convenção de `serie_combinada`'s `skipna=True`.

    Deliberadamente NÃO incluído: cenários de deterioração (Épico 8.3 --
    `aumentar_custos`/`aplicar_slippage`/etc. precisam de `diario['bruto'
    ]`/`['custo']`/`['n_trades']`, colunas sem significado agregado
    coerente entre robôs heterogêneos, mesma razão já documentada para
    `metricas_agregadas`'s `lucro_mensal` não reusar `monthly.
    agregar_mensal`). `minimum_margin`/`limiar` são os valores do
    PORTFÓLIO (margem somada, limiar agregado de
    `limiar_agregado_portfolio`), não de um robô -- opcionais, mesmo
    padrão de `calcular_robustez`."""
    dados = largo.fillna(0.0)
    resultado_bootstrap = circular_block_bootstrap(
        dados, tamanho_bloco=tamanho_bloco, n_trajetorias=n_trajetorias,
        horizonte=horizonte, seed=seed, incluir_dias_sem_operacao=incluir_dias_sem_operacao,
    )
    resumo = resumo_trajetorias(resultado_bootstrap, minimum_margin=minimum_margin, limiar=limiar)
    resumo["seed"] = resultado_bootstrap.seed
    resumo["tamanho_bloco"] = tamanho_bloco
    resumo["n_trajetorias"] = n_trajetorias
    resumo["horizonte"] = horizonte
    return resumo


def correlacao_portfolio(largo: pd.DataFrame) -> pd.DataFrame:
    """Correlação de Pearson par-a-par entre os robôs do portfólio,
    variante "todos os dias" (tarefa 10.4, variante 1 -- lâmina ideal.pdf
    §13 "correlação diária total"). Ver `correlacao_dias_conjuntos`/
    `correlacao_piores_dias`/`correlacao_perdas`/
    `correlacao_volatilidade_alta`/`correlacao_movel` para as outras
    variantes da tarefa 10.4."""
    return largo.corr()


def sincronizar_operou(diarios: dict) -> pd.DataFrame:
    """Wide frame do `operou` (booleano) de cada robô, mesmo alinhamento
    por união de datas de `sincronizar_portfolio` -- usado por
    `correlacao_dias_conjuntos`. `NaN` onde o robô ainda não existia (via
    `reindex`, tratado como "não operou" por quem consome: um robô não
    pode ter "operado" antes de existir)."""
    return pd.DataFrame({nome: diario["operou"] for nome, diario in diarios.items()})


def correlacao_dias_conjuntos(largo: pd.DataFrame, operou: pd.DataFrame) -> pd.DataFrame:
    """Tarefa 10.4, variante 2 (lâmina ideal.pdf §13 "correlação nos dias
    em que ambos operaram") -- generalizada para N robôs: só usa datas em
    que TODOS operaram (não apenas existiam). `operou` vem de
    `sincronizar_operou`."""
    mascara = operou.reindex(largo.index).fillna(False).all(axis=1)
    return largo.loc[mascara].corr()


def correlacao_piores_dias(largo: pd.DataFrame, fracao: float = 0.20) -> pd.DataFrame:
    """Tarefa 10.4, variante 3 (lâmina ideal.pdf §13/tarefas e épicos.pdf:
    "correlação nos 20% piores dias"). Decisão de design (documentada, não
    escondida -- AGENTS.md §8): "piores dias" = piores `fracao` das datas
    pela série COMBINADA do portfólio (`serie_combinada`), não uma
    recombinação por par -- a mesma série de referência usada em todo o
    resto do módulo (`metricas_agregadas`/`limiar_agregado_portfolio`).
    `fracao` exposta como parâmetro (0.20 é o valor citado no PDF-fonte,
    não hardcoded internamente)."""
    combinada = serie_combinada(largo)
    n = max(1, math.ceil(len(combinada) * fracao))
    piores_datas = combinada.nsmallest(n).index
    return largo.loc[piores_datas].corr()


def correlacao_perdas(largo: pd.DataFrame) -> pd.DataFrame:
    """Tarefa 10.4, variante 5 ("correlação de perdas") -- correlação só
    nas datas em que a série COMBINADA teve resultado negativo (mesma
    escolha de série de referência de `correlacao_piores_dias`)."""
    combinada = serie_combinada(largo)
    return largo.loc[combinada < 0].corr()


def correlacao_volatilidade_alta(largo: pd.DataFrame, janela: int = 21, fracao: float = 0.20) -> pd.DataFrame:
    """Tarefa 10.4, variante 4 ("correlação em volatilidade alta"). Nem a
    lâmina ideal.pdf nem tarefas e épicos.pdf definem uma janela ou fração
    para "volatilidade alta" -- ambas expostas como parâmetros (AGENTS.md
    §8.1), não inventadas como constante interna. "Volatilidade" = desvio-
    padrão móvel (`janela` pregões) da série COMBINADA (mesma referência
    de `correlacao_piores_dias`); "alta" = top `fracao` das datas por esse
    valor. Default `janela=21` (~1 mês de pregões) e `fracao=0.20` (mesmo
    valor citado no PDF para "piores dias", por consistência) -- editável
    pelo chamador, nunca escondido."""
    combinada = serie_combinada(largo)
    vol_movel = combinada.rolling(janela).std().dropna()
    n = max(1, math.ceil(len(vol_movel) * fracao))
    datas_alta_vol = vol_movel.nlargest(n).index
    return largo.loc[datas_alta_vol].corr()


def correlacao_movel(largo: pd.DataFrame, janela_pregoes: int) -> pd.DataFrame:
    """Tarefa 10.4, variante 6 ("correlação móvel") -- correlação par-a-
    par recalculada dia a dia sobre uma janela deslizante de
    `janela_pregoes`, uma função genérica sobre a janela (mesmo padrão de
    `limiar.rlt_movel`), não um valor fixo. Uma coluna por par de robôs
    (`"a × b"`), indexada por data; os primeiros `janela_pregoes - 1`
    valores de cada par ficam `NaN` (janela incompleta), não um número
    inventado."""
    nomes = list(largo.columns)
    pares = {
        f"{a} × {b}": largo[a].rolling(janela_pregoes).corr(largo[b])
        for i, a in enumerate(nomes)
        for b in nomes[i + 1:]
    }
    return pd.DataFrame(pares)


def limiar_agregado_portfolio(
    largo: pd.DataFrame,
    minimum_margins: dict,
    percentil_cauda: int = 95,
    fracao_reserva_operacional: float = 0.0,
    increment: float = None,
) -> dict:
    """Limiar do PORTFÓLIO (tarefa 10.6) -- reusa `limiar.decompor_limiar`
    (a mesma função de um robô único) alimentada pela margem mínima
    SOMADA e pelo drawdown da série COMBINADA. `minimum_margins`:
    `{nome_do_robo: margem}`."""
    combinada = serie_combinada(largo)
    equity = curva_equity(combinada)
    dd = drawdown(equity)
    meses_historico = (combinada.index.max() - combinada.index.min()).days / 30.44
    margem_total = sum(minimum_margins.values())
    return limiar_mod.decompor_limiar(
        margem_total, dd, meses_historico, percentil_cauda, fracao_reserva_operacional, increment,
    )


def rlt_e_risco_portfolio(largo: pd.DataFrame, limiar: float) -> dict:
    """RLT e risco normalizado pelo limiar, para o PORTFÓLIO (extensão da
    tarefa 10.3, mesma forma de `report_data.calcular_pagina4` para um
    robô único, mas sobre a série COMBINADA). `limiar` é o limiar agregado
    já decidido (ex. o `limiar_recomendado`/`limiar_bruto` de
    `limiar_agregado_portfolio`) -- nunca recalculado aqui. Reusa
    `metricas_agregadas` para MDD/pior dia/pior mês/lucro mensal (nenhuma
    duplicação de fórmula) e `limiar.rlt_*`/`limiar.normalizar_por_limiar`
    (genéricas, já existentes) para o resto."""
    agregadas = metricas_agregadas(largo)
    combinada = serie_combinada(largo)
    lucro_mensal = agregadas["lucro_mensal"]
    rlt_mensal_serie = limiar_mod.rlt_mensal(lucro_mensal, limiar)

    return {
        "rlt_acumulado": limiar_mod.rlt_acumulado(combinada.sum(), limiar),
        "rlt_anualizado": limiar_mod.rlt_anualizado(combinada, limiar),
        "rlt_mensal_medio": rlt_mensal_serie.mean(),
        "rlt_mensal_mediano": rlt_mensal_serie.median(),
        "rlt_movel_3": limiar_mod.rlt_movel(lucro_mensal, limiar, 3).iloc[-1],
        "rlt_movel_6": limiar_mod.rlt_movel(lucro_mensal, limiar, 6).iloc[-1],
        "rlt_movel_12": limiar_mod.rlt_movel(lucro_mensal, limiar, 12).iloc[-1],
        "mdd_sobre_limiar": limiar_mod.normalizar_por_limiar(agregadas["mdd"], limiar),
        "es95_sobre_limiar": limiar_mod.normalizar_por_limiar(agregadas["es_95"], limiar),
        "pior_dia_sobre_limiar": limiar_mod.normalizar_por_limiar(agregadas["pior_dia_total"], limiar),
        "pior_mes_sobre_limiar": limiar_mod.normalizar_por_limiar(agregadas["pior_mes_total"], limiar),
    }


def beneficio_diversificacao(soma_limiares_individuais: float, limiar_agregado: float) -> dict:
    """Tarefa 10.7 -- em reais e em percentual da soma individual."""
    beneficio_rs = soma_limiares_individuais - limiar_agregado
    return {
        "beneficio_rs": beneficio_rs,
        "beneficio_pct": beneficio_rs / soma_limiares_individuais if soma_limiares_individuais else float("nan"),
    }


def contribuicao_marginal(
    diarios: dict,
    minimum_margins: dict,
    percentil_cauda: int = 95,
    fracao_reserva_operacional: float = 0.0,
    increment: float = None,
    usar_janela_comum: bool = True,
) -> dict:
    """Tarefa 10.5 (lâmina ideal.pdf §13 "Valor marginal do robô"): para
    cada robô, recomputa lucro/MDD/ES95/limiar agregado COM e SEM aquele
    robô (o portfólio dos N-1 restantes), e retorna a diferença (COM -
    SEM). Mecânico uma vez que 10.1/10.3/10.6 já existem -- N+1
    recomputações completas do portfólio (uma "com todos", uma por robô
    "sem ele"), caro para N grande mas barato para o número de robôs
    típico de um portfólio real (medir antes de otimizar, por isso
    nenhuma otimização foi feita aqui).

    `usar_janela_comum=True` (padrão -- pedido de acompanhamento do
    usuário): cada comparação ("com todos", "sem robô X") é restringida
    à SUA PRÓPRIA janela comum via `restringir_janela_comum`, não à união
    inteira nem à janela comum do portfólio completo -- "sem resgat", por
    exemplo, usa o período em que os robôs RESTANTES coexistiam entre si,
    que pode ser maior que a janela comum com resgat incluído. Passe
    `False` para preservar o comportamento antigo (união com skipna).

    VLT deliberadamente NÃO incluído (mesma lacuna documentada em
    `rlt_e_risco_portfolio`/TASKS.md: precisaria de uma política de vapo
    escolhida para o portfólio, uma convenção nova não pedida ainda).

    Exige 2+ robôs -- "contribuição marginal" de um portfólio de 1 robô
    não é um conceito coerente (não há "portfólio sem ele" para
    comparar)."""
    if len(diarios) < 2:
        raise ValueError("contribuicao_marginal exige ao menos 2 robôs no portfólio")

    def _metricas(subset_diarios: dict, subset_margens: dict) -> tuple[dict, float]:
        largo = sincronizar_portfolio(subset_diarios)
        if usar_janela_comum:
            largo = restringir_janela_comum(largo)
        agregadas = metricas_agregadas(largo)
        limiar = limiar_agregado_portfolio(
            largo, subset_margens, percentil_cauda, fracao_reserva_operacional, increment,
        )
        limiar_ativo = limiar.get("limiar_recomendado", limiar["limiar_bruto"])
        return agregadas, limiar_ativo

    agregadas_completo, limiar_completo = _metricas(diarios, minimum_margins)

    resultado = {}
    for nome in diarios:
        outros_diarios = {k: v for k, v in diarios.items() if k != nome}
        outros_margens = {k: v for k, v in minimum_margins.items() if k != nome}
        agregadas_sem, limiar_sem = _metricas(outros_diarios, outros_margens)

        resultado[nome] = {
            "lucro_com": agregadas_completo["lucro_total"],
            "lucro_sem": agregadas_sem["lucro_total"],
            "diferenca_lucro": agregadas_completo["lucro_total"] - agregadas_sem["lucro_total"],
            "mdd_com": agregadas_completo["mdd"],
            "mdd_sem": agregadas_sem["mdd"],
            "diferenca_mdd": agregadas_completo["mdd"] - agregadas_sem["mdd"],
            "es95_com": agregadas_completo["es_95"],
            "es95_sem": agregadas_sem["es_95"],
            "diferenca_es95": agregadas_completo["es_95"] - agregadas_sem["es_95"],
            "limiar_com": limiar_completo,
            "limiar_sem": limiar_sem,
            "diferenca_limiar": limiar_completo - limiar_sem,
        }
    return resultado


_OBJETIVOS_OTIMIZACAO = (
    "maximizar_rlt", "minimizar_mdd_sobre_limiar", "maximizar_lucro_com_limite_mdd",
)
_LIMITE_COMBINACOES_OTIMIZACAO = 20000


def buscar_combinacoes_portfolio(
    diarios_referencia: dict,
    margens_por_contrato: dict,
    candidatos_contratos: dict,
    percentil_cauda: int = 95,
    fracao_reserva_operacional: float = 0.0,
    increment: float = None,
    usar_janela_comum: bool = True,
) -> list[dict]:
    """Tarefa 10.8, a parte CARA da busca discreta (NÃO otimização
    contínua, o PDF-fonte pede isso explicitamente): calcula TODAS as
    métricas relevantes (lucro, MDD, ES95, limiar, RLT acumulado, MDD/
    limiar) para CADA combinação candidata de número de contratos por
    robô, sem aplicar nenhum objetivo, filtro ou ordenação -- isso é
    responsabilidade de `selecionar_melhores_combinacoes`, deliberadamente
    separada (pedido de acompanhamento do usuário: trocar de objetivo na
    UI não deveria recalcular a busca inteira, só reordenar/filtrar a
    tabela já pronta -- a parte lenta roda uma vez).

    `0` é um candidato válido em `candidatos_contratos` -- exclui aquele
    robô inteiramente do portfólio para aquela combinação (pedido
    explícito do usuário: "tirar um robô também é uma possibilidade";
    não incluído automaticamente -- o chamador decide se 0 entra na
    lista de candidatos de cada robô).

    `diarios_referencia`: {nome: diario} na escala de referência
    (`liquido_por_contrato`, invariante ao número de contratos simulado
    -- mesma convenção linear de `daily.escalar_por_contratos`).
    `margens_por_contrato`: {nome: margem por contrato} -- margem de cada
    candidato = margem_por_contrato × n_contratos (mesma convenção do
    modo Portfólio nas UIs). `candidatos_contratos`: {nome: [n_contratos
    a testar]}.

    Custo mensal NÃO entra nesta busca (simplificação documentada, não
    escondida): tornaria cada combinação dependente de uma tabela de
    faixas por robô, e o objetivo desta primeira fatia é o dimensionamento
    puro. Quem quiser o efeito do custo mensal aplica a tabela sobre a
    alocação vencedora depois, fora desta função.

    `usar_janela_comum=True` (padrão -- pedido de acompanhamento do
    usuário): cada combinação testada é restringida à SUA PRÓPRIA janela
    comum (`restringir_janela_comum`) antes de ser pontuada -- diferentes
    combinações têm janelas comuns diferentes, já que excluir um robô
    (candidato 0) muda quem precisa coexistir. Combinações cuja janela
    comum ficaria vazia são puladas. Passe `False` para preservar o
    comportamento antigo (união com skipna).

    Levanta `ValueError` se o total de combinações exceder
    `_LIMITE_COMBINACOES_OTIMIZACAO` (busca discreta não escala para
    muitas combinações -- reduza os candidatos por robô)."""
    nomes = list(diarios_referencia.keys())
    listas_candidatos = [candidatos_contratos[nome] for nome in nomes]

    n_total = math.prod(len(lista) for lista in listas_candidatos)
    if n_total > _LIMITE_COMBINACOES_OTIMIZACAO:
        raise ValueError(
            f"{n_total} combinações excede o limite de {_LIMITE_COMBINACOES_OTIMIZACAO} -- "
            "reduza o número de candidatos por robô (ou o passo entre eles)"
        )

    resultados = []
    for combinacao in itertools.product(*listas_candidatos):
        alocacao = dict(zip(nomes, combinacao))

        diarios_ativos, margens_ativas = {}, {}
        for nome, n_contratos in alocacao.items():
            if n_contratos == 0:
                continue
            diario = diarios_referencia[nome]
            diario_simulado = diario.copy()
            diario_simulado["liquido"] = diario["liquido_por_contrato"] * n_contratos
            diarios_ativos[nome] = diario_simulado
            margens_ativas[nome] = margens_por_contrato[nome] * n_contratos

        if not diarios_ativos:
            continue

        largo = sincronizar_portfolio(diarios_ativos)
        if usar_janela_comum:
            try:
                largo = restringir_janela_comum(largo)
            except ValueError:
                continue
        agregadas = metricas_agregadas(largo)

        limiar = limiar_agregado_portfolio(
            largo, margens_ativas, percentil_cauda, fracao_reserva_operacional, increment,
        )
        limiar_ativo = limiar.get("limiar_recomendado", limiar["limiar_bruto"])
        rlt = rlt_e_risco_portfolio(largo, limiar=limiar_ativo)

        resultados.append({
            "alocacao": alocacao,
            "lucro_total": agregadas["lucro_total"],
            "mdd": agregadas["mdd"],
            "es_95": agregadas["es_95"],
            "limiar_ativo": limiar_ativo,
            "rlt_acumulado": rlt["rlt_acumulado"],
            "mdd_sobre_limiar": rlt["mdd_sobre_limiar"],
        })

    return resultados


def selecionar_melhores_combinacoes(
    resultados: list[dict],
    objetivo: str,
    limite_mdd: float = None,
    top_n: int = 10,
) -> dict:
    """Tarefa 10.8, a parte BARATA da busca discreta -- ordena/filtra
    combinações já calculadas por `buscar_combinacoes_portfolio` segundo
    `objetivo`. NÃO recalcula nenhuma métrica, só reordena/filtra a lista
    já pronta -- isso é o que permite trocar de objetivo (ex. na UI) sem
    refazer a busca inteira.

    Objetivos suportados (dos 6 do PDF-fonte, só os que NÃO dependem de
    uma política de vapo para o portfólio -- decisão ainda não tomada,
    ver `rlt_e_risco_portfolio`):
    - "maximizar_rlt": maior RLT acumulado da combinação.
    - "minimizar_mdd_sobre_limiar": menor |MDD/limiar| (mais seguro,
      mais perto de zero -- NÃO o valor mais negativo, que seria pior).
    - "maximizar_lucro_com_limite_mdd": maior lucro total entre as
      combinações cujo MDD não é pior que `limite_mdd` (obrigatório para
      este objetivo -- nunca inventado, AGENTS.md §8).
    Deliberadamente NÃO implementados: "maximizar VLT" e "maximizar vapo
    com limite de capital" (precisam de uma política de vapo escolhida
    PARA O PORTFÓLIO, não pedida ainda) e "minimizar pior cenário
    deteriorado" (precisaria rodar Monte Carlo + deterioração para cada
    combinação testada -- caro e uma decisão de escopo própria).

    `top_n`: retorna as `top_n` melhores combinações, não só a primeira
    -- o PDF-fonte pede explicitamente para NUNCA reportar só o melhor
    resultado da amostra (risco de sobreajuste de busca com muitas
    tentativas). `n_combinacoes_testadas` no resultado deixa esse risco
    visível para quem consome (quanto mais combinações, maior a chance
    do "melhor" ser sorte de amostra, não edge real) -- para
    "maximizar_lucro_com_limite_mdd" já reflete só as combinações que
    satisfazem `limite_mdd`, não o total bruto testado por
    `buscar_combinacoes_portfolio`.

    Levanta `ValueError` se `objetivo` for desconhecido, se
    `limite_mdd` faltar para "maximizar_lucro_com_limite_mdd", ou se
    nenhuma combinação satisfizer as restrições do objetivo escolhido."""
    if objetivo not in _OBJETIVOS_OTIMIZACAO:
        raise ValueError(f"objetivo deve ser um de {_OBJETIVOS_OTIMIZACAO}, recebido {objetivo!r}")
    if objetivo == "maximizar_lucro_com_limite_mdd" and limite_mdd is None:
        raise ValueError("limite_mdd é obrigatório para o objetivo 'maximizar_lucro_com_limite_mdd'")

    if objetivo == "maximizar_lucro_com_limite_mdd":
        validos = [r for r in resultados if r["mdd"] >= limite_mdd]
        chave = lambda r: r["lucro_total"]
    elif objetivo == "maximizar_rlt":
        validos = resultados
        chave = lambda r: r["rlt_acumulado"]
    else:  # minimizar_mdd_sobre_limiar
        validos = resultados
        chave = lambda r: -abs(r["mdd_sobre_limiar"])

    if not validos:
        raise ValueError(
            "Nenhuma combinação testada satisfaz as restrições do objetivo escolhido "
            f"({objetivo}, limite_mdd={limite_mdd})"
        )

    ordenados = sorted(validos, key=chave, reverse=True)
    melhores = [dict(r, score=chave(r)) for r in ordenados[:top_n]]
    return {
        "objetivo": objetivo,
        "n_combinacoes_testadas": len(validos),
        "melhores": melhores,
    }


def otimizar_portfolio(
    diarios_referencia: dict,
    margens_por_contrato: dict,
    candidatos_contratos: dict,
    objetivo: str,
    limite_mdd: float = None,
    percentil_cauda: int = 95,
    fracao_reserva_operacional: float = 0.0,
    increment: float = None,
    top_n: int = 10,
    usar_janela_comum: bool = True,
) -> dict:
    """Atalho de conveniência (tarefa 10.8) -- roda
    `buscar_combinacoes_portfolio` e `selecionar_melhores_combinacoes`
    numa chamada só, mesmo comportamento de antes desta função ter sido
    dividida em duas. Quem for trocar de objetivo repetidamente (ex. um
    seletor na UI) deve chamar `buscar_combinacoes_portfolio` uma vez e
    `selecionar_melhores_combinacoes` a cada troca, para não recalcular a
    busca inteira a cada clique."""
    resultados = buscar_combinacoes_portfolio(
        diarios_referencia, margens_por_contrato, candidatos_contratos,
        percentil_cauda, fracao_reserva_operacional, increment, usar_janela_comum,
    )
    return selecionar_melhores_combinacoes(resultados, objetivo, limite_mdd, top_n)


def fronteira_pareto(resultados: list, eixo_retorno: str, eixo_risco: str) -> list:
    """Fronteira de Pareto DISCRETA (pedido de acompanhamento do usuário,
    fora dos épicos do PDF-fonte) sobre combinações já calculadas por
    `buscar_combinacoes_portfolio` -- nenhuma busca nova, só um
    reprocessamento barato do que já existe (mesma filosofia de
    `selecionar_melhores_combinacoes`).

    Markowitz (fronteira eficiente contínua, variância como medida de
    risco) foi considerado e descartado -- discutido com o usuário: os
    contratos deste domínio são discretos (uma alocação contínua
    exigiria arredondar depois, o que pode violar exatamente a margem/
    limiar que a otimização deveria respeitar), e o projeto inteiro já
    usa MDD/ES/limiar como vocabulário de risco, não variância/Sharpe --
    introduzir Markowitz seria bifurcar a filosofia de risco, não
    estendê-la. Uma fronteira de Pareto discreta não tem esse problema:
    funciona com QUALQUER par de campos já presentes nos resultados
    (`lucro_total`, `mdd`, `es_95`, `rlt_acumulado`, `mdd_sobre_limiar`),
    sem nenhuma convenção nova.

    Convenção: "maior é melhor" nos DOIS eixos. Os campos de risco já
    existentes (`mdd`/`es_95`/`mdd_sobre_limiar`) já são negativos nesta
    base de código -- "maior" = "menos negativo" = mais seguro, então
    passar esses campos diretamente já funciona, sem inverter sinal.

    Uma combinação está na fronteira quando NENHUMA outra combinação é
    simultaneamente igual-ou-melhor nos dois eixos E estritamente melhor
    em pelo menos um (dominância de Pareto padrão). Algoritmo O(n log n)
    (skyline: ordena por `eixo_retorno` decrescente, varre mantendo o
    melhor `eixo_risco` já visto) em vez de comparação par-a-par O(n²) --
    relevante porque a busca pode ter até `_LIMITE_COMBINACOES_OTIMIZACAO`
    combinações. Combinações com valores IDÊNTICOS nos dois eixos contam
    como uma só (a primeira encontrada representa as demais -- duplicatas
    exatas não são mais "não-dominadas" entre si do que uma cópia de si
    mesma, e listar todas adicionaria ruído sem informação nova)."""
    if not resultados:
        return []
    ordenados = sorted(resultados, key=lambda r: (r[eixo_retorno], r[eixo_risco]), reverse=True)
    fronteira = []
    melhor_risco_ate_agora = -math.inf
    for r in ordenados:
        if r[eixo_risco] > melhor_risco_ate_agora:
            fronteira.append(r)
            melhor_risco_ate_agora = r[eixo_risco]
    return fronteira
