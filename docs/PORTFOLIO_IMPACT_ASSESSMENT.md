# Portfolio Impact Assessment

## Objetivo e princípio

O `PortfolioImpactAssessmentEngine` responde por que um fato validado ou evento selecionado merece atenção para posições canônicas específicas. Ele não consulta fontes externas, reconstrói posições, prevê preços, calcula retorno ou recomenda operações.

## Arquitetura e entradas

No fluxo diário, `DailyFactsEngine` e `MarketAgendaEngine` produzem origens estruturadas. O motor recebe essas duas coleções e `PortfolioPosition` canônicas, gera impactos, e entrega-os ao `DailyAnalysisEngine` e à fronteira pública. As entradas não são modificadas.

## Contrato interno

Cada item contém exatamente `id`, `source_type`, `source_id`, `impact_level`, `impact_direction`, `confidence`, `title`, `summary`, `affected_positions`, `affected_assets`, `impact_factors`, `related_facts` e `related_events`. `source_type` é `FACT` ou `MARKET_EVENT`. Posições afetadas contêm somente `position_id`, `asset_identifier`, `asset_name`, `institution` e `relationship_type`; valores patrimoniais nunca integram o impacto.

## Associação, nível e confiança

A comparação normaliza caixa e espaços, mas exige igualdade integral. A força oficial é: `DIRECT_ASSET`, `ASSET_NAME`, `INSTITUTION`, `SECTOR`, `ASSET_CLASS`, `CURRENCY`, `MARKET`, `COUNTRY`; a relação mais forte prevalece por posição. O motor usa somente campos explícitos e não infere setor, moeda, mercado ou país.

Origem alta com ativo direto gera impacto alto; ativo direto com origem média/baixa gera médio; relação indireta com origem alta gera médio; relação indireta com origem média gera baixo; relação indireta com origem baixa não gera item. Confiança alta representa ativo, nome ou instituição; média representa setor, classe, moeda ou mercado; baixa representa país. Confiança não é probabilidade de ganho.

## Direção e fatores

Direção aceita `POSITIVE`, `NEGATIVE`, `MIXED` e `UNCERTAIN`, sendo `UNCERTAIN` o padrão quando a origem não fornece direção estruturada válida. Cada fator registra tipo, valor e descrição neutra da relação verificável.

## Consolidação, deduplicação e ordenação

Há no máximo uma avaliação por tipo e ID de origem. Duplicatas preservam maior impacto, confiança e quantidade de relações diretas, com menor ID como desempate. A ordem é impacto, confiança, origem (`FACT` antes de `MARKET_EVENT`), título normalizado e ID. A saída diária é limitada aos cinco primeiros itens, sem preenchimento artificial.

## Integração com análises e rastreabilidade

O `DailyAnalysisEngine` aceita impactos opcionalmente e registra `related_impacts` apenas quando essa entrada é fornecida. Chamadas antigas mantêm o contrato anterior. Assim, o backend preserva a cadeia impacto → fato/evento → posição → ativo sem duplicar avaliações como análises nem alterar o limite de duas análises.

## Contrato público 1.2 e compatibilidade

A versão 1.2 preserva os campos 1.1 e adiciona `impact_assessments`, inclusive como lista vazia. Cada item público expõe somente `id`, `source_type`, `impact_level`, `impact_direction`, `confidence`, `title`, `summary`, `affected_assets` e `impact_factors`. IDs de origem/posição e posições internas não atravessam a fronteira. O frontend aceita 1.0 (sem agenda/impactos), 1.1 (agenda, sem impactos) e 1.2.

## Apresentação e segurança

O Cockpit mostra até cinco itens em “Impacto potencial”, entre análises e agenda, com traduções de nível, direção e confiança. O bloco fica oculto quando vazio e informa discretamente que direção não é recomendação. A renderização usa criação de elementos e `textContent`; não usa `innerHTML` nem JSON bruto. Textos com linguagem explícita de compra, venda ou alteração de posição são descartados.

## Limitações e expansão futura

O marco não inclui dados em tempo real, modelos externos, histórico, alertas, pesos, VaR, beta, duration, correlação, stress quantitativo, cenários ou execução. Evoluções futuras podem adicionar métricas quantitativas ou persistência somente por contratos versionados, fontes validadas e regras rastreáveis, sem misturar patrimônios.
