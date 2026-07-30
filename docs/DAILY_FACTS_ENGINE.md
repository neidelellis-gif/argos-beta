# Daily Facts Engine

## Arquitetura

`DailyFactsEngine` é um componente isolado entre o contrato de entrada da
Experiência Diária e a orquestração existente. Ele recebe posições canônicas e
contexto já estruturado como `FactCandidate`. Não consulta rede, arquivos,
HTML, frontend ou dashboard. A fachada entrega seus candidatos à orquestração;
o compositor continua responsável pela apresentação e pelo limite público.

## Responsabilidades

- cruzar eventos conhecidos com ativos da carteira;
- produzir observações objetivas e independentes;
- eliminar duplicatas por identificador ou título;
- ordenar candidatos por `HIGH`, `MEDIUM` e `LOW` e limitar a cinco;
- rejeitar textos com verbos explícitos de recomendação.

O motor não altera posições ou análises, não recomenda, não decide e não cria
prioridades de decisão. Patrimônios permanecem representados exclusivamente nas
posições canônicas recebidas e nunca são consolidados pelo motor.

## Entradas

1. `positions`: sequência de `PortfolioPosition` canônicas.
2. `context`: sequência de eventos estruturados `FactCandidate` disponíveis.

Um evento é relevante quando ao menos uma relação declarada (ativo, setor,
moeda ou instituição) coincide com um campo canônico da posição. Contexto sem
relação explícita não gera fato.

## Saída

`generate()` devolve uma lista de zero a cinco objetos com os campos
obrigatórios `id`, `category`, `priority`, `title`, `summary` e
`affected_assets`. `CRITICAL` do contexto legado é normalizado para `HIGH`;
somente `HIGH`, `MEDIUM` e `LOW` são publicados pelo motor.

## Regras de geração

Os resultados são determinísticos: prioridade, título e identificador definem
a ordem. Ativos afetados são únicos e ordenados. Carteira vazia, contexto vazio
ou contexto irrelevante resulta em `[]`. O componente não inventa eventos a
partir da mera existência de uma posição.

## Expansão futura

Novas fontes devem ser normalizadas para o contexto estruturado antes de chegar
ao motor. Novas relações podem ser incluídas apenas quando derivadas de campos
canônicos e rastreáveis. Acesso a provedores, persistência, enriquecimento por
IA e regras de decisão devem permanecer em camadas próprias; a saída e os três
níveis oficiais devem continuar compatíveis.
