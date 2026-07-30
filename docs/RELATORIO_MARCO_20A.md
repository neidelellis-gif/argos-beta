# RELATÓRIO DE IMPLEMENTAÇÃO — MARCO 20A — CANONICAL PORTFOLIO EXPOSURE

## Resumo executivo e Git inicial

O backend agora expõe diretamente as posições canônicas validadas da sessão nas
respostas existentes de importação e dashboard. O frontend mantém cópias dessas
posições em estado separado da prévia TipRanks, sem alterar a chamada diária ou a
interface visual.

SHA inicial: `ef7475ce43ba239e4cde4031bddb431b01946381`.

## Fonte canônica e fluxo identificado

A fonte da verdade permanece exatamente em
`SESSION_PORTFOLIOS[session_id]["positions"]`, definida em `backend/server.py`.
Os conectores produzem `PortfolioPosition`; os diagnósticos são concluídos; a
sessão substitui somente a instituição reimportada e preserva as demais.

As posições não chegavam ao frontend porque `_import_portfolios()` removia a
tupla por meio de `result.pop("positions")`, usando-a apenas para atualizar a
sessão e construir o dashboard agregado. `GET /api/dashboard` também devolvia
somente o resultado agregado de `build_dashboard()`.

## Arquivos criados

- `backend/canonical_portfolio.py`: serializador público puro.
- `tests/test_canonical_portfolio.py`: testes unitários do serializador.
- `docs/CANONICAL_PORTFOLIO_EXPOSURE.md`: contrato e ciclo da exposição.
- `docs/RELATORIO_MARCO_20A.md`: este relatório.

## Arquivos alterados

- `backend/server.py`: exposição nas respostas existentes.
- `frontend/app.js`: estado canônico da sessão.
- `frontend/app.test.js`: testes do estado frontend e carga inicial.
- `tests/test_portfolio_import.py`: testes HTTP e de sessão.
- `tests/test_dashboard.py`: expectativa do novo campo oficial.

## Serializador e mapeamento

`serialize_portfolio_position()` recebe somente `PortfolioPosition` e cria um
novo dicionário com exatamente: `institution`, `owner`, `account`, `asset_class`,
`asset_subclass`, `asset_name`, `identifier`, `identifier_type`, `quantity`,
`unit_price`, `market_value`, `currency`, `portfolio_weight`, `reference_date` e
`source_file`. `serialize_portfolio_positions()` preserva a ordem da tupla da
sessão, sem ordenar, deduplicar ou modificar os objetos.

`owner` usa `position.owner.value`. Quantidade, preço, valor e peso usam `str()`
diretamente sobre `Decimal`, preservando zeros e precisão, sem `float`. Datas usam
`date.isoformat()`. Todo campo opcional ausente permanece `None`/`null`; não há
fallback de conteúdo ou data.

## Respostas HTTP e comportamentos de sessão

`POST /api/portfolios/import` preserva `dashboard`, `files` e `diagnostics` e
adiciona `positions` com a coleção completa após a atualização da sessão.
`GET /api/dashboard` adiciona `positions` ao payload para carga e recarga. Os
endpoints legados `/api/cockpit` e `/api/facts` permanecem inalterados. Limpar a
sessão retorna `positions: []`.

Uma reimportação parcial continua substituindo apenas a instituição reimportada;
a resposta contém as posições atualizadas e as instituições preservadas. Uma
importação inválida não altera a sessão e não expõe posições parciais no erro.
Uma sessão vazia retorna lista vazia, nunca `null`.

## Estado frontend e separação de fontes

`canonicalPortfolioPositions` começa vazio e recebe cópias rasas de cada objeto
de `payload.positions` após importação válida, carga inicial e limpeza. Leituras
de teste também retornam cópias, impedindo alteração acidental do estado.

`importedPortfolioPositions` permanece exclusivamente como prévia local TipRanks
e nunca alimenta o estado canônico. Strings decimais, proprietários e instituições
são mantidos sem formatação ou consolidação. `loadDailyExperience()` continua
enviando `positions: []`, portanto o Marco 20 não foi retomado.

## Segurança

O payload contém somente os 15 campos públicos. Não inclui token/ID de sessão,
objetos Python, enum repr, stack, diagnósticos por posição, conteúdo bruto ou
campos visuais. Os conectores armazenam em `source_file` o nome oficial do arquivo;
o teste real confirmou que nenhum valor exposto começa com caminho absoluto.

## Testes implementados

Os testes backend cobrem 15 campos exatos, enums, zeros decimais, data, nulos,
coleção vazia, determinismo, imutabilidade, tipo inválido, importação real,
coleção completa após reimportação parcial, preservação após erro, carga da sessão,
sessão vazia e ausência de caminho absoluto.

Os testes frontend cobrem estado inicial, atualização por importação, cópia
imutável, separação TipRanks, UBS e Santander separados, JOLIKA e NEI separados,
precisão decimal, restauração por dashboard e manutenção do request diário vazio.

## Testes HTTP reais

A importação multipart do fixture reconhecido
`frontend/test/fixtures/UBS_Holdings_27_07_2026.csv` retornou HTTP 200, 28 posições
e exatamente 15 campos em cada posição. Uma chamada subsequente a
`GET /api/dashboard` com o mesmo cookie retornou HTTP 200 e uma coleção integralmente
equivalente, sem nova leitura do arquivo.

## Investigação do EXPERIENCE_ERROR

A chamada real a `POST /api/daily-experience` foi repetida usando uma posição
retornada pela nova serialização. Resultado: HTTP 500, `status: ERROR`,
`error.code: EXPERIENCE_ERROR` e `error.stage: EXPERIENCE`.

A reprodução interna identificou a causa exata: com `reference_date: null`, o
orquestrador conclui, mas `DailyExperienceComposer._validate_input()` lança
`DailyExperienceError` de código interno `MISSING_REFERENCE_DATE`. O defeito é uma
inconsistência preexistente entre a referência opcional aceita pelo contrato e a
exigência do compositor; não decorre da estrutura ou serialização das posições.
Nenhuma correção foi feita, pois ela alteraria componentes fora do escopo 20A.
O Marco 20 não deve ser retomado enquanto essa falha permanecer.

## Compatibilidade, riscos e limitações

Os Marcos 10–19 permanecem compatíveis: importadores, validações, diagnósticos,
consolidação, motores, regras analíticas, contrato diário 1.0, CSS e layout não
foram alterados. Endpoints legados não recebem o novo campo.

Não houve mudança visual. A página respondeu HTTP 200, carregou os scripts uma
única vez e o HTML não contém JSON de posições nem `[object Object]`. Screenshot e
console automatizado não foram obtidos porque não há navegador automatizado no
ambiente.

O risco remanescente é o `EXPERIENCE_ERROR` isolado acima. A exposição canônica
está pronta, mas a integração do Marco 20 continua fora deste commit.

## Validações

- `python -m pytest -q`: 411 testes passaram.
- `node --test frontend/app.test.js`: 54 testes passaram.
- `node --check frontend/daily_client.js`: passou.
- `node --check frontend/app.js`: passou.
- `mypy backend`: passou em 58 arquivos.
- `pyright backend tests`: passou sem erros ou avisos.
- `ruff check backend tests`: passou.
- `python -m compileall -q backend tests`: passou.
- `git diff --check`: passou.

Commit, SHA final, branch, árvore limpa, pull request e confirmação de ausência de
merge serão registrados na entrega após o fluxo Git final.
