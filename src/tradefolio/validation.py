"""Input validation for the Smarttbot order-export CSV.

AGENTS.md §14: validate before analysis, prefer explicit errors over
silent repair. Covers the risks sheet.py's original parsing didn't check:
an unknown 'C/V' or 'Tipo' value would have been silently treated as
whichever branch an if/else happened to fall into.
"""
import warnings

import pandas as pd

COLUNAS_OBRIGATORIAS = ("Data/Hora", "C/V", "Tipo", "Quantidade executada", "Resultado (R$)")
TIPOS_VALIDOS = frozenset({"entrada", "saída"})
LADOS_VALIDOS = frozenset({"C", "V"})


def validar_colunas(df: pd.DataFrame) -> None:
    faltantes = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if faltantes:
        raise ValueError(f"colunas obrigatórias ausentes: {faltantes}")


def validar_valores_categoricos(df: pd.DataFrame) -> None:
    tipos_invalidos = set(df["Tipo"].unique()) - TIPOS_VALIDOS
    if tipos_invalidos:
        raise ValueError(f"valores inválidos na coluna 'Tipo': {sorted(tipos_invalidos)}")

    lados_invalidos = set(df["C/V"].unique()) - LADOS_VALIDOS
    if lados_invalidos:
        raise ValueError(f"valores inválidos na coluna 'C/V': {sorted(lados_invalidos)}")


def validar_ordens_parseadas(df: pd.DataFrame) -> None:
    """Valida o dataframe já com 'dt', 'Quantidade executada' e
    'Resultado (R$)' convertidos para os tipos finais."""
    if df["dt"].isna().any():
        n = int(df["dt"].isna().sum())
        raise ValueError(f"{n} linha(s) com 'Data/Hora' que não pôde ser interpretada")

    qtd = df["Quantidade executada"]
    if qtd.isna().any():
        raise ValueError("'Quantidade executada' não numérica em uma ou mais linhas")
    if (qtd <= 0).any():
        raise ValueError("'Quantidade executada' deve ser positiva em todas as linhas")

    saidas_sem_resultado = df[(df["Tipo"] == "saída") & df["Resultado (R$)"].isna()]
    if len(saidas_sem_resultado):
        # Não é necessariamente um erro: observado em dados reais (Smarttbot,
        # robô Romanos) que o fechamento forçado de fim de pregão pode gerar
        # uma linha "saída" que na verdade reabre posição no mesmo instante
        # (sempre às 17:39:00 nessa amostra) e por isso não carrega
        # resultado. tradefolio.trades.reconstruir_trades já trata isso
        # corretamente (rastreia posição líquida, ignora resultado ausente),
        # então isso é aviso, não erro (AGENTS.md §14: aviso explícito para
        # dado incerto porém processável).
        warnings.warn(
            f"{len(saidas_sem_resultado)} linha(s) de 'saída' sem 'Resultado (R$)' "
            "(comum em fechamentos forçados de fim de pregão) -- processando mesmo assim",
            stacklevel=2,
        )

    if "#" in df.columns and df["#"].duplicated().any():
        duplicados = sorted(df.loc[df["#"].duplicated(keep=False), "#"].unique())
        raise ValueError(f"ids de ordem duplicados na coluna '#': {duplicados}")
