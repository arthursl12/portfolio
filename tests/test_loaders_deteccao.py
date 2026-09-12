"""
RED: tradefolio.loaders ainda não trata BOM UTF-8 nem detecta o delimitador
(AGENTS.md épico 1, tarefa 1.1).

BOM: exportações do Excel/Windows frequentemente prefixam o arquivo com
EF BB BF (BOM UTF-8) -- sem tratamento, o BOM gruda no nome da primeira
coluna ("#" vira "﻿#"), quebrando validar_colunas silenciosamente
(a coluna pareceria ausente, não corrompida).

Delimitador: a convenção observada é sempre ';' (decimal já usa vírgula),
mas a tarefa pede detecção em vez de assumir -- `detectar_delimitador`
distingue ';' de ',' pela linha de cabeçalho, com fallback para ';' caso a
detecção seja inconclusiva (nunca falha silenciosamente para um separador
errado sem fallback documentado).
"""
from pathlib import Path

import pandas as pd

from tradefolio.loaders import carregar_ordens, detectar_delimitador

CABECALHO = (
    "#;Data/Hora;Ativo;C/V;Quantidade;Preço limite;Status;Tipo;"
    "Quantidade executada;Preço médio;Resultado (Abs.);Resultado %;Resultado (R$)"
)
LINHA = '1;02/01/2025 / 09:00:00;WINF25;C;2;140000;executada;entrada;2;140000;-;-;-'


def test_carregar_ordens_trata_bom_utf8(tmp_path):
    caminho = tmp_path / "com_bom.csv"
    caminho.write_bytes(("﻿" + CABECALHO + "\n" + LINHA + "\n").encode("utf-8"))
    ordens = carregar_ordens(caminho)
    assert len(ordens) == 1
    assert "#" in ordens.columns  # nao "﻿#"


def test_detectar_delimitador_ponto_e_virgula(tmp_path):
    caminho = tmp_path / "pv.csv"
    caminho.write_text(CABECALHO + "\n" + LINHA + "\n", encoding="utf-8")
    assert detectar_delimitador(caminho) == ";"


def test_detectar_delimitador_virgula(tmp_path):
    cabecalho_virgula = CABECALHO.replace(";", ",")
    linha_virgula = LINHA.replace(";", ",")
    caminho = tmp_path / "virgula.csv"
    caminho.write_text(cabecalho_virgula + "\n" + linha_virgula + "\n", encoding="utf-8")
    assert detectar_delimitador(caminho) == ","


def test_carregar_ordens_com_csv_separado_por_virgula(tmp_path):
    cabecalho_virgula = CABECALHO.replace(";", ",")
    linha_virgula = LINHA.replace(";", ",")
    caminho = tmp_path / "virgula.csv"
    caminho.write_text(cabecalho_virgula + "\n" + linha_virgula + "\n", encoding="utf-8")
    ordens = carregar_ordens(caminho)
    assert len(ordens) == 1
