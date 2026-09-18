"""
RED: tradefolio.monte_carlo ainda não existe (AGENTS.md épico 8, tarefas
8.1/8.2/8.4).

Escopo desta fatia: `circular_block_bootstrap` cobre tanto a tarefa 8.1
("bootstrap diário sincronizado" -- sortear a linha diária inteira) quanto
a 8.2 ("circular block bootstrap", blocos de 5/10/20/40 pregões) com UMA
função genérica (AGENTS.md §8.1): 8.1 é exatamente o caso especial
`tamanho_bloco=1` de 8.2 -- sortear blocos de 1 pregão é sortear dias
independentes, e passar um DataFrame (em vez de uma Series) já mantém
colunas sincronizadas na mesma linha sorteada (ex. WIN e WDO no mesmo
dia), sem precisar de uma segunda implementação.

Decisões de design tomadas (documentadas, não escondidas -- AGENTS.md §8):
- `seed=None` (padrão) gera uma semente aleatória verdadeira e a REPORTA
  no resultado (`ResultadoBootstrap.seed`) -- nunca escondida, mesmo
  quando não escolhida pelo usuário (PDF-fonte: "seed" é parâmetro
  obrigatório do método, mas isso não impede gerar uma e mostrar qual foi
  usada). Reusar essa mesma semente reproduz exatamente as mesmas
  trajetórias.
- `incluir_dias_sem_operacao=True` (padrão) -- dias NO_TRADE são
  histórico legítimo e entram no pool de reamostragem como qualquer
  outro dia; `False` os exclui explicitamente (parâmetro, não uma
  decisão silenciosa).
- Convenção de percentil de MDD (`resumo_trajetorias`, tarefa 8.4) reusa
  exatamente a mesma de `limiar.decompor_limiar` (não uma nova): "MDD
  P99" = `percentile(mdd_por_trajetoria, 100 - 99)` -- o percentil baixo
  da distribuição bruta (majoritariamente negativa) é o lado mais
  profundo, "99% de confiança de não ultrapassar este drawdown".

Valor do bloco==tamanho da série conferido por script antes deste teste:
`np.random.default_rng(7).integers(0, 5, size=(1,1))` sorteia início=4;
para `valores=[10,20,30,40,50]`, a trajetória circular resultante é
`[50,10,20,30,40]` -- uma rotação cíclica, não uma reamostragem i.i.d.
"""
import numpy as np
import pandas as pd
import pytest

from tradefolio.monte_carlo import (
    ResultadoBootstrap,
    aplicar_choque,
    circular_block_bootstrap,
    embaralhamento_dias,
    resumo_trajetorias,
)

SERIE = pd.Series([10.0, 20.0, 30.0, 40.0, 50.0])


def test_circular_block_bootstrap_formato_da_saida():
    resultado = circular_block_bootstrap(SERIE, tamanho_bloco=2, n_trajetorias=7, horizonte=6, seed=1)
    assert isinstance(resultado, ResultadoBootstrap)
    assert resultado.trajetorias.shape == (7, 6)
    assert resultado.seed == 1
    assert resultado.tamanho_bloco == 2
    assert resultado.colunas is None


def test_circular_block_bootstrap_valores_vem_da_serie_original():
    resultado = circular_block_bootstrap(SERIE, tamanho_bloco=3, n_trajetorias=20, horizonte=15, seed=2)
    assert set(np.unique(resultado.trajetorias)).issubset(set(SERIE.values))


def test_circular_block_bootstrap_reproducivel_com_mesma_seed():
    r1 = circular_block_bootstrap(SERIE, tamanho_bloco=2, n_trajetorias=10, horizonte=8, seed=42)
    r2 = circular_block_bootstrap(SERIE, tamanho_bloco=2, n_trajetorias=10, horizonte=8, seed=42)
    assert np.array_equal(r1.trajetorias, r2.trajetorias)


