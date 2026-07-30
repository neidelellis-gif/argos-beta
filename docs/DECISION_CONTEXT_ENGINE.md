# Decision Context Engine — Marco 27

## Objetivo e arquitetura

O `DecisionContextEngine` explica por que informação estruturada pode ser relevante
para o perfil declarado. Ele não recomenda operações, não altera a carteira e roda
depois de fatos, agenda, impactos, análises e prioridades. A saída é uma seção
independente recebida pronta pela experiência diária.

Fluxo: carteira canônica e informação diária → `DecisionContextEngine` → projeção
pública 1.3 → bloco **Contexto da decisão**.

## Perfil canônico

`DecisionProfile` é uma `dataclass` imutável. Seus campos cobrem identificador, nome,
escopo (`PERSONAL`, `COMPANY`, `CONSOLIDATED`), risco, horizonte, objetivos primários
e secundários, liquidez, preservação, tolerâncias declaradas, restrições explícitas,
mercados preferenciais, moeda-base, frequência, data de revisão, fonte e notas.

Os níveis são `VERY_LOW`, `LOW`, `MODERATE`, `HIGH`, `VERY_HIGH` (entrada `MEDIUM`
normaliza para `MODERATE`). Preservação aceita `LOW`, `MODERATE`, `HIGH`, `CRITICAL`;
horizonte aceita `IMMEDIATE`, `SHORT_TERM`, `MEDIUM_TERM`, `LONG_TERM`,
`MULTI_HORIZON`; frequência aceita `DAILY`, `WEEKLY`, `MONTHLY`, `QUARTERLY`,
`EVENT_DRIVEN`. Objetivos são exclusivamente os enums definidos no Marco 27.

## Importação, validação e sessão

`POST /api/decision-context/import` recebe exatamente um JSON (`{"profile": ...}`)
ou CSV oficial; coleções CSV usam `|`. A validação é integral antes da troca em
`SESSION_DECISION_CONTEXT[session_id]`. Erros de formato, enum, fonte, data/moeda,
duplicata, limite ou coerência preservam o perfil atual. `GET /api/decision-context`
consulta e `DELETE /api/decision-context` remove somente o perfil, sem afetar carteira
ou agenda. Não há inferência automática nem persistência histórica.

## Motor, relevância, fatores e conflitos

As associações usam igualdade normalizada em ativos, classes, setores e moedas.
Marcadores estruturados documentam regras de objetivo (`DIVIDEND`/`INCOME`, inflação
e proteção inflacionária, câmbio e proteção cambial), volatilidade e iliquidez. Datas
explícitas são comparadas com a referência segundo o horizonte declarado. Concentração
significa somente múltiplas posições relacionadas, sem cálculo percentual.

Relevância `HIGH`, `MEDIUM` e `LOW` representa relação direta, indireta ou ampla
verificável. Fatores registram o campo declarado que sustentou o contexto. Conflitos
só existem para incompatibilidades explícitas, como preservação crítica com impacto
alto negativo/incerto ou liquidez muito alta com iliquidez marcada na entrada.

## Consolidação, segurança e limitações

O motor deduplica por tipo e relações, ordena deterministicamente por relevância,
tipo, rastreabilidade, título e ID, e limita a cinco itens. Relações internas mantêm
rastreabilidade. A projeção pública não expõe relações internas, perfil, fonte, notas,
sessão ou posições.

Um filtro rejeita linguagem operacional em português e inglês. Entradas e perfil não
são modificados. Limitações aparecem apenas quando materiais. Não há preços em tempo
real, retorno projetado, recomendação, suitability, ordens ou automações.

## Contrato 1.3, frontend e compatibilidade

`decision_contexts` expõe somente `id`, `context_type`, `relevance_level`, `title`,
`summary`, `related_assets`, `context_factors` e `limitations`. O frontend aceita 1.0,
1.1, 1.2 e 1.3; coleção ausente é vazia. O bloco fica oculto quando vazio, traduz tipo
e relevância e cria nós somente com `createElement`, `textContent` e `appendChild`.

## Expansão futura e Marco 30

Novas associações exigem regras estruturadas aprovadas e devem preservar a separação
dos motores. O Marco 30 fica reservado à auditoria integral do MVP: ponta a ponta,
decisões aprovadas, contratos, sessões, frontend, erros silenciosos, estados vazios,
segurança, regressões, dados reais, usabilidade, bugs, arquitetura e documentação.
Nenhuma funcionalidade nova será adicionada antes da conclusão dessa auditoria.
