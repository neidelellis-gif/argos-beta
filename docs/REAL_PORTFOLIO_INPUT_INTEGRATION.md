# Integração da carteira real à experiência diária

## Fluxo oficial

O fluxo da carteira até o Cockpit Executivo é:

`arquivos` → `importadores oficiais` → `PortfolioPosition` →
`SESSION_PORTFOLIOS[session_id]["positions"]` → serializador canônico →
`canonicalPortfolioPositions` → `DailyRequestBuilder` →
`POST /api/daily-experience` → `DailyExperienceComposer` → Cockpit Executivo.

Não existe reconstrução da carteira nesse percurso. A resposta oficial de
importação ou de restauração do dashboard alimenta `canonicalPortfolioPositions`,
que permanece separada da prévia local `importedPortfolioPositions`.

## Responsabilidade do builder

`frontend/daily_request_builder.js` recebe somente a coleção canônica e devolve
cópias das posições contendo exatamente os 15 campos públicos: `institution`,
`owner`, `account`, `asset_class`, `asset_subclass`, `asset_name`, `identifier`,
`identifier_type`, `quantity`, `unit_price`, `market_value`, `currency`,
`portfolio_weight`, `reference_date` e `source_file`.

O builder não converte números, recalcula pesos ou patrimônio, infere classes,
reordena posições, lê arquivos nem consulta dados agregados do dashboard.

## Contrato HTTP 1.0

`loadDailyExperience()` envia o envelope existente:

```json
{
  "positions": [],
  "fact_candidates": [],
  "reference_date": null
}
```

`positions` é o resultado do builder aplicado diretamente a
`canonicalPortfolioPositions`. `fact_candidates` permanece vazio. O
`reference_date` do envelope permanece `null`, inclusive se alguma posição não
possuir data; cada data oficial continua preservada dentro de sua posição e o
backend permanece responsável pela composição da resposta.

## Imutabilidade

O array de saída e cada posição de saída são novos objetos. A coleção e os
objetos armazenados em `canonicalPortfolioPositions` nunca são modificados pelo
builder. Strings decimais, datas e valores `null` são copiados sem transformação.

## Dependências

Esta integração depende do Marco 20A, que expôs a coleção serializada oficial no
frontend, e do Marco 20B, que definiu o tratamento de `reference_date` na
composição. Ela preserva o contrato público 1.0 e todas as rotas existentes.
