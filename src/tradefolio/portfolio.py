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
from tradefolio.drawdowns import (
    calcular_episodios_drawdown,
    curva_equity,
    drawdown,
    maximo_drawdown,
    time_under_water_max,
)
from tradefolio.monte_carlo import (
    aplicar_choque,
    circular_block_bootstrap,
    embaralhamento_dias,
    resumo_trajetorias,
)


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


def robustez_dos_finalistas(
    diarios_referencia: dict,
    margens_por_contrato: dict,
    finalistas: list,
    esquema: str = "bloco",
    tamanho_bloco: int = 20,
    n_trajetorias: int = 2000,
    horizonte: int = 252,
    seed: int = None,
    incluir_dias_sem_operacao: bool = True,
    usar_janela_comum: bool = True,
    choques: list = None,
) -> list:
    """Backlog de `prompts/otimizacao.pdf` §10 ("o Monte Carlo entra
    DEPOIS da triagem, não para rodar profundamente em todas as 6 mil
    combinações"), fora dos épicos do PDF-fonte. `finalistas`: lista
    pequena de resultados já escolhidos (tipicamente `funil_selecao_
    portfolio(...)['camada4_simplicidade']`, mas qualquer `list[dict]`
    com uma chave `"alocacao"` serve -- ex. o `top_n` de `selecionar_
    melhores_combinacoes`). NÃO recalcula nada da busca -- só sincroniza
    cada alocação (`_sincronizar_alocacao`, já existente) e roda a
    máquina de bootstrap já testada.

    Distinta de `robustez_portfolio` (que continua intocada, servindo o
    uso manual já existente na UI de um `largo` só): esta função expõe
    `esquema`/`choques`, que `robustez_portfolio` não tem --
    `esquema="bloco"` (padrão) usa `circular_block_bootstrap` (esquema B
    já existente); `esquema="embaralhamento"` usa `embaralhamento_dias`
    (esquema A) -- nesse caso `horizonte` é IGNORADO (embaralhamento não
    tem esse conceito, a trajetória é sempre do tamanho da amostra,
    documentado em `embaralhamento_dias`). `choques`: lista opcional de
    tipos de `aplicar_choque` (esquema C parcial -- `"pior_dia_repetido"`/
    `"perda_simultanea"`) aplicados em sequência sobre a simulação base.

    `minimum_margin`/`limiar` de cada finalista vêm do PRÓPRIO resultado
    (margem somada da alocação sincronizada, `limiar_ativo` já calculado
    pela busca) -- nunca recalculados aqui. Finalistas degenerados (0
    contratos em todos os robôs) ou sem janela comum são pulados
    silenciosamente, mesma convenção de `buscar_combinacoes_portfolio`.

    Retorna uma lista NA MESMA ORDEM de `finalistas` (menos os pulados),
    cada entrada `{"alocacao": ..., **resumo_de_robustez}` -- `resumo`
    ganha `"esquema"`/`"choques_aplicados"` além dos campos já expostos
    por `resumo_trajetorias` (percentis, CDaR, probabilidade de
    recuperação, etc.)."""
    if esquema not in ("bloco", "embaralhamento"):
        raise ValueError(f"esquema deve ser 'bloco' ou 'embaralhamento', recebido {esquema!r}")
    choques = choques or []

    resultados = []
    for finalista in finalistas:
        alocacao = finalista["alocacao"]
        largo, margens_ativas = _sincronizar_alocacao(
            alocacao, diarios_referencia, margens_por_contrato, usar_janela_comum,
        )
        if largo is None:
            continue
        dados = largo.fillna(0.0)

        if esquema == "bloco":
            base = circular_block_bootstrap(
                dados, tamanho_bloco=tamanho_bloco, n_trajetorias=n_trajetorias, horizonte=horizonte,
                seed=seed, incluir_dias_sem_operacao=incluir_dias_sem_operacao,
            )
        else:
            base = embaralhamento_dias(
                dados, n_trajetorias=n_trajetorias, seed=seed,
                incluir_dias_sem_operacao=incluir_dias_sem_operacao,
            )

        resultado_bootstrap = base
        for tipo_choque in choques:
            resultado_bootstrap = aplicar_choque(resultado_bootstrap, dados, tipo=tipo_choque, seed=seed)

        resumo = resumo_trajetorias(
            resultado_bootstrap, minimum_margin=sum(margens_ativas.values()),
            limiar=finalista.get("limiar_ativo"),
        )
        resumo["seed"] = resultado_bootstrap.seed
        resumo["esquema"] = esquema
        resumo["choques_aplicados"] = list(choques)
        resultados.append({"alocacao": alocacao, **resumo})
    return resultados


def correlacao_portfolio(largo: pd.DataFrame) -> pd.DataFrame:
    """Correlação de Pearson par-a-par entre os robôs do portfólio,
    variante "todos os dias" (tarefa 10.4, variante 1 -- lâmina ideal.pdf
    §13 "correlação diária total"). Ver `correlacao_dias_conjuntos`/
    `correlacao_piores_dias`/`correlacao_perdas`/
    `correlacao_volatilidade_alta`/`correlacao_movel` para as outras
    variantes da tarefa 10.4."""
    return largo.corr()


def clusters_de_risco(largo: pd.DataFrame, limiar_correlacao: float = 0.5) -> list[list[str]]:
    """Backlog de `prompts/otimizacao.pdf` §4 ("agrupe EAs que
    representam o mesmo risco"). O documento não prescreve um algoritmo
    -- método CONFIRMADO com o usuário antes de implementar (AGENTS.md
    §24, para não inventar uma convenção de clustering como se fosse do
    domínio): grafo de limiar + componentes conexos, sobre
    `correlacao_portfolio` (variante "todos os dias", a mesma já usada
    como padrão no resto do módulo). Dois robôs compartilham um cluster
    sse a correlação entre eles é `>= limiar_correlacao`; clusters são os
    componentes conexos do grafo resultante -- robôs sem nenhuma aresta
    ficam em clusters de 1 (equivalente ao "cluster independente" do
    exemplo do documento-fonte).

    Sem dependência nova (AGENTS.md §18) -- `scipy`/`sklearn` seriam
    overkill para o número típico de robôs de um portfólio aqui (2-10);
    componentes conexos com union-find é suficiente e não pede nada além
    de `pandas`, já usado.

    Correlação NEGATIVA nunca agrupa, mesmo forte em magnitude --
    correlação negativa é diversificação (o oposto de "mesmo risco"), só
    correlação POSITIVA acima do limiar indica redundância. Por isso o
    filtro é `corr >= limiar_correlacao` diretamente (não
    `abs(corr) >= limiar_correlacao`).

    Retorna uma lista de clusters (cada um uma lista de nomes), ordenada
    por tamanho decrescente e depois alfabeticamente dentro de cada
    cluster e entre clusters do mesmo tamanho -- determinístico, não
    depende da ordem de iteração de `largo.columns`."""
    corr = correlacao_portfolio(largo)
    nomes = list(corr.columns)

    pai = {nome: nome for nome in nomes}

    def _encontrar(nome: str) -> str:
        raiz = nome
        while pai[raiz] != raiz:
            raiz = pai[raiz]
        while pai[nome] != raiz:
            pai[nome], nome = raiz, pai[nome]
        return raiz

    def _unir(a: str, b: str) -> None:
        raiz_a, raiz_b = _encontrar(a), _encontrar(b)
        if raiz_a != raiz_b:
            pai[raiz_a] = raiz_b

    for i, a in enumerate(nomes):
        for b in nomes[i + 1:]:
            if corr.loc[a, b] >= limiar_correlacao:
                _unir(a, b)

    grupos: dict[str, list[str]] = {}
    for nome in nomes:
        grupos.setdefault(_encontrar(nome), []).append(nome)

    clusters = [sorted(membros) for membros in grupos.values()]
    clusters.sort(key=lambda c: (-len(c), c))
    return clusters


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