def test_circular_block_bootstrap_seeds_diferentes_dao_resultados_diferentes():
    r1 = circular_block_bootstrap(SERIE, tamanho_bloco=1, n_trajetorias=10, horizonte=20, seed=1)
    r2 = circular_block_bootstrap(SERIE, tamanho_bloco=1, n_trajetorias=10, horizonte=20, seed=2)
    assert not np.array_equal(r1.trajetorias, r2.trajetorias)


def test_circular_block_bootstrap_seed_none_gera_e_reporta_semente_reproduzivel():
    resultado = circular_block_bootstrap(SERIE, tamanho_bloco=2, n_trajetorias=5, horizonte=6, seed=None)
    assert isinstance(resultado.seed, int)

    reproduzido = circular_block_bootstrap(
        SERIE, tamanho_bloco=2, n_trajetorias=5, horizonte=6, seed=resultado.seed
    )
    assert np.array_equal(resultado.trajetorias, reproduzido.trajetorias)


def test_circular_block_bootstrap_bloco_igual_a_serie_e_uma_rotacao_ciclica():
    # conferido por script (ver docstring do módulo): seed=7, bloco=5 ->
    # início sorteado=4 -> rotação [50,10,20,30,40], não uma reamostragem
    # i.i.d. dos elementos.
    resultado = circular_block_bootstrap(SERIE, tamanho_bloco=5, n_trajetorias=1, horizonte=5, seed=7)
    assert resultado.trajetorias.tolist() == [[50.0, 10.0, 20.0, 30.0, 40.0]]


def test_circular_block_bootstrap_exclui_dias_sem_operacao_quando_pedido():
    serie_com_zeros = pd.Series([10.0, 0.0, -5.0, 20.0, 0.0, -15.0])
    resultado = circular_block_bootstrap(
        serie_com_zeros, tamanho_bloco=1, n_trajetorias=1, horizonte=500, seed=3,
        incluir_dias_sem_operacao=False,
    )
    assert 0.0 not in resultado.trajetorias
    assert resultado.incluiu_dias_sem_operacao is False


def test_circular_block_bootstrap_dataframe_mantem_colunas_sincronizadas():
    # linha i tem WIN=10*i, WDO=10*i+1 -- um par só pode aparecer junto
    # se a linha inteira foi sorteada, provando sincronização entre colunas.
    df = pd.DataFrame({"WIN": [0.0, 10.0, 20.0, 30.0], "WDO": [1.0, 11.0, 21.0, 31.0]})
    resultado = circular_block_bootstrap(df, tamanho_bloco=1, n_trajetorias=1, horizonte=200, seed=5)

    assert resultado.colunas == ("WIN", "WDO")
    assert resultado.trajetorias.shape == (1, 200, 2)
    win = resultado.trajetorias[0, :, 0]
    wdo = resultado.trajetorias[0, :, 1]
    assert np.array_equal(wdo, win + 1.0)


def test_circular_block_bootstrap_tamanho_bloco_invalido_levanta_erro():
    with pytest.raises(ValueError):
        circular_block_bootstrap(SERIE, tamanho_bloco=0, n_trajetorias=1, horizonte=5, seed=1)


def test_resumo_trajetorias_percentis_e_probabilidades():
    """AGENTS.md épico 8.4. Trajetórias monotônicas construídas à mão
    para ter lucro total e MDD exatos e conferidos por script (mesma
    convenção peak-to-trough de tradefolio.drawdowns: equity=cumsum,
    drawdown=equity-running_max -- o "pico" é o primeiro valor
    acumulado, não um zero implícito antes do início):
    lucro total = [-40,-20,0,20,40], MDD = [-30,-15,0,0,0] (só as
    trajetórias que caem geram drawdown; as que só sobem têm running_max
    igual à própria equity, MDD=0)."""
    trajetorias = np.array([
        [-10.0, -10.0, -10.0, -10.0],
        [-5.0, -5.0, -5.0, -5.0],
        [0.0, 0.0, 0.0, 0.0],
        [5.0, 5.0, 5.0, 5.0],
        [10.0, 10.0, 10.0, 10.0],
    ])
    resultado = ResultadoBootstrap(
        trajetorias=trajetorias, colunas=None, seed=1, tamanho_bloco=1,
        n_trajetorias=5, horizonte=4, incluiu_dias_sem_operacao=True,
    )
    resumo = resumo_trajetorias(resultado)

    assert resumo["lucro_p50"] == pytest.approx(0.0)
    assert resumo["lucro_p5"] == pytest.approx(np.percentile([-40, -20, 0, 20, 40], 5))
    assert resumo["mdd_p50"] == pytest.approx(np.percentile([-30, -15, 0, 0, 0], 50))
    assert resumo["probabilidade_prejuizo"] == pytest.approx(2 / 5)


