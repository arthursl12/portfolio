"""CSV parsing for the Smarttbot order-export format.

Convention (CLAUDE.md > "CSV format (Smarttbot order export)"):
semicolon-delimited, comma decimal / dot thousands separator,
'dd/mm/yyyy / HH:MM:SS' timestamps. Validates (tradefolio.validation)
before returning -- never passes broken data through silently.
"""
import pandas as pd

from tradefolio.validation import (
    ErroValidacao,
    validar_colunas,
    validar_ordens_parseadas,
    validar_valores_categoricos,
)

_MARCADORES_VAZIO = frozenset({"-", "nan"})


def parse_valor_br(s: pd.Series) -> pd.Series:
    """Converte string BR ('1.234,56' ou '-') para float.

    Distingue um '-' legítimo (sem resultado) de uma string realmente
    corrompida (AGENTS.md épico 1, tarefa 1.3, INVALID_MONETARY_VALUE) --
    ambas viravam NaN silenciosamente antes desta checagem, indistinguíveis
    uma da outra.
    """
    bruto = s.astype(str).str.strip()
    vazio = bruto.isin(_MARCADORES_VAZIO)
    tratado = bruto.where(~vazio, other="")
    tratado = tratado.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    numerico = pd.to_numeric(tratado, errors="coerce")

    invalidos = numerico.isna() & ~vazio
    if invalidos.any():
        raise ErroValidacao(
            f"{int(invalidos.sum())} valor(es) monetário(s) não interpretável(is): "
            f"{sorted(bruto[invalidos].unique())}",
            codigo="INVALID_MONETARY_VALUE",
        )
    return numerico


def detectar_delimitador(csv_path) -> str:
    """Distingue ';' de ',' pela linha de cabeçalho (AGENTS.md épico 1,
    tarefa 1.1). Convenção observada é sempre ';' -- usado como fallback se
    a detecção for inconclusiva (nenhum candidato presente na linha)."""
    candidatos = (";", ",")
    if hasattr(csv_path, "read"):
        posicao = csv_path.tell()
        primeira_linha = csv_path.readline()
        csv_path.seek(posicao)
        if isinstance(primeira_linha, bytes):
            primeira_linha = primeira_linha.decode("utf-8-sig")
    else:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            primeira_linha = f.readline()

    contagens = {c: primeira_linha.count(c) for c in candidatos}
    delimitador = max(contagens, key=contagens.get)
    return delimitador if contagens[delimitador] > 0 else ";"


def carregar_ordens(csv_path) -> pd.DataFrame:
    delimitador = detectar_delimitador(csv_path)
    df = pd.read_csv(csv_path, sep=delimitador, quotechar='"', encoding="utf-8-sig")
    validar_colunas(df)
    validar_valores_categoricos(df)

    df["dt"] = pd.to_datetime(df["Data/Hora"], format="%d/%m/%Y / %H:%M:%S", errors="coerce")
    df["data"] = df["dt"].dt.normalize()
    df["Resultado (R$)"] = parse_valor_br(df["Resultado (R$)"])
    df["Quantidade executada"] = pd.to_numeric(df["Quantidade executada"], errors="coerce")

    validar_ordens_parseadas(df)

    return df.sort_values("dt").reset_index(drop=True)
