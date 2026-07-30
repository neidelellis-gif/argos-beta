# Operação Real 01 — Integração das Carteiras Oficiais

## Repositório

As fontes versionadas ficam em `data/portfolios/personal/` e
`data/portfolios/jolika/`. Cada arquivo representa uma única carteira de uma
única instituição. UBS e Santander permanecem em arquivos diferentes e só são
reunidos pelo fluxo de carregamento; PF (`NEI`) nunca é convertida em Jolika.

## Formato esperado

O arquivo é JSON UTF-8 e contém exatamente `portfolio_id`, `portfolio_name`,
`portfolio_type` (`PERSONAL` ou `COMPANY`), `base_currency`, `institution`,
`reference_date` ISO `AAAA-MM-DD`, `origin` e `positions`.

Cada posição usa o contrato já consumido pelos motores: `account`,
`asset_class`, `asset_subclass`, `asset_name`, `identifier`, `identifier_type`,
`quantity`, `unit_price`, `market_value`, `currency` e `portfolio_weight`.
Instituição, proprietário, data e arquivo de origem são derivados do envelope,
evitando divergências dentro de uma carteira.

## Fluxo de carregamento

`OfficialPortfolioLoader` localiza `*/*.json`, valida cada documento e produz
`OfficialPortfolio` e `PortfolioPosition` canônicos e imutáveis. O componente
não consolida, não calcula e não altera valores. O Dashboard e a borda HTTP da
experiência diária carregam essa coleção; os motores Facts, Agenda, Impact,
Analysis, Priority, Decision Context e Data Quality continuam recebendo o mesmo
tipo canônico e não foram modificados.

O corpo público de `POST /api/daily-experience` continua compatível, mas, no
servidor do Cockpit, suas posições são substituídas pelas posições do repositório
oficial antes da execução. Assim, dados locais de teste ou prévias de upload não
alimentam análises operacionais.

## Validações

O carregamento rejeita JSON ou estrutura inválida, campos obrigatórios vazios,
`portfolio_type` desconhecido, moeda-base ou instituição ausente, data fora do
ISO, posição vazia ou inválida, números inválidos ou negativos e identificadores
duplicados de carteira ou posição. Os erros expõem identificadores `portfolio.*`
compatíveis com o vocabulário do `DataQualityEngine`, como
`portfolio.invalid`, `portfolio.missing_currency`,
`portfolio.missing_institution` e `portfolio.duplicates`.

Após a tradução, o `DataQualityEngine` permanece responsável pelo diagnóstico
determinístico da coleção canônica entregue ao fluxo diário.
