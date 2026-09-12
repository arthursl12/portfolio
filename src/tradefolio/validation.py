"""Input validation for the Smarttbot order-export CSV.

AGENTS.md §14: validate before analysis, prefer explicit errors over
silent repair. Covers the risks sheet.py's original parsing didn't check:
an unknown 'C/V' or 'Tipo' value would have been silently treated as
whichever branch an if/else happened to fall into.

Diagnostic codes (AGENTS.md épico 1, tarefa 1.3): `ErroValidacao`/
`AvisoValidacao` carry an optional `.codigo` matching the lâmina's
deterministic diagnostic vocabulary (DUPLICATE_ORDER, INVALID_DATE,
EXIT_WITHOUT_PNL, UNKNOWN_STATUS, ...). Only checks with a genuine,
unambiguous match get one. Checks without a clean match keep `codigo=None`
rather than force one (AGENTS.md §8: never invent a convention silently).

`Status` (separate from `Tipo`): observed real values are "executada",
"cancelada", "expirada" (dados_exemplo/orders_roboraiz.csv has 213
cancelada + 1 expirada, all with Quantidade executada == 0). An earlier
version of this docstring claimed the CSV format had no such field --
wrong; it does, and an unrecognized value is a warning (UNKNOWN_STATUS),
not an error, since the platform may introduce a new legitimate status.
"""
import warnings

import pandas as pd


class ErroValidacao(ValueError):
    def __init__(self, mensagem: str, codigo: str | None = None):
        super().__init__(mensagem)
        self.codigo = codigo


class AvisoValidacao(UserWarning):
    def __init__(self, mensagem: str, codigo: str | None = None):
        super().__init__(mensagem)
        self.codigo = codigo


COLUNAS_OBRIGATORIAS = (
    "Data/Hora", "Ativo", "C/V", "Tipo", "Status",
    "Quantidade", "Quantidade executada", "Resultado (R$)",
)
TIPOS_VALIDOS = frozenset({"entrada", "saída"})
LADOS_VALIDOS = frozenset({"C", "V"})
STATUS_EXECUTADA = "executada"
STATUS_CONHECIDOS = frozenset({STATUS_EXECUTADA, "cancelada", "expirada"})

# Raízes de contrato futuro B3 confirmadas nos dados reais analisados nesta
# sessão (todos os CSVs em dados_exemplo/ + tests/fixtures/): WIN (mini
# Ibovespa) e WDO (mini dólar). Um código de ativo é ROOT + letra do mês +
# 2 dígitos do ano (ex. "WINV26" -> raiz "WIN"), convenção B3 padrão.
RAIZES_CONHECIDAS = frozenset({"WIN", "WDO"})


def extrair_raiz_ativo(ativo: str) -> str:
    """Raiz do código de contrato futuro B3 (ex. "WINV26" -> "WIN"):
    tudo exceto os últimos 3 caracteres (letra do mês + 2 dígitos do ano)."""
    return ativo[:-3]


def validar_colunas(df: pd.DataFrame) -> None:
    faltantes = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if faltantes:
        raise ErroValidacao(f"colunas obrigatórias ausentes: {faltantes}")


def validar_valores_categoricos(df: pd.DataFrame) -> None:
    tipos_invalidos = set(df["Tipo"].unique()) - TIPOS_VALIDOS
    if tipos_invalidos:
        raise ErroValidacao(f"valores inválidos na coluna 'Tipo': {sorted(tipos_invalidos)}")

    lados_invalidos = set(df["C/V"].unique()) - LADOS_VALIDOS
    if lados_invalidos:
        raise ErroValidacao(f"valores inválidos na coluna 'C/V': {sorted(lados_invalidos)}")

    status_desconhecidos = set(df["Status"].unique()) - STATUS_CONHECIDOS
    if status_desconhecidos:
        warnings.warn(
            AvisoValidacao(
                f"valor(es) desconhecido(s) na coluna 'Status': {sorted(status_desconhecidos)} "
                f"(conhecidos: {sorted(STATUS_CONHECIDOS)}) -- processando mesmo assim",
                codigo="UNKNOWN_STATUS",
            ),
            stacklevel=2,
        )

    raizes_desconhecidas = {extrair_raiz_ativo(a) for a in df["Ativo"].unique()} - RAIZES_CONHECIDAS
    if raizes_desconhecidas:
        warnings.warn(
            AvisoValidacao(
                f"raiz(es) de 'Ativo' desconhecida(s): {sorted(raizes_desconhecidas)} "
                f"(conhecidas: {sorted(RAIZES_CONHECIDAS)}) -- processando mesmo assim",
                codigo="UNKNOWN_ASSET",
            ),
            stacklevel=2,
        )


