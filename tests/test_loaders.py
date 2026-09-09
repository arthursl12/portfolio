"""
RED: tradefolio.loaders ainda não existe.

carregar_ordens compõe leitura de CSV + parsing BR + validação
(tradefolio.validation) -- não deve retornar um dataframe sem antes
validar (AGENTS.md §14).
"""
from pathlib import Path

import pandas as pd
import pytest

from tradefolio.loaders import carregar_ordens, parse_valor_br

FIXTURE_MINI = Path(__file__).parent / "fixtures" / "mini_fixture_orders.csv"

CABECALHO = (
    "#;Data/Hora;Ativo;C/V;Quantidade;Preço limite;Status;Tipo;"
    "Quantidade executada;Preço médio;Resultado (Abs.);Resultado %;Resultado (R$)"
)


def test_parse_valor_br_converte_decimal_e_milhar():
    serie = pd.Series(["1.234,56", "-150,00", "0,00", "-"])
    resultado = parse_valor_br(serie)
    assert resultado.tolist()[:3] == [1234.56, -150.00, 0.00]
    assert pd.isna(resultado.iloc[3])


def test_carregar_ordens_le_fixture_mini_com_sucesso():
    ordens = carregar_ordens(FIXTURE_MINI)
    assert len(ordens) == 10
    assert ordens["dt"].is_monotonic_increasing
    assert ordens["Quantidade executada"].notna().all()
    # linhas de entrada nao tem Resultado (R$)
    entradas = ordens[ordens["Tipo"] == "entrada"]
    assert entradas["Resultado (R$)"].isna().all()
    saidas = ordens[ordens["Tipo"] == "saída"]
    assert saidas["Resultado (R$)"].notna().all()


def _escrever_csv(tmp_path: Path, linhas: list[str]) -> Path:
    caminho = tmp_path / "ordens.csv"
    caminho.write_text(CABECALHO + "\n" + "\n".join(linhas) + "\n", encoding="utf-8")
    return caminho


def test_carregar_ordens_propaga_erro_de_coluna_ausente(tmp_path):
    caminho = tmp_path / "ordens_sem_tipo.csv"
    caminho.write_text(
        "#;Data/Hora;Ativo;C/V;Quantidade;Preço limite;Status;"
        "Quantidade executada;Preço médio;Resultado (Abs.);Resultado %;Resultado (R$)\n"
        '1;02/01/2025 / 09:00:00;WINF25;C;2;140000;executada;2;140000;-;-;-\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="Tipo"):
        carregar_ordens(caminho)


def test_carregar_ordens_propaga_erro_de_valor_categorico_invalido(tmp_path):
    caminho = _escrever_csv(
        tmp_path,
        ['1;02/01/2025 / 09:00:00;WINF25;X;2;140000;executada;entrada;2;140000;-;-;-'],
    )
    with pytest.raises(ValueError, match="C/V"):
        carregar_ordens(caminho)


def test_carregar_ordens_propaga_erro_de_saida_sem_resultado(tmp_path):
    caminho = _escrever_csv(
        tmp_path,
        ['1;02/01/2025 / 09:05:00;WINF25;V;2;140100;executada;saída;2;140100;-;-;-'],
    )
    with pytest.raises(ValueError, match="saída"):
        carregar_ordens(caminho)
