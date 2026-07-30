# Daily Priority Engine

## Finalidade

O `DailyPriorityEngine` é o terceiro motor oficial de inteligência diária do
ARGOS. Ele transforma análises estruturadas em **zero a duas prioridades de
atenção**. O motor não recomenda nem executa operações financeiras.

## Arquitetura e integrações

O fluxo oficial é:

```text
Carteira canônica
  → DailyFactsEngine
  → DailyAnalysisEngine
  → DailyPriorityEngine
  → DailyExperienceComposer
  → Cockpit Executivo
```

O Facts Engine relaciona contexto estruturado à carteira. O Analysis Engine
organiza os fatos e preserva seus ativos. O Priority Engine usa somente essas
análises como fonte de decisão. A facade coordena os motores, e o Composer
somente limita e mapeia o resultado para o contrato público existente.

## Entradas

- `analyses`: coleção de mapas com `id`, `type`, `priority`, `title`, `summary`,
  `related_facts` e, opcionalmente, `affected_assets`;
- `positions`: coleção de `PortfolioPosition` canônicas, disponível apenas para
  confirmação de relações. Posições não são necessárias quando a análise já
  contém os ativos.

O motor não reconstrói fatos por `related_facts`, não recalcula patrimônio,
exposição, peso ou risco e não modifica as entradas.

## Contrato de saída

Cada item contém exatamente:

```json
{
  "id": "priority-...",
  "type": "ANALYZE",
  "priority": "HIGH",
  "title": "...",
  "summary": "...",
  "related_analyses": ["analysis-..."],
  "affected_assets": ["..."]
}
```

## Tipos e níveis

- `ANALYZE`: compreensão, acompanhamento ou aprofundamento;
- `DECIDE`: uma escolha objetiva já indicada pela análise precisa ser examinada,
  sem implicar execução.

Os níveis aceitos são `HIGH`, `MEDIUM` e `LOW`. `CRITICAL` é normalizado para
`HIGH`; qualquer outro nível é descartado. A prioridade da análise não é
elevada nem reduzida por critérios patrimoniais.

## Agrupamento, deduplicação e ordenação

Análises são agrupadas somente quando compartilham ativos, inclusive de forma
transitiva. Ativos e referências duplicados são removidos deterministicamente.

Duplicatas são eliminadas por ID, título normalizado ou combinação de tipo com
o mesmo conjunto de análises relacionadas. A ocorrência de maior prioridade é
preservada. A ordem final é:

1. prioridade: `HIGH`, `MEDIUM`, `LOW`;
2. tipo: `DECIDE`, `ANALYZE`;
3. título normalizado;
4. ID.

Depois da ordenação, no máximo dois itens são expostos. O motor nunca cria uma
segunda prioridade artificial.

## Rastreabilidade

`related_analyses` mantém a ligação da prioridade às análises. Cada análise
mantém `related_facts`, e os fatos preservam os ativos. Assim, permanece a
cadeia prioridade → análise → fato → ativo. `affected_assets` é copiado somente
das análises, sem inserir ativos não relacionados ou a carteira inteira.

## Linguagem proibida

Análises que propagam instruções explícitas como comprar, vender, aumentar ou
reduzir posição, reforçar, liquidar, entrar, sair, aplicar, resgatar e seus
equivalentes oficiais em inglês são descartadas. O motor não substitui uma
recomendação por outra formulação recomendatória.

## Limites do MVP

O motor não consulta notícias, agenda, calendário, preços ou serviços externos;
não produz alertas, notificações, recomendações, execução automática, modelos
de linguagem, telas novas ou histórico persistente. O contrato público continua
na versão `1.0`.

## Critérios para expansão futura

Qualquer novo tipo, nível, campo, fonte externa, persistência ou regra de
priorização exige autorização e revisão explícita do contrato. Uma expansão
deve preservar rastreabilidade, separação patrimonial, determinismo,
imutabilidade e ausência de recomendação financeira.
