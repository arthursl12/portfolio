"""
RED: tradefolio.daily_results ainda não existe.

Formato alternativo ao Smarttbot orders (AGENTS.md épico 1, mas fora de
`COLUNAS_OBRIGATORIAS`/`tradefolio.importers` -- aquele é order-level,
este é um resultado diário já agregado, sem nenhum detalhe de ordem).
Pedido do usuário: um novo robô (TradingX) só tem
`dados_exemplo/daily_tradingx.csv` -- `Data;Mes;Pontos;Resultado_R$;
Saldo_Acumulado_R$`, uma linha por pregão.

Decisões de design (documentadas, não escondidas -- AGENTS.md §8):
- `bruto`/`custo`/`n_trades` ficam NaN no `diario` construído -- sem
  dado de ordem, são genuinamente DESCONHECIDOS, não inventados como 0
  (0 já significa "sem custo B3", um fato diferente de "não sabemos o
  custo"). Qualquer métrica que dependa deles degrada para NaN/"—", não
  um número fabricado.
- Métricas de nível trade (Página 2) são impossíveis por construção
  (sem trade reconstruído) -- este módulo não tenta produzi-las.
- `contratos_referencia=1` fixo, NÃO detectado (não há "Quantidade
  executada") -- decisão confirmada com o usuário: a série já representa
  1 contrato, permite escalar como os demais robôs
  (`daily.escalar_por_contratos`), diferente de tratar como um valor
  fixo não-escalável.
- Um pregão B3 ausente do arquivo vira `liquido=0`/`operou=False` --
  mesma convenção de `alignment.preencher_calendario_b3`, só que
  derivada da PRESENÇA da linha (não de `n_trades`, que não existe
  aqui).

Valores conferidos por script (dados_exemplo/daily_tradingx.csv) antes
destes testes: 174 linhas, 2026-01-06 a 2026-09-15, sem nenhum pregão
B3 ausente nesse intervalo (0 gaps), sem datas duplicadas.
"""
import io

import pandas as pd
import pytest

from tradefolio.daily_results import (
    carregar_resultados_diarios,
    eh_formato_resultados_diarios,
    montar_diario_resultados,
)

CABECALHO_RESULTADOS = "Data;Mes;Pontos;Resultado_R$;Saldo_Acumulado_R$"


def test_carregar_resultados_diarios_le_csv_real():
    resultados = carregar_resultados_diarios("dados_exemplo/daily_tradingx.csv")

    assert len(resultados) == 174
    assert list(resultados.columns) == ["liquido"]
    assert resultados.index.min() == pd.Timestamp("2026-01-06")
    assert resultados.index.max() == pd.Timestamp("2026-09-15")
    assert resultados.loc["2026-01-06", "liquido"] == pytest.approx(296.0)
    assert resultados.loc["2026-09-15", "liquido"] == pytest.approx(-345.0)


def test_carregar_resultados_diarios_datas_duplicadas_levanta_erro(tmp_path):
    caminho = tmp_path / "duplicado.csv"
    caminho.write_text(
        CABECALHO_RESULTADOS + "\n"
        "06/01/2026;Jan;100;20;20\n"
        "06/01/2026;Jan;200;40;60\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicada"):
        carregar_resultados_diarios(caminho)


def test_carregar_resultados_diarios_coluna_faltante_levanta_erro(tmp_path):
    caminho = tmp_path / "sem_resultado.csv"
    caminho.write_text("Data;Mes;Pontos\n06/01/2026;Jan;100\n", encoding="utf-8")
    with pytest.raises(ValueError, match="obrigat"):
        carregar_resultados_diarios(caminho)


def test_montar_diario_resultados_com_dados_reais():
    resultados = carregar_resultados_diarios("dados_exemplo/daily_tradingx.csv")
    diario = montar_diario_resultados(resultados)

    # Sem gaps no calendário B3 real para este robô -- confirmado por
    # script antes deste teste.
    assert len(diario) == 174
    assert diario["operou"].all()
    assert diario["bruto"].isna().all()
    assert diario["custo"].isna().all()
    assert diario["n_trades"].isna().all()
    assert (diario["liquido_por_contrato"] == diario["liquido"]).all()  # contratos_referencia=1
    assert diario.loc["2026-01-06", "liquido"] == pytest.approx(296.0)
    assert diario.loc["2026-09-15", "liquido"] == pytest.approx(-345.0)


def test_montar_diario_resultados_preenche_pregao_ausente_com_zero_e_nao_operou():
    # 2026-01-06 a 2026-01-09 são 4 pregões B3 consecutivos (conferido por
    # script); pulamos 01-07 e 01-08 de propósito.
    resultados = pd.DataFrame(
        {"liquido": [100.0, 50.0]},
        index=pd.DatetimeIndex(["2026-01-06", "2026-01-09"], name="data"),
    )
    diario = montar_diario_resultados(resultados)

    assert len(diario) == 4
    dia_ausente = pd.Timestamp("2026-01-07")
    assert diario.loc[dia_ausente, "liquido"] == 0.0
    assert diario.loc[dia_ausente, "operou"] == False  # noqa: E712
    assert pd.isna(diario.loc[dia_ausente, "bruto"])  # desconhecido, não 0
    assert diario.loc[pd.Timestamp("2026-01-06"), "operou"] == True  # noqa: E712


def test_eh_formato_resultados_diarios_detecta_pelo_cabecalho():
    assert eh_formato_resultados_diarios("dados_exemplo/daily_tradingx.csv") is True
    assert eh_formato_resultados_diarios("dados_exemplo/orders_resgat.csv") is False


def test_eh_formato_resultados_diarios_aceita_arquivo_em_memoria():
    conteudo = (CABECALHO_RESULTADOS + "\n06/01/2026;Jan;100;20;20\n").encode("utf-8-sig")
    arquivo = io.BytesIO(conteudo)
    assert eh_formato_resultados_diarios(arquivo) is True