def test_resumo_trajetorias_probabilidade_toca_margem_e_abaixo_do_limiar():
    trajetorias = np.array([
        [-60.0, 0.0, 0.0, 0.0],   # equity minimo -60 (toca margem 50), termina -60
        [-10.0, 0.0, 0.0, 0.0],   # equity minimo -10, termina -10
        [10.0, 0.0, 0.0, 0.0],    # equity minimo 0, termina 10
    ])
    resultado = ResultadoBootstrap(
        trajetorias=trajetorias, colunas=None, seed=1, tamanho_bloco=1,
        n_trajetorias=3, horizonte=4, incluiu_dias_sem_operacao=True,
    )
    resumo = resumo_trajetorias(resultado, minimum_margin=50.0, limiar=5.0)

    assert resumo["probabilidade_toca_margem"] == pytest.approx(1 / 3)
    assert resumo["probabilidade_termina_abaixo_do_limiar"] == pytest.approx(2 / 3)


def test_resumo_trajetorias_sem_margem_ou_limiar_nao_inclui_essas_chaves():
    trajetorias = np.array([[1.0, 1.0], [2.0, 2.0]])
    resultado = ResultadoBootstrap(
        trajetorias=trajetorias, colunas=None, seed=1, tamanho_bloco=1,
        n_trajetorias=2, horizonte=2, incluiu_dias_sem_operacao=True,
    )
    resumo = resumo_trajetorias(resultado)
    assert "probabilidade_toca_margem" not in resumo
    assert "probabilidade_termina_abaixo_do_limiar" not in resumo


# --- CDaR e probabilidade de recuperação (backlog de
# prompts/otimizacao.pdf §12, fora dos épicos do PDF-fonte) ----------------
#
# CDaR (Conditional Drawdown at Risk) = ES aplicado à distribuição de MDD
# por trajetória, em vez de à distribuição de retornos -- mesma mecânica
# de `metrics.expected_shortfall` (média dos valores abaixo do
# percentil-limiar), generalização padrão do mercado, não uma fórmula
# nova. Probabilidade de recuperação = fração das trajetórias cujo
# equity retorna ao pico anterior ao pior drawdown em até N pregões
# depois do fundo -- trajetórias cujo fundo é o ÚLTIMO dia (sem dias
# seguintes para recuperar) contam como NÃO recuperadas, nunca invertido
# silenciosamente. Trajetória construída à mão e conferida por script:
# T1 = [10,-5,-10,0,5,25] (equity [10,5,-5,-5,0,25], MDD=-15 no dia 2,
# recupera ao pico 10 só no dia 5 -- dentro de 3 dias do fundo, não
# dentro de 2); T2 = [-10]*6 (equity monotonicamente decrescente, MDD=-50
# no ÚLTIMO dia, nunca recupera).

def test_resumo_trajetorias_cdar():
    trajetorias = np.array([
        [10.0, -5.0, -10.0, 0.0, 5.0, 25.0],
        [-10.0, -10.0, -10.0, -10.0, -10.0, -10.0],
    ])
    resultado = ResultadoBootstrap(
        trajetorias=trajetorias, colunas=None, seed=1, tamanho_bloco=1,
        n_trajetorias=2, horizonte=6, incluiu_dias_sem_operacao=True,
    )
    resumo = resumo_trajetorias(resultado)
    assert resumo["cdar_95"] == pytest.approx(-50.0)


