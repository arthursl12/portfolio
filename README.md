# Lâmina de Robô

Analisa o histórico de ordens de um robô de trading (exportado da plataforma
Smarttbot) e gera um relatório HTML de uma página ("lâmina") com métricas de
performance, curva de capital/drawdown e distribuição de resultados.

## Setup

Requer Python 3. Crie um ambiente virtual e instale as dependências:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install -e .
```

(`requirements-dev.txt` inclui `requirements.txt` — pandas, numpy, matplotlib,
pandas_market_calendars — mais pytest para rodar os testes. O `pip install -e .`
deixa o pacote `tradefolio` em `src/` importável de qualquer lugar do
projeto — sem ele, `import tradefolio` só funciona dentro do pytest.)

## Gerando um relatório

`report.py` lê um CSV de ordens (formato Smarttbot: `;`-separado, decimal com
vírgula, colunas como `Data/Hora`, `C/V`, `Tipo`, `Resultado (R$)`) e escreve
um HTML autocontido (gráficos embutidos em base64).

O caminho de entrada e o de saída estão fixados no topo/final de `report.py`:

```python
CSV_PATH = "/mnt/user-data/uploads/orders_romanos.csv"   # linha ~19
...
out_path = "/mnt/user-data/outputs/lamina_romanos_pagina1.html"  # dentro do __main__
```

Para gerar um relatório com os seus próprios dados, edite essas duas linhas
apontando para o seu CSV de ordens e para onde você quer o HTML, depois rode:

```bash
.venv/bin/python report.py
```

O caminho de saída será impresso no final (`Salvo em: ...`).

### Teste rápido com dados de exemplo

O repositório já traz um CSV real (robô "Romanos") em
`tests/fixtures/romanos_orders.csv`, útil para ver o relatório funcionando
sem precisar de dados próprios:

```bash
.venv/bin/python -c "
import report
diario = report.montar_dataframe_diario('tests/fixtures/romanos_orders.csv')
metricas, equity, drawdown = report.calcular_metricas_pagina1(diario)
grafico_b64 = report.gerar_grafico_curva_drawdown(equity, drawdown)

ordens = report.carregar_ordens('tests/fixtures/romanos_orders.csv')
p2 = report.calcular_metricas_pagina2(diario, ordens)
metricas.update({
    'n_trades_reconstruidos': p2['n_trades'],
    'win_rate_trades': p2['win_rate_trades'],
    'profit_factor_trades': p2['profit_factor_trades'],
    'lucro_medio_trade': p2['lucro_medio_trade'],
    'prejuizo_medio_trade': p2['prejuizo_medio_trade'],
})
secao_pagina2 = report.gerar_secao_pagina2(p2)

p3 = report.calcular_metricas_pagina3(diario)
grafico_dist_b64 = report.gerar_grafico_distribuicao(p3)
secao_pagina3 = report.gerar_secao_pagina3(p3)

html = report.gerar_html(metricas, grafico_b64, grafico_dist_b64, secao_pagina2, secao_pagina3)
with open('lamina_exemplo.html', 'w', encoding='utf-8') as f:
    f.write(html)
print('Salvo em: lamina_exemplo.html')
"
```

Isso escreve `lamina_exemplo.html` na raiz do projeto — abra no navegador.

## Rodando os testes

```bash
.venv/bin/python -m pytest
```

## Estrutura

- `src/tradefolio/` — biblioteca de cálculo (validação, custos, alinhamento
  de calendário, reconstrução de trades, métricas, drawdown, orquestração).
  Ver `CLAUDE.md` para a arquitetura completa e as convenções de domínio.
- `report.py` — renderização do HTML/gráficos a partir dos dicts produzidos
  por `tradefolio.report_data`.
- `sheet.py` — implementação original de referência (pré-`tradefolio/`);
  não é mais o caminho usado por `report.py`.
- `tests/` — suíte pytest, incluindo `tests/fixtures/` (dados de exemplo e
  valores esperados calculados à mão ou conferidos contra o relatório
  nativo da Smarttbot).
- `AGENTS.md` — workflow obrigatório para mudanças neste repositório
  (TDD, convenções financeiras, etc.).