def contribuicao_risco_por_robo(
    diarios: dict,
    percentil_cauda: int = 95,
    usar_janela_comum: bool = True,
) -> dict:
    """Backlog de `prompts/otimizacao.pdf` (fora dos épicos do PDF-fonte):
    decomposição de risco DENTRO de uma carteira já escolhida -- "quem
    causou o quê" -- distinta de `contribuicao_marginal` (que compara COM
    vs. SEM o robô, N+1 recomputações completas). Aqui não há
    recomputação: é uma decomposição ANALÍTICA de uma única carteira já
    fixada, em três lentes mantidas SEPARADAS (o documento-fonte é
    explícito: "não some imediatamente os três em uma nota arbitrária"):

    1. `contribuicao_volatilidade`/`participacao_volatilidade_pct` --
       alocação de Euler: `Cov(robô, portfólio) / vol(portfólio)`, que
       soma exatamente à `volatilidade_portfolio` (identidade de Euler
       para uma função homogênea de grau 1 como o desvio padrão de uma
       soma linear). Decisão CONFIRMADA com o usuário: isto reabre a
       convenção de variância/covariância que a docstring de
       `fronteira_pareto` rejeitou -- mas só para ESCOLHER contratos
       discretos (Markowitz não serve para a busca em si, que continua
       usando MDD/ES/limiar). Aqui é só uma decomposição analítica de uma
       carteira já fixada -- não influencia nenhuma busca, não
       reintroduz variância como critério de otimização.
    2. `contribuicao_es`/`participacao_es_pct` -- média do resultado de
       cada robô nos MESMOS dias que definem o `es_referencia`
       (`ES{percentil_cauda}`) do portfólio (mesmo corte de
       `metrics.var_historico` usado por `metrics.expected_shortfall`).
       Soma exatamente a `es_referencia`.
    3. `contribuicao_drawdown`/`participacao_drawdown_pct`/
       `frequencia_lidera_perda_drawdown` -- decisão CONFIRMADA com o
       usuário: usa APENAS o PIOR episódio histórico de drawdown do
       portfólio (`episodio_drawdown_referencia`, o mesmo que já define
       o MDD reportado por `metricas_agregadas`), não uma média entre
       todos os episódios -- garante que as participações somem
       exatamente ao MDD já mostrado em outros lugares da UI, e evita
       inventar um esquema de ponderação entre episódios de profundidade
       diferente (mais episódios/ponderação é backlog, não decidido).
       A janela do episódio é do primeiro dia submerso (dia seguinte ao
       pico) até o dia do fundo, INCLUSIVE -- não até a recuperação --
       porque é exatamente essa janela cuja soma bate com
       `profundidade_rs` (`equity_fundo - equity_pico`).
       `frequencia_lidera_perda_drawdown`: fração dos dias dessa janela
       em que aquele robô teve o PIOR resultado do dia entre os robôs do
       portfólio (empate: `DataFrame.idxmin` resolve pela ordem das
       colunas, primeira ocorrência -- resultado determinístico, não
       "crédito compartilhado"). Soma 1.0 entre os robôs.

    `usar_janela_comum=True` (padrão, mesmo espírito de
    `contribuicao_marginal`/`buscar_combinacoes_portfolio`): restringe
    `largo` à janela em que todos os robôs coexistiam antes de qualquer
    cálculo. Com `False` (união), `largo.fillna(0.0)` evita que NaN (robô
    ainda não existia) vaze para covariância/ES/drawdown -- mesma
    convenção de `robustez_portfolio` (um robô inexistente contribui 0,
    nunca NaN).

    Exige 2+ robôs -- "contribuição de risco" de um portfólio de 1 robô
    não é um conceito coerente (não há o que decompor)."""
    if len(diarios) < 2:
        raise ValueError("contribuicao_risco_por_robo exige ao menos 2 robôs no portfólio")

    nomes = list(diarios.keys())
    largo = sincronizar_portfolio(diarios)
    if usar_janela_comum:
        largo = restringir_janela_comum(largo)
    largo = largo.fillna(0.0)
    combinada = serie_combinada(largo)

    por_robo = {nome: {} for nome in nomes}

    # 1. Volatilidade (alocação de Euler via covariância).
    volatilidade_portfolio = combinada.std()
    for nome in nomes:
        contrib = largo[nome].cov(combinada) / volatilidade_portfolio
        por_robo[nome]["contribuicao_volatilidade"] = contrib
        por_robo[nome]["participacao_volatilidade_pct"] = contrib / volatilidade_portfolio * 100

    # 2. Expected Shortfall.
    confianca = percentil_cauda / 100
    limite_es = metrics.var_historico(combinada, confianca)
    dias_cauda = combinada[combinada <= limite_es].index
    es_referencia = metrics.expected_shortfall(combinada, confianca)
    for nome in nomes:
        contrib = largo.loc[dias_cauda, nome].mean()
        por_robo[nome]["contribuicao_es"] = contrib
        por_robo[nome]["participacao_es_pct"] = contrib / es_referencia * 100

    # 3. Drawdown -- pior episódio histórico (mesmo que define o MDD).
    equity = curva_equity(combinada)
    episodios = calcular_episodios_drawdown(equity)
    if episodios.empty:
        raise ValueError(
            "Nenhum episódio de drawdown encontrado na série combinada -- "
            "portfólio nunca ficou abaixo do pico anterior"
        )
    pior = episodios.loc[episodios["profundidade_rs"].idxmin()]
    pos_pico = equity.index.get_loc(pior["inicio_pico"])
    primeiro_dia_submerso = equity.index[pos_pico + 1]
    janela_episodio = largo.loc[primeiro_dia_submerso:pior["data_fundo"]]
    lideres_do_dia = janela_episodio.idxmin(axis=1)
    contagem_lideres = lideres_do_dia.value_counts()
    for nome in nomes:
        contrib = janela_episodio[nome].sum()
        por_robo[nome]["contribuicao_drawdown"] = contrib
        por_robo[nome]["participacao_drawdown_pct"] = contrib / pior["profundidade_rs"] * 100
        por_robo[nome]["frequencia_lidera_perda_drawdown"] = (
            contagem_lideres.get(nome, 0) / len(janela_episodio)
        )

    return {
        "por_robo": por_robo,
        "volatilidade_portfolio": volatilidade_portfolio,
        "es_referencia": es_referencia,
        "percentil_cauda": percentil_cauda,
        "n_dias_cauda_es": len(dias_cauda),
        "episodio_drawdown_referencia": {
            "inicio_pico": pior["inicio_pico"],
            "data_fundo": pior["data_fundo"],
            "data_recuperacao": pior["data_recuperacao"],
            "profundidade_rs": pior["profundidade_rs"],
            "pregoes_ate_fundo": pior["pregoes_ate_fundo"],
        },
    }