def test_resumo_trajetorias_probabilidade_recuperacao():
    trajetorias = np.array([
        [10.0, -5.0, -10.0, 0.0, 5.0, 25.0],
        [-10.0, -10.0, -10.0, -10.0, -10.0, -10.0],
    ])
    resultado = ResultadoBootstrap(
        trajetorias=trajetorias, colunas=None, seed=1, tamanho_bloco=1,
        n_trajetorias=2, horizonte=6, incluiu_dias_sem_operacao=True,
    )
    resumo = resumo_trajetorias(resultado, horizontes_recuperacao=(2, 3))
    assert resumo["probabilidade_recuperacao_2"] == pytest.approx(0.0)
    assert resumo["probabilidade_recuperacao_3"] == pytest.approx(0.5)


def test_resumo_trajetorias_horizontes_recuperacao_padrao():
    # Padrão do documento-fonte (60/120 pregões) -- só confirma que as
    # chaves existem com esses nomes quando nada é passado explicitamente.
    trajetorias = np.array([[1.0, 1.0], [2.0, 2.0]])
    resultado = ResultadoBootstrap(
        trajetorias=trajetorias, colunas=None, seed=1, tamanho_bloco=1,
        n_trajetorias=2, horizonte=2, incluiu_dias_sem_operacao=True,
    )
    resumo = resumo_trajetorias(resultado)
    assert "probabilidade_recuperacao_60" in resumo
    assert "probabilidade_recuperacao_120" in resumo


# --- Esquema A: embaralhamento simples dos dias (backlog de
# prompts/otimizacao.pdf §11.A, fora dos épicos do PDF-fonte) --------------
#
# "Muda a ordem dos resultados, preservando os mesmos dias." Distinto de
# `circular_block_bootstrap(tamanho_bloco=1)`, que reamostra COM
# reposição (dias podem repetir, outros nunca são sorteados) --
# `embaralhamento_dias` é uma PERMUTAÇÃO sem reposição do mesmo conjunto
# de dias, sempre do tamanho da amostra (não recebe `horizonte`: uma
# permutação não pode ser maior nem menor que o conjunto permutado sem
# inventar reposição/truncamento). Valor conferido por script:
# `np.random.default_rng(7).permutation(5)` dá `[2,0,4,1,3]` na primeira
# chamada.

def test_embaralhamento_dias_e_permutacao_sem_reposicao():
    resultado = embaralhamento_dias(SERIE, n_trajetorias=1, seed=7)
    assert resultado.horizonte == 5
    trajetoria = resultado.trajetorias[0]
    assert sorted(trajetoria.tolist()) == sorted(SERIE.tolist())  # mesmo conjunto
    assert list(trajetoria) == [30.0, 10.0, 50.0, 20.0, 40.0]  # ordem de [2,0,4,1,3]


def test_embaralhamento_dias_dataframe_mantem_colunas_sincronizadas():
    df = pd.DataFrame({"WIN": [0.0, 10.0, 20.0, 30.0], "WDO": [1.0, 11.0, 21.0, 31.0]})
    resultado = embaralhamento_dias(df, n_trajetorias=3, seed=5)
    assert resultado.colunas == ("WIN", "WDO")
    assert resultado.horizonte == 4
    win = resultado.trajetorias[:, :, 0]
    wdo = resultado.trajetorias[:, :, 1]
    assert np.array_equal(wdo, win + 1.0)
    for t in range(3):
        assert sorted(win[t].tolist()) == [0.0, 10.0, 20.0, 30.0]


def test_embaralhamento_dias_reproducivel_com_mesma_seed():
    a = embaralhamento_dias(SERIE, n_trajetorias=4, seed=42)
    b = embaralhamento_dias(SERIE, n_trajetorias=4, seed=42)
    assert np.array_equal(a.trajetorias, b.trajetorias)


