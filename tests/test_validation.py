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
import warnings

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
            "Ativo": ["WINF25", "WINF25"],
            "C/V": ["C", "V"],
            "Tipo": ["entrada", "saída"],
            "Status": ["executada", "executada"],
            "Quantidade": [2, 2],
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


def test_validar_colunas_rejeita_status_ausente():
    df = _ordens_validas().drop(columns=["Status"])
    with pytest.raises(ValueError, match="Status"):
        validar_colunas(df)


def test_validar_valores_categoricos_avisa_status_desconhecido():
    # AGENTS.md épico 1, tarefa 1.1/1.3: valores reais observados são
    # "executada", "cancelada", "expirada" (dados_exemplo/orders_roboraiz.csv).
    # Um valor fora desse conjunto é aviso, não erro -- a plataforma pode
    # introduzir um status novo e legítimo (ex. "parcial") sem que isso deva
    # bloquear o carregamento (AGENTS.md §14: aviso para dado incerto porém
    # processável).
    df = _ordens_validas()
    df.loc[0, "Status"] = "pendente"
    with pytest.warns(UserWarning, match="Status"):
        validar_valores_categoricos(df)  # nao deve levantar


def test_codigo_diagnostico_status_desconhecido_e_unknown_status():
    df = _ordens_validas()
    df.loc[0, "Status"] = "pendente"
    with pytest.warns(UserWarning) as record:
        validar_valores_categoricos(df)
    assert record[0].message.codigo == "UNKNOWN_STATUS"


def test_validar_ordens_parseadas_aceita_quantidade_zero_para_ordem_nao_executada():
    # ordem cancelada/expirada legitimamente nao tem quantidade executada
    # (dados_exemplo/orders_roboraiz.csv: 213 canceladas + 1 expirada, todas
    # com Quantidade executada == 0) -- nao e dado corrompido.
    df = _parseadas(_ordens_validas())
    df.loc[0, "Status"] = "cancelada"
    df.loc[0, "Quantidade executada"] = 0
    validar_ordens_parseadas(df)  # nao deve levantar


def test_validar_ordens_parseadas_rejeita_quantidade_zero_para_ordem_executada():
    df = _parseadas(_ordens_validas())
    df.loc[0, "Quantidade executada"] = 0  # Status continua "executada"
    with pytest.raises(ValueError, match="Quantidade executada"):
        validar_ordens_parseadas(df)


def test_validar_ordens_parseadas_rejeita_quantidade_negativa_mesmo_cancelada():
    df = _parseadas(_ordens_validas())
    df.loc[0, "Status"] = "cancelada"
    df.loc[0, "Quantidade executada"] = -1
    with pytest.raises(ValueError, match="Quantidade executada"):
        validar_ordens_parseadas(df)


def test_validar_valores_categoricos_avisa_ativo_desconhecido():
    # AGENTS.md épico 1, tarefa 1.3. Raízes conhecidas confirmadas nos dados
    # reais (todos os CSVs em dados_exemplo/ + tests/fixtures/): WIN, WDO.
    df = _ordens_validas()
    df.loc[0, "Ativo"] = "BOVA26"
    with pytest.warns(UserWarning, match="Ativo"):
        validar_valores_categoricos(df)  # nao deve levantar


def test_codigo_diagnostico_ativo_desconhecido_e_unknown_asset():
    df = _ordens_validas()
    df.loc[0, "Ativo"] = "BOVA26"
    with pytest.warns(UserWarning) as record:
        validar_valores_categoricos(df)
    assert record[0].message.codigo == "UNKNOWN_ASSET"


def test_validar_ordens_parseadas_avisa_quantidade_diferente_de_executada():
    # descoberto em dados_exemplo/orders_roboraiz.csv: toda ordem com
    # Quantidade != Quantidade executada la e cancelada/expirada (Status !=
    # executada) -- nesse caso e esperado, nao um aviso. Para uma ordem
    # EXECUTADA, quantidade solicitada != executada indica fill parcial,
    # que a tarefa pede para sinalizar (nao ha exemplo real ainda, mas o
    # dado ja tem as duas colunas para isso).
    df = _parseadas(_ordens_validas())
    df["Quantidade"] = [2, 3]  # linha 1 (saida, executada): pediu 3, executou 2
    with pytest.warns(UserWarning, match="[Qq]uantidade"):
        validar_ordens_parseadas(df)


