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

`report.py` é uma CLI (`argparse`), sem caminhos fixados no código. Modo
`robo` (um único robô):

```bash
.venv/bin/python report.py robo caminho/para/ordens.csv saida.html --minimum-margin 5000
```

`--minimum-margin` (margem mínima da posição, em R$) é obrigatório —
`AGENTS.md` §8 proíbe inventar um valor de convenção financeira, então não
há default. Há muitos outros parâmetros opcionais (Monte Carlo, cenário de
deterioração, custo mensal, janela de detecção multi-ativo, ...) —
`.venv/bin/python report.py robo --help` lista todos. Modo `portfolio`
(2+ robôs combinados) segue o mesmo padrão — `.venv/bin/python report.py
portfolio --help`. O caminho de saída é impresso no final (`Salvo em: ...`).

### Teste rápido com dados de exemplo

O repositório já traz CSVs reais de robôs em `dados_exemplo/` (e um em
`tests/fixtures/romanos_orders.csv`, usado pela suíte de testes), úteis para
ver o relatório funcionando sem precisar de dados próprios:

```bash
.venv/bin/python demo.py
```

Isso roda sobre `dados_exemplo/orders_romanos2.csv` e escreve
`orders_romanos2.html` na raiz do projeto (edite as constantes no topo de
`demo.py` para apontar para outro CSV) — abra o HTML no navegador.

## Página ao vivo (Streamlit)

`app.py` é uma versão interativa: envie um CSV ou escolha um robô de
`dados_exemplo/`, filtre por janela de tempo (1 semana até 2 anos, ou desde o
início — cada janela é recalculada do zero, não é um recorte da curva
acumulada) e simule quantos contratos você operaria (as métricas em R$ e o
gráfico escalam linearmente; retorno %, drawdown %, Sharpe/Sortino/Calmar
não mudam com o número de contratos — são invariantes por construção).

```bash
.venv/bin/streamlit run app.py
```

Abre em `http://localhost:8501`. Só mostra métricas de nível diário (página 1
e a distribuição da página 3) — nesta primeira versão, deliberadamente sem a
página de trades (página 2), porque filtrar as ordens pela mesma janela
poderia cortar um trade no meio e corromper a reconstrução de posição.

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
- `demo.py` — roda `report.py` sobre `tests/fixtures/romanos_orders.csv`,
  sem precisar de dados próprios.
- `app.py` — página Streamlit ao vivo (upload/exemplo, filtro de janela,
  simulação de contratos). Ver "Página ao vivo" acima.
- `dados_exemplo/` — CSVs de exemplo para a página Streamlit (separado de
  `tests/fixtures/`, que é para os testes).
- `sheet.py` — implementação original de referência (pré-`tradefolio/`);
  não é mais o caminho usado por `report.py`.
- `tests/` — suíte pytest, incluindo `tests/fixtures/` (dados de exemplo e
  valores esperados calculados à mão ou conferidos contra o relatório
  nativo da Smarttbot).
- `AGENTS.md` — workflow obrigatório para mudanças neste repositório
  (TDD, convenções financeiras, etc.).