def test_embaralhamento_dias_exclui_dias_sem_operacao_quando_pedido():
    serie_com_zeros = pd.Series([10.0, 0.0, -5.0, 20.0, 0.0, -15.0])
    resultado = embaralhamento_dias(
        serie_com_zeros, n_trajetorias=2, seed=3, incluir_dias_sem_operacao=False,
    )
    assert 0.0 not in resultado.trajetorias
    assert resultado.horizonte == 4  # 6 dias - 2 zeros


# --- Esquema C (parcial): choques de "pior dia repetido" e "perda
# simultânea" (backlog de prompts/otimizacao.pdf §11.C) --------------------
#
# Decisão CONFIRMADA com o usuário (AGENTS.md §24): só estes dois --
# "slippage dobrado" (mesma lacuna que excluiu o esquema D: bruto/custo
# não são separáveis na série agregada do portfólio) e "correlação
# elevada artificialmente" (exigiria inventar uma técnica de
# covariância/cópula não pedida) ficam de fora, mesmo raciocínio de
# antes. Os dois implementados substituem UM dia (posição aleatória) de
# cada trajetória JÁ SIMULADA (por `circular_block_bootstrap`/
# `embaralhamento_dias`) por um "dia de choque":
# - "pior dia repetido": a linha histórica REAL do dia em que a série
#   COMBINADA (soma entre colunas) foi pior -- preserva a composição
#   real daquele dia entre os robôs, não inventa uma.
# - "perda simultânea": um dia SINTÉTICO onde cada robô, independente,
#   está no SEU PRÓPRIO pior dia histórico (podem ser datas diferentes
#   na realidade) -- testa a suposição de correlação de cauda, não
#   reproduz um dia que de fato ocorreu.

DF_CHOQUE = pd.DataFrame({"a": [10.0, -50.0, 5.0, -8.0], "b": [-5.0, -3.0, 2.0, -30.0]})
# combinada = [5, -53, 7, -38] -> pior dia combinado é o índice 1: [-50, -3].
# pior de "a" isolado = -50 (índice 1); pior de "b" isolado = -30 (índice 3).


def test_aplicar_choque_pior_dia_repetido_usa_linha_historica_real():
    base = circular_block_bootstrap(DF_CHOQUE, tamanho_bloco=1, n_trajetorias=5, horizonte=10, seed=1)
    resultado = aplicar_choque(base, DF_CHOQUE, tipo="pior_dia_repetido", seed=2)
    for t in range(5):
        assert any(
            resultado.trajetorias[t, dia, 0] == -50.0 and resultado.trajetorias[t, dia, 1] == -3.0
            for dia in range(10)
        )


def test_aplicar_choque_perda_simultanea_usa_pior_de_cada_coluna():
    base = circular_block_bootstrap(DF_CHOQUE, tamanho_bloco=1, n_trajetorias=5, horizonte=10, seed=1)
    resultado = aplicar_choque(base, DF_CHOQUE, tipo="perda_simultanea", seed=2)
    for t in range(5):
        assert any(
            resultado.trajetorias[t, dia, 0] == -50.0 and resultado.trajetorias[t, dia, 1] == -30.0
            for dia in range(10)
        )


def test_aplicar_choque_preserva_metadados_do_resultado_base():
    base = circular_block_bootstrap(DF_CHOQUE, tamanho_bloco=20, n_trajetorias=3, horizonte=50, seed=1)
    resultado = aplicar_choque(base, DF_CHOQUE, tipo="pior_dia_repetido", seed=2)
    assert resultado.colunas == base.colunas
    assert resultado.tamanho_bloco == base.tamanho_bloco
    assert resultado.n_trajetorias == base.n_trajetorias
    assert resultado.horizonte == base.horizonte


def test_aplicar_choque_tipo_invalido_levanta_erro():
    base = circular_block_bootstrap(DF_CHOQUE, tamanho_bloco=1, n_trajetorias=2, horizonte=10, seed=1)
    with pytest.raises(ValueError, match="tipo"):
        aplicar_choque(base, DF_CHOQUE, tipo="slippage_dobrado")