def validar_ordens_parseadas(df: pd.DataFrame) -> None:
    """Valida o dataframe já com 'dt', 'Quantidade executada' e
    'Resultado (R$)' convertidos para os tipos finais."""
    if df["dt"].isna().any():
        n = int(df["dt"].isna().sum())
        raise ErroValidacao(
            f"{n} linha(s) com 'Data/Hora' que não pôde ser interpretada", codigo="INVALID_DATE"
        )

    qtd = df["Quantidade executada"]
    if qtd.isna().any():
        raise ErroValidacao("'Quantidade executada' não numérica em uma ou mais linhas")
    if (qtd < 0).any():
        raise ErroValidacao("'Quantidade executada' não pode ser negativa")
    executada = df["Status"] == STATUS_EXECUTADA
    if ((qtd <= 0) & executada).any():
        raise ErroValidacao(
            "'Quantidade executada' deve ser positiva em toda ordem com Status='executada' "
            "(quantidade zero é esperada para ordens canceladas/expiradas)"
        )

    mismatch = df[(df["Status"] == STATUS_EXECUTADA) & (df["Quantidade"] != df["Quantidade executada"])]
    if len(mismatch):
        # Só para ordens executadas: quantidade solicitada != executada
        # ali indica fill parcial. Para ordens canceladas/expiradas isso é
        # esperado (Quantidade executada sempre 0) e não é sinalizado.
        warnings.warn(
            AvisoValidacao(
                f"{len(mismatch)} ordem(ns) executada(s) com quantidade solicitada "
                "diferente da executada (fill parcial) -- processando mesmo assim",
                codigo="QUANTITY_MISMATCH",
            ),
            stacklevel=2,
        )

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
            AvisoValidacao(
                f"{len(saidas_sem_resultado)} linha(s) de 'saída' sem 'Resultado (R$)' "
                "(comum em fechamentos forçados de fim de pregão) -- processando mesmo assim",
                codigo="EXIT_WITHOUT_PNL",
            ),
            stacklevel=2,
        )

    if "#" in df.columns and df["#"].duplicated().any():
        duplicados = sorted(df.loc[df["#"].duplicated(keep=False), "#"].unique())
        raise ErroValidacao(
            f"ids de ordem duplicados na coluna '#': {duplicados}", codigo="DUPLICATE_ORDER"
        )


def diagnostico_ingestao(ordens: pd.DataFrame) -> dict:
    """Resumo agregado de ingestão (AGENTS.md épico 1, tarefa 1.3). Recebe
    o dataframe já carregado por tradefolio.loaders.carregar_ordens (já
    validado). Entradas/saídas contam só ordens executadas -- uma ordem
    cancelada/expirada não é nem uma coisa nem outra, entra em
    `ordens_nao_executadas`."""
    executadas = ordens[ordens["Status"] == STATUS_EXECUTADA]
    saidas_executadas = executadas[executadas["Tipo"] == "saída"]

    return {
        "linhas_encontradas": len(ordens),
        "linhas_com_resultado": int(saidas_executadas["Resultado (R$)"].notna().sum()),
        "entradas": int((executadas["Tipo"] == "entrada").sum()),
        "saidas": len(saidas_executadas),
        "ordens_nao_executadas": len(ordens) - len(executadas),
        "identificadores_duplicados": int(ordens["#"].duplicated().sum()) if "#" in ordens.columns else 0,
        "quantidades_inconsistentes": int(
            (executadas["Quantidade"] != executadas["Quantidade executada"]).sum()
        ),
    }
