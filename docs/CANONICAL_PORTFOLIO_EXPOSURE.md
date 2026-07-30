# Exposição canônica de posições

## Fonte da verdade e ciclo da sessão

A única fonte da verdade é `SESSION_PORTFOLIOS[session_id]["positions"]`, uma
tupla de `PortfolioPosition` produzida pelos conectores e validações oficiais. A
importação continua substituindo somente a instituição reimportada e preservando
as demais instituições da sessão.

As rotas existentes foram ampliadas; nenhum endpoint novo foi criado:

- `POST /api/portfolios/import` retorna a coleção completa da sessão em
  `positions` após uma importação válida.
- `GET /api/dashboard` retorna `positions` para restaurar a sessão ao carregar ou
  recarregar a página.
- `DELETE /api/portfolios` retorna `positions: []` após limpar a sessão.

## Formato público

`backend/canonical_portfolio.py` serializa diretamente cada `PortfolioPosition`
nos 15 campos aceitos pelo contrato diário: `institution`, `owner`, `account`,
`asset_class`, `asset_subclass`, `asset_name`, `identifier`, `identifier_type`,
`quantity`, `unit_price`, `market_value`, `currency`, `portfolio_weight`,
`reference_date` e `source_file`.

Enums usam seu valor público; decimais usam `str()` sem conversão por `float`;
datas usam ISO 8601; campos opcionais ausentes permanecem `null`. A ordem da tupla
canônica é preservada, tornando a resposta determinística sem deduplicação ou
reordenação adicional.

O serializador não inclui sessão, caminhos técnicos, diagnósticos, apresentação,
conteúdo bruto ou objetos Python. `source_file` já é o nome armazenado oficialmente
pelos conectores e é preservado sem enriquecimento.

## Estado frontend

`canonicalPortfolioPositions` recebe exclusivamente cópias das posições das
respostas oficiais. Ele não é derivado do dashboard agregado e permanece separado
de `importedPortfolioPositions`, que continua sendo apenas uma prévia TipRanks
anterior à validação.

O Marco 20 deverá futuramente mapear esse estado para o request diário. O Marco
20A não altera `loadDailyExperience()`, que continua enviando uma carteira vazia.

## EXPERIENCE_ERROR

A falha foi isolada no compositor: uma requisição com `reference_date: null`
conclui a orquestração, mas `DailyExperienceComposer` rejeita o resultado com
`MISSING_REFERENCE_DATE`. Ela independe da serialização e da exposição canônica;
por isso não foi corrigida neste marco.
