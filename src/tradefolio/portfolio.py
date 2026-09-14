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
import math

import pandas as pd

from tradefolio import limiar as limiar_mod
from tradefolio import metrics
from tradefolio.drawdowns import curva_equity, drawdown, maximo_drawdown, time_under_water_max


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
