"""
RED: tradefolio.validation ainda não existe.

Convenção (AGENTS.md §14 "Data validation": validar antes de analisar,
preferir erros explícitos a reparo silencioso). Cobre exatamente os
riscos que o parsing de sheet.py não verificava: coluna ausente, valor
categórico desconhecido em C/V ou Tipo (usado como sinal +1/-1 e para
decidir se conta 'Resultado (R$)' -- um valor inesperado seria tratado
silenciosamente como o caso "else"), data não interpretável, quantidade
não numérica ou não positiva, linha de saída sem resultado, e id de
ordem duplicado.
"""
import math

import pandas as pd
import pytest

from tradefolio.validation import (
    validar_colunas,
    validar_ordens_parseadas,
    validar_valores_categoricos,
)


def _ordens_validas() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "#": [1, 2],
            "Data/Hora": ["02/01/2025 / 09:00:00", "02/01/2025 / 09:05:00"],
            "C/V": ["C", "V"],
            "Tipo": ["entrada", "saída"],
            "Quantidade executada": [2, 2],
            "Resultado (R$)": [math.nan, 200.0],
        }
    )


def _parseadas(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["dt"] = pd.to_datetime(df["Data/Hora"], format="%d/%m/%Y / %H:%M:%S", errors="coerce")
    return df


def test_validar_colunas_aceita_dataframe_completo():
    validar_colunas(_ordens_validas())  # nao deve levantar


def test_validar_colunas_rejeita_coluna_ausente():
    df = _ordens_validas().drop(columns=["Tipo"])
    with pytest.raises(ValueError, match="Tipo"):
        validar_colunas(df)


def test_validar_valores_categoricos_aceita_valores_conhecidos():
    validar_valores_categoricos(_ordens_validas())  # nao deve levantar


def test_validar_valores_categoricos_rejeita_tipo_desconhecido():
    df = _ordens_validas()
    df.loc[0, "Tipo"] = "cancelada"
    with pytest.raises(ValueError, match="Tipo"):
        validar_valores_categoricos(df)


def test_validar_valores_categoricos_rejeita_lado_desconhecido():
    df = _ordens_validas()
    df.loc[0, "C/V"] = "X"
    with pytest.raises(ValueError, match="C/V"):
        validar_valores_categoricos(df)


def test_validar_ordens_parseadas_aceita_dataframe_valido():
    validar_ordens_parseadas(_parseadas(_ordens_validas()))  # nao deve levantar


def test_validar_ordens_parseadas_rejeita_data_nao_interpretavel():
    df = _ordens_validas()
    df.loc[0, "Data/Hora"] = "data invalida"
    with pytest.raises(ValueError, match="Data/Hora"):
        validar_ordens_parseadas(_parseadas(df))


def test_validar_ordens_parseadas_rejeita_quantidade_nao_numerica():
    # validar_ordens_parseadas roda depois do pd.to_numeric(errors="coerce")
    # de tradefolio.loaders -- um valor nao numerico ja chega aqui como NaN.
    df = _parseadas(_ordens_validas())
    df["Quantidade executada"] = df["Quantidade executada"].astype(float)
    df.loc[0, "Quantidade executada"] = math.nan
    with pytest.raises(ValueError, match="Quantidade executada"):
        validar_ordens_parseadas(df)


def test_validar_ordens_parseadas_rejeita_quantidade_nao_positiva():
    df = _parseadas(_ordens_validas())
    df.loc[0, "Quantidade executada"] = 0
    with pytest.raises(ValueError, match="Quantidade executada"):
        validar_ordens_parseadas(df)


def test_validar_ordens_parseadas_rejeita_saida_sem_resultado():
    df = _parseadas(_ordens_validas())
    df.loc[1, "Resultado (R$)"] = math.nan  # linha 1 e "saida"
    with pytest.raises(ValueError, match="saída"):
        validar_ordens_parseadas(df)


def test_validar_ordens_parseadas_rejeita_id_duplicado():
    df = _parseadas(_ordens_validas())
    df.loc[1, "#"] = 1  # duplica o id da linha 0
    with pytest.raises(ValueError, match="#"):
        validar_ordens_parseadas(df)
