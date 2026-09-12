"""Motor de vapo -- withdrawal engine (AGENTS.md épico 7).

Escopo desta primeira fatia (tarefas 7.1/7.3 -- as únicas com fórmula
concreta e sem ambiguidade uma vez resolvido o modelo abaixo):
`PoliticaVapo` (interface comum, ABC no mesmo padrão de
`tradefolio.importers.OrderImporter`) + `PoliticaPisoFixo` (a única das
7 políticas nomeadas na tarefa 7.2 com fórmula literal no PDF-fonte:
"100% do excedente" acima do limiar) + `gerar_serie_vapo` (o motor
mensal, tarefa 7.3).

Deliberadamente NÃO implementadas aqui (AGENTS.md §8: nunca inventar uma
fórmula financeira a partir de um esqueleto): as outras 6 políticas da
tarefa 7.2 (percentual do excedente, teto mensal, percentual do lucro,
somente mês positivo, preservação do capital inicial, acumulação para
aumento de mão) -- cada uma precisa de uma definição explícita própria
(ex. "percentual do lucro" não diz se é lucro bruto/líquido, mensal/
acumulado) que o PDF-fonte não especifica. Adicionar novas políticas
implementando `PoliticaVapo` quando essas decisões forem tomadas.

Modelo do motor mensal (a única leitura autoconsistente da ordem literal
das colunas do PDF-fonte -- "saldo inicial" carrega de mês para mês como
uma equity corrente, não reseta a cada mês): `déficit_anterior` é
puramente uma leitura derivada (`max(0, limiar - saldo_inicial)`) para
exibição/transparência (mesmo espírito de `decompor_limiar`, épico 6.5),
não um estado extra somado de novo na fórmula do vapo -- ele já está
embutido em `saldo_antes_do_vapo` porque `saldo_inicial` é uma equity
corrente. Verificado numericamente contra dados reais
(dados_exemplo/orders_roboraiz.csv, ver tests/test_vapo.py) antes de
fixar esta interpretação.

`saldo_final` desconta o vapo BRUTO, não o líquido: a provisão fiscal é
dinheiro que sai da conta de trading para cobrir o imposto -- só o valor
efetivamente distribuível ao dono (`vapo_liquido`) é menor, a conta
como um todo perde o bruto inteiro.

Alíquota fiscal (`aliquota_fiscal`) nunca tem um valor padrão diferente
de 0.0 -- 0% é uma escolha explícita e válida (sem provisão), nunca um
imposto inventado silenciosamente (AGENTS.md §8).
"""
from abc import ABC, abstractmethod

import pandas as pd

from tradefolio import limiar as limiar_mod
from tradefolio import metrics


class PoliticaVapo(ABC):
    """Interface comum entre políticas de retirada (AGENTS.md épico 7,
    tarefa 7.2) -- o motor (`gerar_serie_vapo`) não precisa conhecer a
    fórmula interna de nenhuma política concreta."""

    @abstractmethod
    def calcular_vapo_bruto(self, saldo_antes_do_vapo: float, limiar: float, deficit_anterior: float) -> float:
        """Quanto retirar (bruto, antes da provisão fiscal) neste mês."""


class PoliticaPisoFixo(PoliticaVapo):
    """Tarefa 7.1: retira 100% do excedente acima do limiar (o piso).
    `deficit_anterior` não entra na fórmula -- já está embutido em
    `saldo_antes_do_vapo` (ver docstring do módulo)."""

    def calcular_vapo_bruto(self, saldo_antes_do_vapo: float, limiar: float, deficit_anterior: float) -> float:
        return max(0.0, saldo_antes_do_vapo - limiar)