def test_codigo_diagnostico_quantidade_diferente_e_quantity_mismatch():
    df = _parseadas(_ordens_validas())
    df["Quantidade"] = [2, 3]
    with pytest.warns(UserWarning) as record:
        validar_ordens_parseadas(df)
    codigos = [r.message.codigo for r in record]
    assert "QUANTITY_MISMATCH" in codigos


def test_quantidade_diferente_em_ordem_cancelada_nao_avisa_quantity_mismatch():
    df = _parseadas(_ordens_validas())
    df.loc[0, "Status"] = "cancelada"
    df.loc[0, "Quantidade executada"] = 0
    df["Quantidade"] = [3, 2]  # linha 0 (cancelada): pediu 3, executou 0 -- esperado
    with warnings.catch_warnings(record=True) as record:
        warnings.simplefilter("always")
        validar_ordens_parseadas(df)
    codigos = [w.message.codigo for w in record if hasattr(w.message, "codigo")]
    assert "QUANTITY_MISMATCH" not in codigos


def test_validar_ordens_parseadas_avisa_mas_nao_rejeita_saida_sem_resultado():
    # Descoberto ao rodar contra tests/fixtures/romanos_orders.csv: 26
    # linhas "saida" reais (fechamento forcado de fim de pregao, sempre
    # 17:39:00) nao tem Resultado (R$) -- e um padrao real da plataforma,
    # nao dado corrompido, e tradefolio.trades.reconstruir_trades ja lida
    # com isso corretamente. Deve avisar, nao levantar (AGENTS.md §14).
    df = _parseadas(_ordens_validas())
    df.loc[1, "Resultado (R$)"] = math.nan  # linha 1 e "saida"
    with pytest.warns(UserWarning, match="saída"):
        validar_ordens_parseadas(df)  # nao deve levantar


def test_validar_ordens_parseadas_rejeita_id_duplicado():
    df = _parseadas(_ordens_validas())
    df.loc[1, "#"] = 1  # duplica o id da linha 0
    with pytest.raises(ValueError, match="#"):
        validar_ordens_parseadas(df)


def test_codigo_diagnostico_data_nao_interpretavel_e_invalid_date():
    # AGENTS.md épico 1, tarefa 1.3 (códigos determinísticos de diagnóstico)
    df = _ordens_validas()
    df.loc[0, "Data/Hora"] = "data invalida"
    with pytest.raises(ValueError) as exc_info:
        validar_ordens_parseadas(_parseadas(df))
    assert exc_info.value.codigo == "INVALID_DATE"


def test_codigo_diagnostico_id_duplicado_e_duplicate_order():
    df = _parseadas(_ordens_validas())
    df.loc[1, "#"] = 1
    with pytest.raises(ValueError) as exc_info:
        validar_ordens_parseadas(df)
    assert exc_info.value.codigo == "DUPLICATE_ORDER"


def test_codigo_diagnostico_saida_sem_resultado_e_exit_without_pnl():
    df = _parseadas(_ordens_validas())
    df.loc[1, "Resultado (R$)"] = math.nan
    with pytest.warns(UserWarning) as record:
        validar_ordens_parseadas(df)
    assert record[0].message.codigo == "EXIT_WITHOUT_PNL"


def test_codigo_diagnostico_ausente_fica_none_quando_sem_mapeamento_limpo():
    # colunas ausentes, Tipo/C-V desconhecidos e quantidade inválida não têm
    # correspondência limpa no vocabulário de códigos da lâmina -- ficam
    # codigo=None em vez de um código forçado/inventado.
    df = _ordens_validas().drop(columns=["Tipo"])
    with pytest.raises(ValueError) as exc_info:
        validar_colunas(df)
    assert exc_info.value.codigo is None
