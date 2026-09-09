"""CSV parsing for the Smarttbot order-export format.

Convention (CLAUDE.md > "CSV format (Smarttbot order export)"):
semicolon-delimited, comma decimal / dot thousands separator,
'dd/mm/yyyy / HH:MM:SS' timestamps. Validates (tradefolio.validation)
before returning -- never passes broken data through silently.
"""
import numpy as np
import pandas as pd

from tradefolio.validation import (
    validar_colunas,
    validar_ordens_parseadas,
    validar_valores_categoricos,
)


def parse_valor_br(s: pd.Series) -> pd.Series:
    """Converte string BR ('1.234,56' ou '-') para float."""
    s = s.astype(str).str.strip()
    s = s.replace({"-": np.nan, "nan": np.nan})
    s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    return pd.to_numeric(s, errors="coerce")


def carregar_ordens(csv_path) -> pd.DataFrame:
    df = pd.read_csv(csv_path, sep=";", quotechar='"', encoding="utf-8")
    validar_colunas(df)
    validar_valores_categoricos(df)

    df["dt"] = pd.to_datetime(df["Data/Hora"], format="%d/%m/%Y / %H:%M:%S", errors="coerce")
    df["data"] = df["dt"].dt.normalize()
    df["Resultado (R$)"] = parse_valor_br(df["Resultado (R$)"])
    df["Quantidade executada"] = pd.to_numeric(df["Quantidade executada"], errors="coerce")

    validar_ordens_parseadas(df)

    return df.sort_values("dt").reset_index(drop=True)