def gerar_serie_vapo(
    mensal: pd.DataFrame,
    limiar: float,
    politica: PoliticaVapo,
    aliquota_fiscal: float = 0.0,
    saldo_inicial: float = 0.0,
) -> pd.DataFrame:
    """Motor mensal de vapo (AGENTS.md épico 7, tarefa 7.3). `mensal` é
    a saída de `tradefolio.monthly.agregar_mensal` na escala TOTAL da
    posição (`diario['liquido']`, não por contrato -- mesma decisão de
    escala já resolvida para o limiar/RLT nesta sessão), precisando das
    colunas `bruto`/`custo`/`liquido`."""
    linhas = []
    saldo = saldo_inicial
    for mes, linha_mensal in mensal.iterrows():
        saldo_do_mes_anterior = saldo
        deficit_anterior = max(0.0, limiar - saldo_do_mes_anterior)
        pnl_liquido = linha_mensal["liquido"]
        saldo_antes_do_vapo = saldo_do_mes_anterior + pnl_liquido
        vapo_bruto = politica.calcular_vapo_bruto(saldo_antes_do_vapo, limiar, deficit_anterior)
        provisao_fiscal = aliquota_fiscal * vapo_bruto
        vapo_liquido = vapo_bruto - provisao_fiscal
        saldo_final = saldo_antes_do_vapo - vapo_bruto

        linhas.append({
            "mes": mes,
            "saldo_inicial": saldo_do_mes_anterior,
            "pnl_bruto": linha_mensal["bruto"],
            "custos": linha_mensal["custo"],
            "pnl_liquido": pnl_liquido,
            "saldo_antes_do_vapo": saldo_antes_do_vapo,
            "deficit_anterior": deficit_anterior,
            "vapo_bruto": vapo_bruto,
            "provisao_fiscal": provisao_fiscal,
            "vapo_liquido": vapo_liquido,
            "saldo_final": saldo_final,
        })
        saldo = saldo_final

    return pd.DataFrame(linhas).set_index("mes")


def vlt_acumulado(vapo_liquido: pd.Series, limiar: float) -> float:
    """VLT = vapo sobre o limiar (AGENTS.md épico 7.4) -- mesma fórmula
    genérica `valor / limiar` de `limiar.rlt_acumulado` (AGENTS.md §8.1),
    reusada diretamente, não reimplementada."""
    return limiar_mod.rlt_acumulado(vapo_liquido.sum(), limiar)


def vlt_mensal(vapo_liquido: pd.Series, limiar: float) -> pd.Series:
    """Como vlt_acumulado, uma razão por mês -- reusa limiar.rlt_mensal."""
    return limiar_mod.rlt_mensal(vapo_liquido, limiar)


def frequencia_meses_com_vapo(vapo_liquido: pd.Series) -> float:
    """Fração de meses com vapo líquido > 0 -- reusa metrics.taxa_positivos
    (AGENTS.md §8.1: mesma fórmula, série diferente)."""
    return metrics.taxa_positivos(vapo_liquido)


def maior_vapo(vapo_liquido: pd.Series) -> float:
    return vapo_liquido.max()


def maior_sequencia_sem_vapo(vapo_liquido: pd.Series) -> int:
    """Maior corrida de meses consecutivos com vapo líquido == 0 -- reusa
    metrics.maior_sequencia_mascara (extraída de maior_sequencia nesta
    mesma leva, exatamente para cobrir um predicado de igualdade que
    maior_sequencia, só >0/<0, não cobria)."""
    return metrics.maior_sequencia_mascara(vapo_liquido == 0)


def meses_positivos_sem_vapo_por_deficit(serie_vapo: pd.DataFrame) -> int:
    """Meses com resultado líquido positivo que, mesmo assim, não geraram
    vapo -- porque o déficit acumulado de meses anteriores ainda não
    tinha sido coberto (AGENTS.md épico 7.4, mesmo conceito citado em
    "lâmina ideal.pdf" §6: "um mês positivo não significa necessariamente
    dinheiro distribuível"). Recebe a série inteira de `gerar_serie_vapo`
    (precisa de `pnl_liquido` e `vapo_bruto` juntos, não uma métrica
    isolada de uma única coluna)."""
    return int(((serie_vapo["pnl_liquido"] > 0) & (serie_vapo["vapo_bruto"] == 0)).sum())


def deficit_atual(saldo_final: pd.Series, limiar: float) -> float:
    """Déficit do robô em relação ao limiar no fim da série (AGENTS.md
    épico 7.4) -- 0 se o saldo final já estiver no limiar ou acima."""
    return max(0.0, limiar - saldo_final.iloc[-1])
