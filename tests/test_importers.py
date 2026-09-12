"""
RED: tradefolio.importers ainda não existe (AGENTS.md épico 1, tarefa 1.2
"perfis de importação").

Escopo desta fatia: só a interface comum `OrderImporter`
(`can_parse`/`parse`/`diagnostics`) e a implementação Smarttbot que
envolve o que já existe (`loaders.carregar_ordens`,
`validation.diagnostico_ingestao`) -- não reescreve nem duplica lógica de
parsing. Deliberadamente FORA desta fatia (não inventados): um
"importador genérico de CSV" e um "formato manual padronizado" (a própria
tarefa 1.2 os pede como itens separados, e nenhum formato concreto foi
especificado -- inventar um agora seria adivinhar um formato que não
existe) e o critério de aceite "reimportar não duplica" (exige uma noção
de "já importado antes" entre execuções, que é o próprio Épico 1.4 --
persistência -- ainda sem decisão de tecnologia).

`can_parse` reusa a mesma leitura de primeira linha que
`loaders.detectar_delimitador` já fazia (extraída para não duplicar) e
checa se as colunas obrigatórias da Smarttbot aparecem no cabeçalho --
não tenta ler o arquivo inteiro nem validar o conteúdo (isso é `parse`).
"""
from pathlib import Path

import pandas as pd
import pytest

from tradefolio.importers import OrderImporter, SmarttbotOrderImporter
from tradefolio.loaders import carregar_ordens
from tradefolio.validation import diagnostico_ingestao

FIXTURE = Path(__file__).parent / "fixtures" / "mini_fixture_orders.csv"


def test_order_importer_e_abstrata_nao_pode_instanciar_direto():
    with pytest.raises(TypeError):
        OrderImporter()


def test_subclasse_incompleta_nao_pode_instanciar():
    class Incompleta(OrderImporter):
        def can_parse(self, csv_path) -> bool:
            return True

    with pytest.raises(TypeError):
        Incompleta()


def test_smarttbot_importer_can_parse_fixture_real():
    assert SmarttbotOrderImporter().can_parse(FIXTURE) is True


def test_smarttbot_importer_can_parse_recusa_csv_sem_colunas_obrigatorias(tmp_path):
    caminho = tmp_path / "outro_formato.csv"
    caminho.write_text("data,ticker,valor\n2025-01-01,PETR4,10.5\n", encoding="utf-8")
    assert SmarttbotOrderImporter().can_parse(caminho) is False


def test_smarttbot_importer_can_parse_arquivo_inexistente_retorna_false(tmp_path):
    assert SmarttbotOrderImporter().can_parse(tmp_path / "nao_existe.csv") is False


def test_smarttbot_importer_parse_igual_a_carregar_ordens():
    esperado = carregar_ordens(FIXTURE)
    obtido = SmarttbotOrderImporter().parse(FIXTURE)
    pd.testing.assert_frame_equal(obtido, esperado)


def test_smarttbot_importer_diagnostics_igual_a_diagnostico_ingestao():
    ordens = carregar_ordens(FIXTURE)
    esperado = diagnostico_ingestao(ordens)
    obtido = SmarttbotOrderImporter().diagnostics(ordens)
    assert obtido == esperado
