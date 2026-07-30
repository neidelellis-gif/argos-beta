# Marco 25 — Market Agenda Foundation

## Objetivo e arquitetura

A Agenda de Mercado recebe exclusivamente eventos estruturados e verificáveis. O fluxo é
`upload JSON/CSV → MarketAgendaEvent → MarketAgendaEngine → DailyApiFacade → contrato 1.1 → renderer`.
Ela não consulta notícias, não usa modelos de linguagem e não inventa eventos.

## Modelo canônico

`MarketAgendaEvent` é imutável e preserva data, horário e fuso recebidos. Os tipos oficiais são
`EARNINGS`, `DIVIDEND`, `CENTRAL_BANK`, `MACROECONOMIC`, `REGULATORY`, `CORPORATE`,
`MARKET_HOLIDAY` e `OTHER`. A importância aceita `HIGH`, `MEDIUM` e `LOW`; na entrada,
`CRITICAL` normaliza para `HIGH` e `MODERATE` para `MEDIUM`.

Datas usam `YYYY-MM-DD`; horários usam `HH:MM`. Eventos com horário exigem identificador IANA.
Eventos de dia inteiro não podem informar horário. Todo evento exige `source_name` e
`source_reference`; a referência técnica não é exposta no Cockpit.

## Importação e sessão

`POST /api/market-agenda/import` aceita exatamente um upload `multipart/form-data`, `.json` ou
`.csv`. JSON contém somente `{"events": [...]}`. CSV usa os cabeçalhos canônicos na ordem oficial
e `|` para coleções. A validação é única e atômica: qualquer erro retorna HTTP 400 e preserva a
sessão anterior. Uma importação válida substitui integralmente a agenda da sessão.

`GET /api/market-agenda` consulta a coleção e `DELETE /api/market-agenda` limpa somente a agenda.
`SESSION_MARKET_AGENDA` é independente de `SESSION_PORTFOLIOS`; não existe histórico permanente.

## Relevância, deduplicação e ordem

O motor considera a janela inclusiva da data de referência até sete dias depois. A relevância é
estabelecida por identificador, nome, classe, setor, moeda ou instituição da carteira. Eventos
gerais `HIGH` dos tipos banco central, macroeconômico, regulatório e feriado exigem relação com a
carteira; eventos globais não são incluídos indiscriminadamente.

Duplicatas são detectadas por ID, data/horário/título normalizado ou fonte/referência. Prevalecem
maior importância, maior preenchimento e menor ID. A ordem é data, presença de horário, horário,
importância, título e ID. A saída diária é limitada a dez eventos e não modifica entradas.

## Contrato público, frontend e segurança

O contrato 1.1 preserva os campos 1.0 e adiciona `market_agenda`. Cada item expõe exatamente
`id`, `event_type`, `importance`, `title`, `summary`, `event_date`, `event_time`, `timezone`,
`all_day`, `affected_assets` e `source_name`. O cliente lê com segurança respostas 1.0 sem agenda.
O renderer oculta o painel vazio, traduz categoria/importância e apresenta horário e fuso originais
sem conversão. IDs e referências técnicas não são renderizados. O DOM usa `createElement`,
`textContent` e `appendChild`, sem `innerHTML`.

Cada importação aceita no máximo 1.000 eventos, títulos de 200 caracteres, descrições de 1.000 e
50 itens por coleção. Controles inválidos, IDs vazios, fontes ausentes, fusos ambíguos, campos
desconhecidos e duplicatas rejeitam o arquivo inteiro.

## Expansão futura

Captura automática, APIs pagas, notícias, sentimento, alertas, banco de dados, recorrência e
conversão de fuso permanecem fora deste marco e exigem decisão de arquitetura futura.

## Validação visual

Os testes DOM validam painel presente/ausente, múltiplos eventos, largura estrutural já responsiva,
texto seguro, fonte, data e fuso. A captura automatizada não foi executada neste ambiente porque
não há navegador nem Playwright instalados; não foram observados erros nos testes DOM.