def scores_individuais_portfolio(
    diarios: dict,
    percentil_cauda: int = 95,
    fracao_melhores_dias: float = 0.05,
    fracao_piores_dias: float = 0.20,
    usar_janela_comum: bool = True,
) -> dict:
    """Backlog de `prompts/otimizacao.pdf` §3 ("avalie a qualidade
    individual, mas não ranqueie somente por ela"). O documento pede 3
    scores por robô mantidos SEPARADOS -- "não some imediatamente os três
    em uma nota arbitrária". **Decisão confirmada com o usuário**
    (AGENTS.md §24): em vez de reduzir cada eixo a UM número (o que
    exigiria inventar uma fórmula de normalização/peso que ninguém
    pediu), esta função devolve as métricas BRUTAS de cada eixo,
    agrupadas em 3 seções por robô -- nenhuma agregação nova, só reuso
    do que já existe, organizado pelo eixo que o documento atribui a
    cada métrica:

    - `"retorno"`: `lucro_liquido` (soma), `expectativa_diaria`
      (`metrics.expectancia`), `desvio_padrao_diario`
      (`metrics.desvio_padrao` -- proxy de "estabilidade dos retornos",
      MENOR é mais estável), `resultado_sem_melhores_dias` (soma
      excluindo os `fracao_melhores_dias` melhores dias -- mesmo
      mecanismo de corte por quantil de `metrics.var_historico`, só no
      lado superior da série).
    - `"risco"`: `mdd`, `es` (`metrics.expected_shortfall`), `pior_dia`,
      `duracao_drawdown_max` (`drawdowns.time_under_water_max`),
      `maior_sequencia_perdas` (`metrics.maior_sequencia`).
    - `"diversificacao"`: `correlacao_media` (`correlacao_portfolio`),
      `correlacao_dias_negativos` (`correlacao_perdas`),
      `coincidencia_piores_dias` (`correlacao_piores_dias`),
      `contribuicao_drawdown_portfolio_pct` (reusa
      `contribuicao_risco_por_robo`, não recalcula), e
      `retorno_quando_outros_perdem` (média do resultado do robô nos
      dias em que a soma dos OUTROS robôs foi negativa -- `NaN` se isso
      nunca ocorreu, nunca inventado como 0).

    Todas as métricas de cada eixo operam sobre a série `liquido` de
    cada robô DENTRO da janela usada (`usar_janela_comum=True`, padrão,
    mesmo espírito do resto do módulo). Exige 2+ robôs -- as métricas de
    diversificação não são um conceito coerente para um portfólio de 1
    robô (não há "os outros" para comparar)."""
    if len(diarios) < 2:
        raise ValueError("scores_individuais_portfolio exige ao menos 2 robôs no portfólio")

    largo = sincronizar_portfolio(diarios)
    if usar_janela_comum:
        largo = restringir_janela_comum(largo)
    nomes = list(largo.columns)

    corr = correlacao_portfolio(largo)
    corr_perdas = correlacao_perdas(largo)
    corr_piores = correlacao_piores_dias(largo, fracao=fracao_piores_dias)
    contribuicoes = contribuicao_risco_por_robo(
        diarios, percentil_cauda=percentil_cauda, usar_janela_comum=usar_janela_comum,
    )["por_robo"]

    resultado = {}
    for nome in nomes:
        serie = largo[nome]
        dd = drawdown(curva_equity(serie))
        limite_superior = serie.quantile(1 - fracao_melhores_dias)

        outros = largo.drop(columns=[nome]).sum(axis=1)
        dias_outros_perdem = outros[outros < 0].index

        resultado[nome] = {
            "retorno": {
                "lucro_liquido": serie.sum(),
                "expectativa_diaria": metrics.expectancia(serie),
                "desvio_padrao_diario": metrics.desvio_padrao(serie),
                "resultado_sem_melhores_dias": serie[serie < limite_superior].sum(),
            },
            "risco": {
                "mdd": maximo_drawdown(dd),
                "es": metrics.expected_shortfall(serie, percentil_cauda / 100),
                "pior_dia": serie.min(),
                "duracao_drawdown_max": time_under_water_max(dd),
                "maior_sequencia_perdas": metrics.maior_sequencia(serie, positivo=False),
            },
            "diversificacao": {
                "correlacao_media": corr.loc[nome].drop(nome).mean(),
                "correlacao_dias_negativos": corr_perdas.loc[nome].drop(nome).mean(),
                "coincidencia_piores_dias": corr_piores.loc[nome].drop(nome).mean(),
                "contribuicao_drawdown_portfolio_pct": contribuicoes[nome]["participacao_drawdown_pct"],
                "retorno_quando_outros_perdem": largo.loc[dias_outros_perdem, nome].mean(),
            },
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


def _sincronizar_alocacao(
    alocacao: dict, diarios_referencia: dict, margens_por_contrato: dict, usar_janela_comum: bool,
) -> tuple:
    """Monta `largo`/`margens_ativas` para UMA alocação -- mesma lógica
    por-combinação usada por `buscar_combinacoes_portfolio` (extraída
    aqui para `buscar_combinacoes_portfolio_com_filtros`/
    `vizinhanca_local` compartilharem, sem duplicar uma terceira vez; a
    função ORIGINAL `buscar_combinacoes_portfolio` permanece intocada,
    pedido explícito do usuário). Retorna `(None, None)` se a alocação é
    degenerada (todos os robôs em 0 contratos) ou se `usar_janela_comum`
    deixaria a janela comum vazia -- os dois casos silenciosos que
    `buscar_combinacoes_portfolio` já pulava sem contar."""
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
        return None, None

    largo = sincronizar_portfolio(diarios_ativos)
    if usar_janela_comum:
        try:
            largo = restringir_janela_comum(largo)
        except ValueError:
            return None, None
    return largo, margens_ativas


def _metricas_de_alocacao(
    alocacao: dict, largo: pd.DataFrame, margens_ativas: dict,
    percentil_cauda: int, fracao_reserva_operacional: float, increment: float,
) -> dict:
    """Métricas CARAS para uma alocação já sincronizada (`largo` de
    `_sincronizar_alocacao`) -- mesmo formato de resultado de
    `buscar_combinacoes_portfolio`."""
    agregadas = metricas_agregadas(largo)
    limiar = limiar_agregado_portfolio(
        largo, margens_ativas, percentil_cauda, fracao_reserva_operacional, increment,
    )
    limiar_ativo = limiar.get("limiar_recomendado", limiar["limiar_bruto"])
    rlt = rlt_e_risco_portfolio(largo, limiar=limiar_ativo)
    return {
        "alocacao": alocacao,
        "lucro_total": agregadas["lucro_total"],
        "mdd": agregadas["mdd"],
        "es_95": agregadas["es_95"],
        "limiar_ativo": limiar_ativo,
        "rlt_acumulado": rlt["rlt_acumulado"],
        "mdd_sobre_limiar": rlt["mdd_sobre_limiar"],
    }


def buscar_combinacoes_portfolio_com_filtros(
    diarios_referencia: dict,
    margens_por_contrato: dict,
    candidatos_contratos: dict,
    percentil_cauda: int = 95,
    fracao_reserva_operacional: float = 0.0,
    increment: float = None,
    usar_janela_comum: bool = True,
    deduplicar_composicao: bool = False,
    min_robos_ativos: int = 0,
    margem_maxima: float = None,
    perda_diaria_maxima: float = None,
    clusters: list = None,
    max_contratos_por_cluster: int = None,
) -> dict:
    """Backlog de `prompts/otimizacao.pdf` (fora dos épicos do PDF-fonte):
    variante de `buscar_combinacoes_portfolio` com um funil de filtros
    baratos ANTES do cálculo caro por combinação. Pedido explícito do
    usuário: função NOVA e paralela, não uma modificação de
    `buscar_combinacoes_portfolio` -- para comparar lado a lado na UI, e
    para não arriscar o comportamento já testado daquela função. Com
    todos os filtros desligados (os padrões), reproduz EXATAMENTE
    `buscar_combinacoes_portfolio` -- mesmo pipeline por combinação
    (`sincronizar_portfolio`/`metricas_agregadas`/
    `limiar_agregado_portfolio`/`rlt_e_risco_portfolio`), só reorganizado
    em camadas para permitir podar combinações ANTES de chegar nele:

    1. `deduplicar_composicao=True`: `[2,2]` é a MESMA composição que
       `[1,1]` em outra escala (reduz cada vetor de contratos pelo MDC) --
       mantém só a combinação de MENOR escala por composição
       (documento-fonte §13: "escolha a menor escala que represente
       razoavelmente"). Puramente combinatório, não toca nenhum dado --
       roda antes de qualquer outro filtro.
    2. `min_robos_ativos`/`margem_maxima`/`max_contratos_por_cluster`:
       filtros baratos calculados só a partir da alocação (quantos
       candidatos são > 0, margem = margem_por_contrato × contratos
       somada, soma de contratos dentro de cada grupo de
       `clusters` -- ver `clusters_de_risco`) -- antes de sincronizar
       qualquer série diária. `clusters`/`max_contratos_por_cluster`
       precisam vir JUNTOS (um sem o outro não filtra nada) -- backlog
       de prompts/otimizacao.pdf §4/§5 ("nenhum cluster acima de X% do
       risco"; aqui em contratos, não %, mesma simplificação de
       `max_candidato` por robô já existente).
    3. `perda_diaria_maxima`: depois de sincronizar (e restringir à
       janela comum, se `usar_janela_comum`), descarta a combinação se o
       PIOR DIA HISTÓRICO da série combinada (`combinada.min()`, já
       disponível sem rodar `metricas_agregadas`/`limiar_agregado_
       portfolio`/`rlt_e_risco_portfolio`) for pior que este limite.
       Este NÃO é um cenário estressado/Monte Carlo -- rodar Monte Carlo
       por combinação seria caro demais para um filtro de funil (fica
       para uma fase de finalistas, backlog separado).

    Deliberadamente NÃO incluídos nesta rodada: exposição bruta (nenhuma
    noção de "exposição" existe hoje no código -- inventar uma violaria
    AGENTS.md §8, precisa de uma convenção decidida antes) e contribuição
    máxima de risco por robô (exigiria rodar `contribuicao_risco_por_robo`
    por combinação, o oposto de um filtro barato -- também backlog).

    Retorna um `dict` (não uma `list[dict]` como `buscar_combinacoes_
    portfolio`) para expor a contagem de quantas combinações cada camada
    podou -- é o que permite comparar o efeito de cada filtro, não só o
    resultado final:
    `resultados` (mesmo formato de `buscar_combinacoes_portfolio`,
    passável direto para `selecionar_melhores_combinacoes`/
    `fronteira_pareto`, nenhuma duplicação nelas), `n_combinacoes_totais`,
    `n_puladas_composicao_duplicada`, `n_puladas_sobrevivencia`,
    `n_puladas_cluster`, `n_puladas_perda_diaria`, `n_avaliadas`.

    Mesmo limite/erro de `buscar_combinacoes_portfolio` para o total
    BRUTO de combinações (`_LIMITE_COMBINACOES_OTIMIZACAO`) -- os filtros
    reduzem quantas são efetivamente CALCULADAS, não quantas a
    especificação de candidatos pode gerar."""
    nomes = list(diarios_referencia.keys())
    listas_candidatos = [candidatos_contratos[nome] for nome in nomes]

    combinacoes_brutas = list(itertools.product(*listas_candidatos))
    n_total = len(combinacoes_brutas)
    if n_total > _LIMITE_COMBINACOES_OTIMIZACAO:
        raise ValueError(
            f"{n_total} combinações excede o limite de {_LIMITE_COMBINACOES_OTIMIZACAO} -- "
            "reduza o número de candidatos por robô (ou o passo entre eles)"
        )

    sobreviventes = combinacoes_brutas
    n_puladas_dedupe = 0
    if deduplicar_composicao:
        menor_por_composicao = {}
        for combinacao in combinacoes_brutas:
            if not any(combinacao):
                menor_por_composicao[combinacao] = combinacao  # degenerada (tudo 0), única, sem o que deduplicar
                continue
            g = math.gcd(*combinacao)
            canonica = tuple(n // g for n in combinacao)
            atual = menor_por_composicao.get(canonica)
            if atual is None or g < math.gcd(*atual):
                menor_por_composicao[canonica] = combinacao
        sobreviventes = list(menor_por_composicao.values())
        n_puladas_dedupe = n_total - len(sobreviventes)

    resultados = []
    n_puladas_sobrevivencia = 0
    n_puladas_cluster = 0
    n_puladas_perda_diaria = 0
    for combinacao in sobreviventes:
        alocacao = dict(zip(nomes, combinacao))

        n_ativos = sum(1 for n in combinacao if n > 0)
        if n_ativos < min_robos_ativos:
            n_puladas_sobrevivencia += 1
            continue
        margem_total = sum(margens_por_contrato[nome] * n for nome, n in alocacao.items())
        if margem_maxima is not None and margem_total > margem_maxima:
            n_puladas_sobrevivencia += 1
            continue
        if clusters is not None and max_contratos_por_cluster is not None:
            excede_cluster = any(
                sum(alocacao.get(nome, 0) for nome in cluster) > max_contratos_por_cluster
                for cluster in clusters
            )
            if excede_cluster:
                n_puladas_cluster += 1
                continue

        largo, margens_ativas = _sincronizar_alocacao(
            alocacao, diarios_referencia, margens_por_contrato, usar_janela_comum,
        )
        if largo is None:
            continue

        if perda_diaria_maxima is not None:
            combinada = serie_combinada(largo)
            if combinada.min() < perda_diaria_maxima:
                n_puladas_perda_diaria += 1
                continue

        resultados.append(_metricas_de_alocacao(
            alocacao, largo, margens_ativas, percentil_cauda, fracao_reserva_operacional, increment,
        ))

    return {
        "resultados": resultados,
        "n_combinacoes_totais": n_total,
        "n_puladas_composicao_duplicada": n_puladas_dedupe,
        "n_puladas_sobrevivencia": n_puladas_sobrevivencia,
        "n_puladas_cluster": n_puladas_cluster,
        "n_puladas_perda_diaria": n_puladas_perda_diaria,
        "n_avaliadas": len(resultados),
    }


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


def curva_limiares_mdd(resultados: list[dict], limites_mdd: list[float]) -> list[dict]:
    """Backlog de `prompts/otimizacao.pdf` §7: em vez de pedir ao usuário
    um único MDD máximo, gera uma curva com vários limiares e, "para
    cada limiar, retorna somente a carteira de maior RLT". Opera sobre
    `resultados` já calculados (por `buscar_combinacoes_portfolio` OU
    `buscar_combinacoes_portfolio_com_filtros(...)["resultados"]` --
    qualquer `list[dict]` no formato já usado por `selecionar_melhores_
    combinacoes`/`fronteira_pareto`), nenhuma busca nova.

    Distinto do objetivo já existente "maximizar_lucro_com_limite_mdd"
    (`selecionar_melhores_combinacoes`), que maximiza LUCRO sob a mesma
    restrição de MDD -- RLT e lucro bruto são objetivos diferentes, por
    isso esta função tem sua própria lógica de seleção (filtra por MDD,
    ordena por `rlt_acumulado`) em vez de reusar aquele objetivo com um
    nome enganoso.

    Retorna uma linha por limiar, NA MESMA ORDEM de `limites_mdd`:
    `{"limite_mdd": limite, "n_combinacoes_validas": N, "melhor": dict|None}`.
    `melhor` é `None` (nunca um erro) quando nenhuma combinação em
    `resultados` satisfaz aquele limiar -- um limiar sem candidato válido
    e uma lista de resultados vazia são coisas diferentes, nunca
    confundidas silenciosamente."""
    curva = []
    for limite in limites_mdd:
        validos = [r for r in resultados if r["mdd"] >= limite]
        melhor = max(validos, key=lambda r: r["rlt_acumulado"]) if validos else None
        curva.append({
            "limite_mdd": limite,
            "n_combinacoes_validas": len(validos),
            "melhor": melhor,
        })
    return curva


def vizinhanca_local(
    alocacao_base: dict,
    diarios_referencia: dict,
    margens_por_contrato: dict,
    percentil_cauda: int = 95,
    fracao_reserva_operacional: float = 0.0,
    increment: float = None,
    usar_janela_comum: bool = True,
    incluir_transferencias: bool = True,
) -> dict:
    """Backlog de `prompts/otimizacao.pdf` §9 ("Robustez local para
    contratos inteiros"): para uma carteira já escolhida, testa vizinhas
    a ±1 contrato POR ROBÔ (uma coordenada por vez) e, opcionalmente
    (`incluir_transferencias=True`, padrão), uma transferência de 1
    contrato entre cada PAR ORDENADO de robôs (-1 num, +1 noutro) --
    mesma ideia do documento-fonte ("teste vizinhas... também teste
    transferências"). Ele mesmo não classifica "platô robusto" vs. "pico
    isolado" -- isso depende de uma tolerância que é decisão de produto
    (ver epsilon-Pareto, backlog), não uma convenção do PDF-fonte; quem
    consome decide o que "boa o suficiente" significa. A leitura
    pretendida (documento-fonte): "se a carteira é excelente mas todas as
    vizinhas são ruins, ela provavelmente explora uma coincidência
    histórica; se a carteira e as vizinhas são boas, é um platô robusto."

    Contratos negativos nunca são gerados (mínimo 0 -- equivalente a
    excluir aquele robô, candidato válido no resto do módulo). Vizinhas
    degeneradas (todos os robôs em 0) ou cuja janela comum ficaria vazia
    (`usar_janela_comum=True`) são omitidas do resultado, não inventadas
    como zero -- mesma convenção de `buscar_combinacoes_portfolio`.

    Reusa `_sincronizar_alocacao`/`_metricas_de_alocacao` (extraídas de
    `buscar_combinacoes_portfolio_com_filtros` para as duas funções
    novas compartilharem, sem duplicar o pipeline uma terceira vez) --
    a função ORIGINAL `buscar_combinacoes_portfolio` permanece intocada
    (pedido explícito do usuário).

    Retorna `{"base": dict, "vizinhas": list[dict]}` -- cada entrada tem
    o mesmo formato de `buscar_combinacoes_portfolio` mais `"tipo"`
    (`"±1 <nome>"` ou `"transferência <de> -> <para>"`) identificando QUAL
    perturbação gerou aquela vizinha; as duas direções (-1/+1) do mesmo
    `"±1 <nome>"` compartilham o rótulo -- a direção já está implícita na
    própria `alocacao` de cada entrada.

    Levanta `ValueError` se a própria carteira base for degenerada (0
    contratos em todos os robôs) ou não tiver janela comum -- não há o
    que testar vizinhança de uma base que nem existe."""
    nomes = list(alocacao_base.keys())

    candidatos = []
    for nome in nomes:
        for delta in (-1, 1):
            novo_n = alocacao_base[nome] + delta
            if novo_n < 0:
                continue
            vizinha = dict(alocacao_base)
            vizinha[nome] = novo_n
            candidatos.append((f"±1 {nome}", vizinha))

    if incluir_transferencias:
        for de, para in itertools.permutations(nomes, 2):
            if alocacao_base[de] <= 0:
                continue
            vizinha = dict(alocacao_base)
            vizinha[de] -= 1
            vizinha[para] += 1
            candidatos.append((f"transferência {de} -> {para}", vizinha))

    def _avaliar(alocacao: dict) -> dict:
        largo, margens_ativas = _sincronizar_alocacao(
            alocacao, diarios_referencia, margens_por_contrato, usar_janela_comum,
        )
        if largo is None:
            return None
        return _metricas_de_alocacao(
            alocacao, largo, margens_ativas, percentil_cauda, fracao_reserva_operacional, increment,
        )

    base_resultado = _avaliar(alocacao_base)
    if base_resultado is None:
        raise ValueError(
            "A carteira base é degenerada (0 contratos em todos os robôs) ou não tem janela comum"
        )

    vizinhas = []
    for tipo, alocacao in candidatos:
        resultado = _avaliar(alocacao)
        if resultado is None:
            continue
        vizinhas.append({**resultado, "tipo": tipo})

    return {"base": base_resultado, "vizinhas": vizinhas}


def _eficiencia_rlt_mdd(rlt_acumulado: float, mdd: float) -> float:
    """RLT/|MDD| -- maior é melhor. `mdd == 0` (nunca houve drawdown)
    trataria uma divisão por zero: `+inf` se RLT > 0 (eficiência
    infinita, literalmente nenhum risco incorrido para o retorno obtido),
    `-inf` se RLT < 0 (prejuízo sem nenhum drawdown reconhecido é pior
    que qualquer combinação com MDD), `nan` se RLT também é 0 (nenhuma
    base de comparação) -- mesmo espírito das convenções de borda já
    documentadas em `metrics.payoff`/`metrics.profit_factor`."""
    if mdd == 0:
        if rlt_acumulado > 0:
            return math.inf
        if rlt_acumulado < 0:
            return -math.inf
        return math.nan
    return rlt_acumulado / abs(mdd)


def funil_selecao_portfolio(
    diarios_referencia: dict,
    margens_por_contrato: dict,
    candidatos_contratos: dict,
    percentil_cauda: int = 95,
    fracao_reserva_operacional: float = 0.0,
    increment: float = None,
    usar_janela_comum: bool = True,
    deduplicar_composicao: bool = False,
    min_robos_ativos: int = 0,
    margem_maxima: float = None,
    perda_diaria_maxima: float = None,
    clusters: list = None,
    max_contratos_por_cluster: int = None,
    top_n_eficiencia: int = 20,
    tolerancia_robustez_pct: float = 20.0,
    incluir_transferencias_robustez: bool = True,
) -> dict:
    """Backlog de `prompts/otimizacao.pdf` §6 ("eu não escolheria entre
    'máximo RLT' e 'mínimo MDD'. Usaria uma sequência [de camadas]").
    Forma CONFIRMADA com o usuário antes de implementar (AGENTS.md §24 --
    TASKS.md já sinalizava que isso precisava de alinhamento antes de
    tocar `selecionar_melhores_combinacoes`/`otimizar_portfolio`, que
    permanecem intocados: este é um fluxo NOVO e paralelo, não uma
    substituição):

    1. **Sobrevivência**: `buscar_combinacoes_portfolio_com_filtros` (já
       existente) -- todos os parâmetros de filtro dessa função
       (dedupe/min_robos_ativos/margem_maxima/perda_diaria_maxima/
       clusters) são repassados diretamente, nenhuma lógica nova aqui.
    2. **Eficiência**: ranqueia os sobreviventes por `_eficiencia_rlt_mdd`
       (RLT/|MDD|, computável dos campos que a camada 1 já calcula --
       nenhuma fórmula nova) e mantém os `top_n_eficiencia` melhores.
    3. **Robustez**: roda `vizinhanca_local` (já existente) em cada um
       dos `top_n_eficiencia` e elimina quem tem a MÉDIA do
       `rlt_acumulado` das vizinhas abaixo de
       `(1 - tolerancia_robustez_pct/100) × RLT da própria base` --
       "todas as vizinhas são ruins" vira "a média das vizinhas é ruim"
       (agregação por média, não o mínimo -- o documento fala da carteira
       E das vizinhas serem boas como afirmação coletiva, não de que
       toda vizinha individual precise passar; usar o mínimo seria
       eliminar quase tudo com uma única vizinha ruim de várias). Uma
       base sem NENHUMA vizinha válida (`vizinhas` vazia) não é eliminada
       por falta de evidência -- não há o que reprovar. Sem walk-forward
       ainda (backlog separado), esta é a única evidência de robustez
       disponível hoje.
    4. **Simplicidade**: entre os sobreviventes da camada 3, ordena por
       eficiência decrescente e, como critério de DESEMPATE, por total
       de contratos (`sum(alocacao.values())`) crescente -- não uma
       comparação de similaridade epsilon (isso já existe separadamente
       em `fronteira_pareto`).

    Cada camada expõe os avaliados E os sobreviventes (quando aplicável)
    -- mesmo princípio de transparência de `buscar_combinacoes_portfolio_
    com_filtros`/`fronteira_pareto` epsilon (nunca esconder o que foi
    descartado): `camada1_sobrevivencia` (dict completo de
    `buscar_combinacoes_portfolio_com_filtros`), `camada2_eficiencia`
    (lista, cada resultado + `eficiencia_rlt_mdd`), `camada3_robustez`
    (`{"avaliados": [...+ "media_rlt_vizinhas"/"robusto"...],
    "sobreviventes": [...só os robustos...]}`), `camada4_simplicidade`
    (lista final, cada resultado + `total_contratos`)."""
    camada1 = buscar_combinacoes_portfolio_com_filtros(
        diarios_referencia, margens_por_contrato, candidatos_contratos,
        percentil_cauda=percentil_cauda, fracao_reserva_operacional=fracao_reserva_operacional,
        increment=increment, usar_janela_comum=usar_janela_comum,
        deduplicar_composicao=deduplicar_composicao, min_robos_ativos=min_robos_ativos,
        margem_maxima=margem_maxima, perda_diaria_maxima=perda_diaria_maxima,
        clusters=clusters, max_contratos_por_cluster=max_contratos_por_cluster,
    )

    camada2 = sorted(
        (dict(r, eficiencia_rlt_mdd=_eficiencia_rlt_mdd(r["rlt_acumulado"], r["mdd"])) for r in camada1["resultados"]),
        key=lambda r: r["eficiencia_rlt_mdd"], reverse=True,
    )[:top_n_eficiencia]

    avaliados_camada3 = []
    for r in camada2:
        viz = vizinhanca_local(
            r["alocacao"], diarios_referencia, margens_por_contrato,
            percentil_cauda=percentil_cauda, fracao_reserva_operacional=fracao_reserva_operacional,
            increment=increment, usar_janela_comum=usar_janela_comum,
            incluir_transferencias=incluir_transferencias_robustez,
        )
        vizinhas = viz["vizinhas"]
        media_rlt_vizinhas = (
            sum(v["rlt_acumulado"] for v in vizinhas) / len(vizinhas) if vizinhas else None
        )
        robusto = (
            True if media_rlt_vizinhas is None
            else bool(media_rlt_vizinhas >= r["rlt_acumulado"] * (1 - tolerancia_robustez_pct / 100))
        )
        avaliados_camada3.append(dict(r, media_rlt_vizinhas=media_rlt_vizinhas, robusto=robusto))

    sobreviventes_camada3 = [r for r in avaliados_camada3 if r["robusto"]]

    camada4 = sorted(
        (dict(r, total_contratos=sum(r["alocacao"].values())) for r in sobreviventes_camada3),
        key=lambda r: (-r["eficiencia_rlt_mdd"], r["total_contratos"]),
    )

    return {
        "camada1_sobrevivencia": camada1,
        "camada2_eficiencia": camada2,
        "camada3_robustez": {"avaliados": avaliados_camada3, "sobreviventes": sobreviventes_camada3},
        "camada4_simplicidade": camada4,
    }


def fronteira_pareto(
    resultados: list, eixo_retorno: str, eixo_risco: str,
    tolerancia_retorno_pct: float = 0.0, tolerancia_risco_pct: float = 0.0,
) -> list:
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
    mesma, e listar todas adicionaria ruído sem informação nova).

    Epsilon-Pareto (backlog de `prompts/otimizacao.pdf` §8, fora dos
    épicos do PDF-fonte): `tolerancia_retorno_pct`/`tolerancia_risco_pct`
    tratam combinações "economicamente iguais" (dentro de X% uma da
    outra nos dois eixos) como uma só, além dos empates exatos já
    tratados acima -- documento-fonte: "a diferença entre RLT R$80.000/
    MDD R$14.000 e RLT R$80.200/MDD R$14.100 provavelmente não é
    economicamente relevante". Tolerância é decisão de PRODUTO, não
    convenção financeira -- perguntado ao usuário antes de implementar
    (AGENTS.md §24); resposta foi deixar configurável ao vivo na UI, por
    isso o DEFAULT aqui é `0.0`/`0.0` (nenhuma tolerância, reproduz
    EXATAMENTE o comportamento anterior a este item -- só dedup de
    empates exatos), não o 1%/2% do exemplo do documento (que vira o
    valor inicial dos campos em `app.py`, não um padrão fixado no
    código).

    Algoritmo: sobre a fronteira ESTRITA já calculada acima (mesma ordem
    de retorno decrescente), mantém um "representante" -- um ponto cujos
    dois eixos estão dentro da tolerância (relativa,
    `abs(diferença) / abs(valor do representante)`, `<=` inclusive) do
    representante ATUAL é agrupado com ele e descartado; um ponto fora da
    tolerância em qualquer eixo vira o novo representante. Comparação
    SEMPRE contra o representante fixo do grupo corrente, nunca contra o
    último ponto agrupado -- evita "encadeamento" (uma sequência de
    pontos levemente distantes uns dos outros colapsando pontos muito
    distantes entre si). Quando o valor do representante num eixo é
    exatamente `0`, só um ponto também exatamente `0` naquele eixo conta
    como "dentro da tolerância" (divisão por zero evitada sem inventar
    uma regra de proximidade absoluta não pedida).

    Cada representante retornado carrega `"_agrupados"`: a lista das
    combinações (mesmo formato de resultado) que foram absorvidas nele --
    pedido de acompanhamento do usuário, para a UI não simplesmente
    esconder o que o agrupamento removeu. Vazia (`[]`) quando nada foi
    agrupado com aquele representante. Só aparece quando alguma
    tolerância é `> 0` -- com `0.0`/`0.0` (default) a função retorna os
    MESMOS objetos de `resultados`, sem essa chave, preservando
    compatibilidade byte a byte com o comportamento anterior a este
    item (`fronteira_pareto([resultado], ...) == [resultado]` continua
    válido)."""
    if not resultados:
        return []
    ordenados = sorted(resultados, key=lambda r: (r[eixo_retorno], r[eixo_risco]), reverse=True)
    fronteira = []
    melhor_risco_ate_agora = -math.inf
    for r in ordenados:
        if r[eixo_risco] > melhor_risco_ate_agora:
            fronteira.append(r)
            melhor_risco_ate_agora = r[eixo_risco]

    if tolerancia_retorno_pct <= 0.0 and tolerancia_risco_pct <= 0.0:
        return fronteira

    def _dentro_da_tolerancia(valor: float, referencia: float, tolerancia_pct: float) -> bool:
        if referencia == 0:
            return valor == 0
        return abs(valor - referencia) / abs(referencia) <= tolerancia_pct / 100

    agrupada = [dict(fronteira[0], _agrupados=[])]
    representante = fronteira[0]
    for r in fronteira[1:]:
        if (
            _dentro_da_tolerancia(r[eixo_retorno], representante[eixo_retorno], tolerancia_retorno_pct)
            and _dentro_da_tolerancia(r[eixo_risco], representante[eixo_risco], tolerancia_risco_pct)
        ):
            agrupada[-1]["_agrupados"].append(r)
            continue
        agrupada.append(dict(r, _agrupados=[]))
        representante = r
    return agrupada


def _pesos_risco_inverso(largo_ref: pd.DataFrame, nomes: list) -> dict:
    """Peso de cada robô proporcional a `1/desvio_padrão_diário`
    (`metrics.desvio_padrao`) da sua série de referência, normalizado
    para somar 1 -- "risco inverso", benchmark padrão (documento-fonte
    §18/19: "contratos iguais" e "risco inverso" servem para descobrir
    se a otimização complexa realmente agrega algo). Reusado tanto pelo
    benchmark `risco_inverso` global quanto DENTRO de cada cluster em
    `shortlist_portfolio`'s Handcrafted Risk."""
    inv_vol = {nome: 1.0 / metrics.desvio_padrao(largo_ref[nome]) for nome in nomes}
    soma = sum(inv_vol.values())
    return {nome: v / soma for nome, v in inv_vol.items()}


def shortlist_portfolio(
    resultados: list,
    diarios_referencia: dict,
    margens_por_contrato: dict,
    total_contratos_benchmark: int,
    alocacao_atual: dict = None,
    clusters: list = None,
    eixo_retorno: str = "lucro_total",
    eixo_risco: str = "mdd",
    retorno_minimo: float = None,
    risco_maximo: float = None,
    percentil_cauda: int = 95,
    fracao_reserva_operacional: float = 0.0,
    increment: float = None,
    usar_janela_comum: bool = True,
) -> dict:
    """Backlog de `prompts/otimizacao.pdf` §18 ("permitir ao usuário ver
    se a otimização complexa realmente supera referências simples"),
    fora dos épicos do PDF-fonte. Devolve um conjunto pequeno e NOMEADO
    de candidatas em vez de uma única tabela ordenada por objetivo:

    - `"minimum_risk"`: menor `eixo_risco` entre as combinações de
      `resultados` cujo `eixo_retorno` é `>= retorno_minimo` (sem
      filtro se `retorno_minimo` for `None`).
    - `"growth"`: maior `eixo_retorno` entre as combinações cujo
      `eixo_risco` é `>= risco_maximo` (sem filtro se `risco_maximo` for
      `None`).
    - `"balanced"`: o ponto de `fronteira_pareto(resultados, eixo_retorno,
      eixo_risco)` mais próximo do canto ideal (máximo retorno E máximo
      risco, ambos normalizados para `[0, 1]`) -- técnica padrão de
      "knee point" em otimização multiobjetivo, não uma fórmula
      inventada para este projeto.
    - `"handcrafted_risk"` (só se `clusters` for informado): peso IGUAL
      entre CLUSTERS ("um voto por cluster", não por robô -- evita que
      vários robôs correlacionados dominem só por serem vários) e,
      DENTRO de cada cluster, peso por risco inverso
      (`_pesos_risco_inverso`) entre os membros; os pesos finais são
      multiplicados por `total_contratos_benchmark` e arredondados.
    - `"contratos_iguais"`: `total_contratos_benchmark` dividido
      igualmente (arredondado) entre todos os robôs.
    - `"risco_inverso"`: `total_contratos_benchmark` distribuído por
      `_pesos_risco_inverso` GLOBAL (sem olhar clusters) -- distinto de
      Handcrafted Risk propositalmente, para isolar o efeito de
      considerar cluster ou não.
    - `"carteira_atual"` (só se `alocacao_atual` for informado):
      recalcula as métricas dessa alocação específica (a carteira que o
      usuário já está rodando), para comparação direta com as demais.

    **"Most Robust" deliberadamente NÃO implementado** -- o próprio
    documento-fonte condiciona esse perfil a walk-forward existir
    (§18: "melhor desempenho médio em walk-forward/stress/vizinhança/
    degradação"), que ainda não existe neste projeto (só robustez local,
    `vizinhanca_local`, já existe) -- decisão de escopo, não
    esquecimento.

    Cada valor do dicionário é `None` quando nenhuma combinação satisfaz
    o filtro do perfil (`minimum_risk`/`growth`) ou quando a fronteira
    está vazia (`balanced`) -- `resultados` vazio propaga `None` para
    todos os perfis baseados nele, nunca inventa um substituto."""
    nomes = list(diarios_referencia.keys())

    def _avaliar(alocacao: dict) -> dict:
        largo, margens_ativas = _sincronizar_alocacao(
            alocacao, diarios_referencia, margens_por_contrato, usar_janela_comum,
        )
        if largo is None:
            return None
        return _metricas_de_alocacao(
            alocacao, largo, margens_ativas, percentil_cauda, fracao_reserva_operacional, increment,
        )

    shortlist = {}

    validos_minimum_risk = [
        r for r in resultados if retorno_minimo is None or r[eixo_retorno] >= retorno_minimo
    ]
    shortlist["minimum_risk"] = (
        max(validos_minimum_risk, key=lambda r: r[eixo_risco]) if validos_minimum_risk else None
    )

    validos_growth = [r for r in resultados if risco_maximo is None or r[eixo_risco] >= risco_maximo]
    shortlist["growth"] = max(validos_growth, key=lambda r: r[eixo_retorno]) if validos_growth else None

    fronteira = fronteira_pareto(resultados, eixo_retorno, eixo_risco)
    if fronteira:
        retornos = [r[eixo_retorno] for r in fronteira]
        riscos = [r[eixo_risco] for r in fronteira]
        min_r, max_r = min(retornos), max(retornos)
        min_k, max_k = min(riscos), max(riscos)

        def _dist_ao_ideal(r: dict) -> float:
            nr = (r[eixo_retorno] - min_r) / (max_r - min_r) if max_r > min_r else 1.0
            nk = (r[eixo_risco] - min_k) / (max_k - min_k) if max_k > min_k else 1.0
            return (1 - nr) ** 2 + (1 - nk) ** 2

        shortlist["balanced"] = min(fronteira, key=_dist_ao_ideal)
    else:
        shortlist["balanced"] = None

    largo_ref = sincronizar_portfolio(diarios_referencia)
    if usar_janela_comum:
        largo_ref = restringir_janela_comum(largo_ref)

    if clusters is not None:
        peso_por_cluster = 1.0 / len(clusters)
        pesos_handcrafted = {}
        for cluster in clusters:
            pesos_cluster = _pesos_risco_inverso(largo_ref, cluster)
            for nome in cluster:
                pesos_handcrafted[nome] = peso_por_cluster * pesos_cluster[nome]
        alocacao_handcrafted = {
            nome: round(pesos_handcrafted.get(nome, 0.0) * total_contratos_benchmark) for nome in nomes
        }
        shortlist["handcrafted_risk"] = _avaliar(alocacao_handcrafted)

    alocacao_igual = {nome: round(total_contratos_benchmark / len(nomes)) for nome in nomes}
    shortlist["contratos_iguais"] = _avaliar(alocacao_igual)

    pesos_risco_inverso = _pesos_risco_inverso(largo_ref, nomes)
    alocacao_risco_inverso = {
        nome: round(pesos_risco_inverso[nome] * total_contratos_benchmark) for nome in nomes
    }
    shortlist["risco_inverso"] = _avaliar(alocacao_risco_inverso)

    if alocacao_atual is not None:
        shortlist["carteira_atual"] = _avaliar(alocacao_atual)

    return shortlist
