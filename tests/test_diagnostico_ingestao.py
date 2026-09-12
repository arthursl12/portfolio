"""
RED: tradefolio.validation.diagnostico_ingestao ainda não existe (AGENTS.md
épico 1, tarefa 1.3 -- relatório agregado de diagnóstico).

O exemplo numérico do PDF-fonte ("3.699 linhas encontradas / 1.649 linhas
com resultado / 1.637 entradas / ...") é ilustrativo, não um fixture: só
"linhas encontradas" e "linhas com resultado realizado" batem exatamente
contra dados_exemplo/orders_roboraiz.csv quando computados aqui; entradas/
saídas/canceladas não batem em nenhuma definição testada (nem só
executadas, nem todas as linhas por Tipo) -- não faz sentido perseguir um
número de exemplo solto. Os valores abaixo foram computados e conferidos
por script antes deste teste contra os dois arquivos reais, com uma
definição própria e documentada: entradas/saídas contam só ordens
executadas (Status == "executada"); ordens não executadas (canceladas ou
expiradas) entram em uma categoria própria, não classificadas como
entrada/saída.
"""
from tradefolio.loaders import carregar_ordens
from tradefolio.validation import diagnostico_ingestao


def test_diagnostico_romanos():
    ordens = carregar_ordens("tests/fixtures/romanos_orders.csv")
    d = diagnostico_ingestao(ordens)
    assert d == {
        "linhas_encontradas": 1645,
        "linhas_com_resultado": 823,
        "entradas": 796,
        "saidas": 849,
        "ordens_nao_executadas": 0,
        "identificadores_duplicados": 0,
        "quantidades_inconsistentes": 0,
    }


def test_diagnostico_roboraiz():
    ordens = carregar_ordens("dados_exemplo/orders_roboraiz.csv")
    d = diagnostico_ingestao(ordens)
    assert d == {
        "linhas_encontradas": 3699,
        "linhas_com_resultado": 1649,
        "entradas": 1831,
        "saidas": 1654,
        "ordens_nao_executadas": 214,
        "identificadores_duplicados": 0,
        "quantidades_inconsistentes": 0,
    }
