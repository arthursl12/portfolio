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
import pandas as pd

from tradefolio import limiar as limiar_mod
from tradefolio import metrics
from tradefolio.drawdowns import curva_equity, drawdown, maximo_drawdown


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
    """Lucro total, MDD e ES95 sobre a série COMBINADA (tarefa 10.3,
    parcial -- ver docstring do módulo para o que falta). Reusa
    `drawdowns`/`metrics` diretamente, nenhuma fórmula nova."""
    combinada = serie_combinada(largo)
    equity = curva_equity(combinada)
    dd = drawdown(equity)
    return {
        "lucro_total": combinada.sum(),
        "mdd": maximo_drawdown(dd),
        "es_95": metrics.expected_shortfall(combinada, 0.95),
    }


def correlacao_portfolio(largo: pd.DataFrame) -> pd.DataFrame:
    """Correlação de Pearson par-a-par entre os robôs do portfólio,
    variante "todos os dias" (tarefa 10.4 -- as outras 3 variantes do
    PDF-fonte precisam de convenções extras, mesma lacuna já documentada
    para `report_data.calcular_pagina6`)."""
    return largo.corr()


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


def beneficio_diversificacao(soma_limiares_individuais: float, limiar_agregado: float) -> dict:
    """Tarefa 10.7 -- em reais e em percentual da soma individual."""
    beneficio_rs = soma_limiares_individuais - limiar_agregado
    return {
        "beneficio_rs": beneficio_rs,
        "beneficio_pct": beneficio_rs / soma_limiares_individuais if soma_limiares_individuais else float("nan"),
    }
