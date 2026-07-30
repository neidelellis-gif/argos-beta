# Integração de dados oficiais de mercado

## Repositório offline

O ARGOS lê exclusivamente arquivos JSON locais em `data/market/facts/` e
`data/market/agenda/`. Não há rede, sincronização ou classificação no carregador.
Cada arquivo declara `source_id`, `source_name`, `source_type`, `reference_date`,
`collected_at` (ISO 8601 com fuso) e `data_version`.

## Formato e modelos

Arquivos de fatos contêm `facts`; cada item possui `fact_id`, `title`,
`description`, `category`, `source`, `reference_date`, `importance` e as coleções
`related_assets`, `related_sectors`, `related_currencies` e
`related_institutions`. Categorias seguem `FactCategory`; importâncias seguem
`FactImportance`. `source` referencia o `source_id` do arquivo.

Arquivos de agenda contêm `events` no contrato já documentado em
`MARKET_AGENDA_FOUNDATION.md`. O modelo imutável `MarketAgendaEvent` permanece
inalterado. `MarketFact` é o nome oficial do mesmo modelo imutável
`FactCandidate`, preservando compatibilidade direta com os motores existentes.

Tipos de fonte aceitos: `BANCO_CENTRAL`, `BOLSA`, `EMPRESA`,
`CALENDARIO_ECONOMICO` e `RELATORIO_OFICIAL`.

## Fluxo

`MarketDataLoader` localiza os arquivos, valida todo o conjunto atomicamente e
retorna `OfficialMarketData`, cujas coleções `facts`, `agenda` e `sources` são
tuplas. A borda diária fornece os fatos ao `DailyFactsEngine` e os eventos ao
`MarketAgendaEngine`; os demais motores continuam recebendo apenas seus objetos
canônicos. O Cockpit combina esses dados com as carteiras carregadas por
`OfficialPortfolioLoader`.

## Qualidade

Falhas geram `MarketDataValidationError` com `diagnostic_id` no padrão do
`DataQualityEngine`. São rejeitados arquivos/fontes ausentes, formatos e tipos de
fonte inválidos, fatos ou eventos duplicados, datas inválidas ou inconsistentes,
categorias/importâncias inválidas, ativos malformados e origem divergente. Não há
saída parcial: qualquer erro rejeita a carga completa.
