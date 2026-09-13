"""Monte Carlo engine (AGENTS.md épico 8).

Escopo desta primeira fatia (tarefas 8.1/8.2/8.4): `circular_block_bootstrap`
cobre tanto 8.1 ("bootstrap diário sincronizado" -- sortear a linha
diária inteira) quanto 8.2 ("circular block bootstrap", blocos de
5/10/20/40 pregões) com UMA função genérica (AGENTS.md §8.1): 8.1 é
exatamente o caso especial `tamanho_bloco=1` de 8.2 -- sortear blocos de
tamanho 1 é sortear dias independentes, e passar um `pd.DataFrame` (em
vez de uma `pd.Series`) já mantém colunas sincronizadas na mesma linha
sorteada (ex. WIN e WDO no mesmo dia, ou -- futuramente, Épico 10 -- um
robô por coluna num portfólio), sem precisar de uma segunda
implementação.

Deliberadamente NÃO implementadas aqui: tarefa 8.3 (cenários
deteriorados -- cada uma das 6 transformações precisa de uma decisão
própria antes de codificar, ex. "duplicar os piores dias" não tem uma
definição literal única) e 8.5/8.6 (processamento em background e cache
-- bloqueados pela mesma decisão de arquitetura do Épico 1.4,
persistência, ainda não tomada).

Decisões de design tomadas (documentadas, não escondidas -- AGENTS.md §8):

- `seed=None` (padrão) gera uma semente aleatória verdadeira via
  `numpy.random.SeedSequence` e a REPORTA em `ResultadoBootstrap.seed` --
  nunca escondida. Reusar essa mesma semente reproduz exatamente as
  mesmas trajetórias (mesmo princípio de proveniência de
  `tradefolio.metric_registry`: nunca misturar dado observado com
  simulado sem rótulo/rastro).
- `incluir_dias_sem_operacao=True` (padrão) -- dias NO_TRADE são
  histórico legítimo e entram no pool de reamostragem como qualquer
  outro dia; `False` os exclui explicitamente. Para um DataFrame
  multi-coluna, uma linha só é excluída se TODAS as colunas forem zero
  nela (nenhuma coluna operou naquele dia).
- Convenção de percentil de MDD em `resumo_trajetorias` (tarefa 8.4)
  reusa exatamente a mesma de `limiar.decompor_limiar`, não uma nova:
  "MDD P99" = `percentile(mdd_por_trajetoria, 100 - 99)` -- o percentil
  baixo da distribuição bruta (majoritariamente negativa) é o lado mais
  profundo ("99% de confiança de não ultrapassar este drawdown").
  "Lucro P5" não precisa dessa inversão (maior é sempre melhor para
  lucro, ao contrário de drawdown).
- MDD por trajetória usa a MESMA convenção peak-to-trough de
  `tradefolio.drawdowns` (equity=cumsum, drawdown=equity-running_max) --
  não uma reimplementação, só vetorizada por trajetória.
"""
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ResultadoBootstrap:
    trajetorias: np.ndarray  # (n_trajetorias, horizonte) ou (n_trajetorias, horizonte, n_colunas)
    colunas: tuple | None  # nomes das colunas se a entrada era um DataFrame, None se era uma Series
    seed: int
    tamanho_bloco: int
    n_trajetorias: int
    horizonte: int
    incluiu_dias_sem_operacao: bool


def circular_block_bootstrap(
    dados,
    tamanho_bloco: int,
    n_trajetorias: int,
    horizonte: int,
    seed: int = None,
    incluir_dias_sem_operacao: bool = True,
) -> ResultadoBootstrap:
    """`dados`: `pd.Series` (uma única série, ex. `diario['liquido']`) ou
    `pd.DataFrame` (múltiplas colunas que devem ficar sincronizadas na
    mesma linha sorteada, ex. `daily.pivotar_liquido_por_ativo`). Ver
    docstring do módulo para as convenções de seed/zeros/percentil."""
    if tamanho_bloco < 1:
        raise ValueError(f"tamanho_bloco deve ser >= 1, recebido {tamanho_bloco}")

    e_dataframe = isinstance(dados, pd.DataFrame)
    valores = dados.to_numpy(dtype=float)
    if not e_dataframe:
        valores = valores.reshape(-1, 1)

    if not incluir_dias_sem_operacao:
        linhas_com_atividade = ~(valores == 0).all(axis=1)
        valores = valores[linhas_com_atividade]

    n = len(valores)
    if n == 0:
        raise ValueError("nenhum dia disponível para reamostrar (série vazia após o filtro de atividade)")

    if seed is None:
        seed = int(np.random.SeedSequence().entropy)
    rng = np.random.default_rng(seed)

    n_blocos = math.ceil(horizonte / tamanho_bloco)
    inicios = rng.integers(0, n, size=(n_trajetorias, n_blocos))
    offsets = np.arange(tamanho_bloco)
    indices = (inicios[:, :, None] + offsets[None, None, :]) % n  # (T, B, L)
    indices = indices.reshape(n_trajetorias, n_blocos * tamanho_bloco)[:, :horizonte]  # (T, H)

    trajetorias = valores[indices]  # (T, H, C)
    if not e_dataframe:
        trajetorias = trajetorias[:, :, 0]  # (T, H)

    return ResultadoBootstrap(
        trajetorias=trajetorias,
        colunas=tuple(dados.columns) if e_dataframe else None,
        seed=seed,
        tamanho_bloco=tamanho_bloco,
        n_trajetorias=n_trajetorias,
        horizonte=horizonte,
        incluiu_dias_sem_operacao=incluir_dias_sem_operacao,
    )


def resumo_trajetorias(resultado: ResultadoBootstrap, minimum_margin: float = None, limiar: float = None) -> dict:
    """Percentis e probabilidades sobre as trajetórias simuladas
    (AGENTS.md épico 8.4). `minimum_margin`/`limiar` opcionais -- as
    chaves de probabilidade correspondentes só aparecem quando
    informados (mesmo padrão de `report_data.calcular_pagina1`'s
    `ordens` opcional: nada é calculado sem o dado necessário)."""
    trajetorias = resultado.trajetorias
    if trajetorias.ndim == 3:
        trajetorias = trajetorias.sum(axis=2)  # soma entre colunas -> resultado total por dia

    equity = np.cumsum(trajetorias, axis=1)
    lucro_total = equity[:, -1]
    running_max = np.maximum.accumulate(equity, axis=1)
    drawdown = equity - running_max
    mdd_por_trajetoria = drawdown.min(axis=1)

    resumo = {
        "lucro_p5": float(np.percentile(lucro_total, 5)),
        "lucro_p25": float(np.percentile(lucro_total, 25)),
        "lucro_p50": float(np.percentile(lucro_total, 50)),
        "lucro_p75": float(np.percentile(lucro_total, 75)),
        "lucro_p95": float(np.percentile(lucro_total, 95)),
        "mdd_p50": float(np.percentile(mdd_por_trajetoria, 100 - 50)),
        "mdd_p90": float(np.percentile(mdd_por_trajetoria, 100 - 90)),
        "mdd_p95": float(np.percentile(mdd_por_trajetoria, 100 - 95)),
        "mdd_p99": float(np.percentile(mdd_por_trajetoria, 100 - 99)),
        "probabilidade_prejuizo": float((lucro_total < 0).mean()),
    }
    if minimum_margin is not None:
        resumo["probabilidade_toca_margem"] = float((equity.min(axis=1) <= -minimum_margin).mean())
    if limiar is not None:
        resumo["probabilidade_termina_abaixo_do_limiar"] = float((lucro_total < limiar).mean())
    return resumo
