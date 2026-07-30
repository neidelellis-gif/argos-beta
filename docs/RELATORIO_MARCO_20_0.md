# RELATÓRIO DE IMPLEMENTAÇÃO — MARCO 20.0 — REAL PORTFOLIO INPUT INTEGRATION

## Resumo executivo

O Marco 20.0 está bloqueado por uma incompatibilidade entre a fonte canônica e o
contrato atualmente exposto ao frontend. As posições validadas são mantidas
somente na sessão do backend. O backend remove `positions` da resposta de
importação antes de serializá-la, e o dashboard público contém apenas métricas
agregadas. Portanto, o frontend não tem acesso às posições canônicas necessárias
para construir um `DailyApiRequest` real.

Conforme a regra expressa do marco para incompatibilidades reais, a implementação
foi interrompida antes de alterar o backend. Criar o construtor ou integrar a
chamada neste estado produziria código sem uma fonte canônica, ou exigiria reler
arquivos e duplicar a pipeline, ambas alternativas proibidas.

## Estado canônico identificado

- A importação oficial retorna internamente uma tupla de `PortfolioPosition`.
- A sessão canônica fica em `SESSION_PORTFOLIOS[session_id]["positions"]` no
  backend.
- Importações subsequentes preservam instituições não reimportadas e substituem
  somente as posições da instituição reimportada.
- O dashboard operacional é calculado a partir dessa mesma tupla, mas não a
  inclui no payload público.

## Fluxo atual de importação e validação

1. O frontend envia os arquivos para `POST /api/portfolios/import`.
2. O backend seleciona o conector reconhecido e carrega `PortfolioPosition`.
3. Diagnósticos existentes são executados por instituição.
4. As posições validadas são gravadas em `SESSION_PORTFOLIOS`.
5. `build_dashboard()` recebe as posições, consolida diagnósticos e devolve
   somente dados agregados.
6. Antes da resposta HTTP, `result.pop("positions")` retira as posições
   canônicas do resultado da importação.
7. O frontend recebe `dashboard`, `files` e `diagnostics`, mas nenhuma coleção
   canônica de posições.

`importedPortfolioPositions`, em `frontend/app.js`, não é essa fonte: ela contém
somente uma prévia TipRanks criada antes da importação oficial e não pode ser
usada pela experiência diária.

## Incompatibilidade com o contrato HTTP diário

O `DailyHttpAdapter` exige exatamente os 15 campos públicos de cada posição:

`institution`, `owner`, `account`, `asset_class`, `asset_subclass`, `asset_name`,
`identifier`, `identifier_type`, `quantity`, `unit_price`, `market_value`,
`currency`, `portfolio_weight`, `reference_date` e `source_file`.

Os payloads públicos do dashboard possuem apenas contagens, moedas, totais e
avisos por instituição. Não é possível reconstruir os 15 campos a partir desses
agregados, nem preservar proprietário, conta, identificador, precisão decimal,
data ou arquivo de origem.

## Arquivos criados e alterados

- Criado somente este relatório.
- Nenhum arquivo de frontend foi alterado.
- Nenhum arquivo de backend foi alterado.
- `frontend/daily_request_builder.js` não foi criado, pois não teria uma entrada
  canônica disponível.

## Itens de implementação não iniciados

Sem acesso frontend às posições canônicas, não foi possível implementar com
integridade:

- o mapeamento completo no `DailyRequestBuilder`;
- a preservação de decimais, proprietário e instituição no request real;
- o fingerprint determinístico da carteira;
- a recarga diária após importação válida;
- os testes de importação válida, inválida, repetição e alteração de carteira.

O comportamento existente sem carteira permanece inalterado: a chamada diária
continua usando `positions: []`, `fact_candidates: []` e `reference_date: null`.
Importações válidas e inválidas também preservam integralmente o comportamento
atual, sem uma integração parcial ou divergente.

## Mudança mínima necessária para desbloqueio

É necessária uma decisão de contrato/backend que disponibilize, de forma segura,
as posições canônicas da sessão ao frontend — na resposta de importação e na
carga inicial do dashboard, ou por um endpoint dedicado. A serialização deve
preservar os 15 campos aceitos pelo `DailyHttpAdapter`, especialmente os decimais
como texto, sem expor dados adicionais.

Após essa decisão, o frontend poderá manter como fonte única a coleção recebida
do backend, criar o `DailyRequestBuilder` puro e atualizar a experiência diária
com fingerprint em memória. Não é aceitável usar a prévia TipRanks, interpretar
novamente CSV/XLS/XLSX ou reconstruir posições a partir dos agregados.

## Compatibilidade, riscos e limitações

- Marcos 10–19 permanecem intactos porque não houve mudança funcional.
- O contrato público 1.0, o cockpit, CSS, motores e validações permanecem
  inalterados.
- O risco evitado é enviar dados incompletos, não validados ou provenientes de
  uma segunda pipeline.
- A limitação permanece: a experiência diária oficial ainda não recebe a
  carteira real.
- O Marco 20.0 não atende aos critérios de aprovação enquanto a fonte canônica
  não for disponibilizada ao frontend.

## Git e validações

SHA inicial: `74f145623a51d6ada8b0f8daac6cc4771b93d76e`.

Resultados executados antes do commit:

- `python -m pytest -q`: 404 testes passaram.
- `node --test frontend/app.test.js`: 49 testes passaram.
- `node --check frontend/daily_client.js`: passou.
- `node --check frontend/app.js`: passou.
- `mypy backend`: passou em 57 arquivos.
- `pyright backend tests`: passou sem erros ou avisos.
- `ruff check backend tests`: passou.
- `python -m compileall -q backend tests`: passou.
- `git diff --check`: passou.
- `git diff --exit-code -- backend`: passou; backend inalterado.
- `node --check frontend/daily_request_builder.js`: não executado porque o
  arquivo foi deliberadamente não criado diante do bloqueio documentado.

O teste HTTP real foi executado duas vezes com uma posição UBS/JOLIKA contendo
todos os campos oficiais. O adaptador aceitou e processou o JSON, mas o servidor
respondeu HTTP 500 com `contract_version: "1.0"`, `status: "ERROR"` e código
`EXPERIENCE_ERROR`. A segunda tentativa utilizou os valores do fixture oficial
de `tests/test_daily_http.py` e reproduziu o mesmo resultado. Essa falha do fluxo
real já existente não foi corrigida porque o backend está explicitamente fora do
escopo do marco.

Commit, SHA final, branch, pull request, limpeza final da árvore e confirmação de
ausência de merge serão registrados na entrega após a conclusão do fluxo Git.
