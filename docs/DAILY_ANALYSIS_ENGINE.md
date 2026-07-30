# Daily Analysis Engine

## Objetivo

O `DailyAnalysisEngine` é a segunda camada oficial de inteligência diária do
ARGOS. O `DailyFactsEngine` responde **o que aconteceu**; o Analysis Engine
responde **quais conjuntos de fatos merecem atenção hoje**.

O componente é uma transformação determinística e isolada. Ele não acessa
HTML, frontend, arquivos externos ou APIs e não altera fatos ou posições.

## Arquitetura

```text
Posições canônicas
       ↓
DailyFactsEngine
       ↓
fatos relacionados à carteira
       ↓
DailyAnalysisEngine
       ↓
0 a 2 análises
       ↓
DailyExperienceComposer
       ↓
Cockpit Executivo
```

O motor está em `backend/daily_analysis_engine.py`. A API principal é
`DailyAnalysisEngine.generate(facts, positions)`; `build` é um alias para
manter a convenção dos demais motores diários.

## Responsabilidade e limites

O motor:

- valida o contrato mínimo dos fatos;
- elimina fatos duplicados;
- agrupa fatos relacionados;
- explica objetivamente por que cada grupo merece atenção;
- classifica com os tipos `ANALYZE` ou `DECIDE`;
- mantém apenas as prioridades `HIGH`, `MEDIUM` e `LOW`;
- ordena de forma estável e entrega no máximo duas análises;
- preserva em `related_facts` todos os IDs que originaram cada análise.

O motor não consulta novas fontes, não reconstitui a carteira, não modifica as
entradas e não recomenda comprar, vender, aumentar ou reduzir posições. As
posições são recebidas exclusivamente no modelo canônico `PortfolioPosition`;
assim, o limite entre patrimônios permanece responsabilidade do fluxo que
seleciona as posições e gera os fatos, sem dependência de formatos de origem.

## Entradas

### Fatos

A entrada aceita os dicionários produzidos pelo `DailyFactsEngine`. Para a
análise, cada fato precisa conter:

```python
{
    "id": "fact-1",
    "priority": "HIGH",
    "title": "Resultado divulgado",
    "summary": "A companhia divulgou o resultado trimestral.",
    "affected_assets": ["ARGOS1"],
}
```

Campos adicionais, como `category`, são aceitos, mas não criam contexto novo.
Um fato inválido gera erro claro em vez de uma análise parcial.

### Posições

As posições devem ser instâncias de `PortfolioPosition`. O motor valida o
limite canônico, mas não lê arquivos, recalcula posições nem as modifica.

## Saída

A saída é uma lista com zero, uma ou duas análises:

```python
[
    {
        "id": "analysis-0123456789ab",
        "type": "DECIDE",
        "priority": "HIGH",
        "title": "2 fatos relacionados sobre ARGOS1",
        "summary": "Os fatos fact-1, fact-2 merecem atenção conjunta porque afetam ARGOS1.",
        "related_facts": ["fact-1", "fact-2"],
    }
]
```

`DECIDE` indica que um conjunto de prioridade `HIGH` merece decisão; não é uma
ordem ou recomendação de investimento. `MEDIUM` e `LOW` usam `ANALYZE`.

Quando nenhum fato é recebido, a saída é `[]`. O corte de segurança do motor é
duas análises, mesmo antes do limite de apresentação aplicado pelo Composer.

## Regras de agrupamento e deduplicação

1. IDs e títulos são normalizados sem diferenças de caixa, acentos ou
   pontuação.
2. Fatos com o mesmo ID ou título normalizado pertencem ao mesmo conjunto de
   duplicatas. A relação é transitiva.
3. Fatos que contenham linguagem recomendatória são descartados no limite do
   motor e nunca têm seu texto propagado para uma análise.
4. Em cada conjunto duplicado, permanece o fato de maior prioridade; empates
   são resolvidos por título e ID, garantindo estabilidade.
5. Fatos únicos são relacionados quando compartilham ao menos um item de
   `affected_assets`.
6. O agrupamento também é transitivo: se A se relaciona com B e B com C, os
   três formam uma única análise.
7. Grupos independentes permanecem análises independentes.
8. A prioridade do grupo é a maior prioridade entre seus fatos.
9. A ordenação final usa prioridade, título e ID. Somente os dois primeiros
   grupos são emitidos.

Essas regras usam somente os fatos recebidos. A descrição textual de um fato
não é interpretada para inferir ativos, impactos ou contexto adicional.

## Integração

### Facts Engine

O chamador deve primeiro executar o `DailyFactsEngine` com as posições
canônicas e o contexto estruturado. Apenas a lista retornada deve alimentar o
Analysis Engine. Não se deve enviar candidatos externos diretamente para esta
camada.

### Daily Experience Composer

O resultado analítico é a entrada do bloco **Análises**. O Composer continua
responsável somente por:

- ordenar os blocos da experiência;
- aplicar novamente o limite público de duas análises;
- traduzir os rótulos de apresentação (`Analisar` e `Decidir`);
- montar a resposta pública do Cockpit.

Deduplicação, agrupamento, explicação, tipo e prioridade pertencem ao Analysis
Engine e não devem ser recalculados pelo Composer.

## Expansões futuras

Sem alterar o contrato público, evoluções possíveis incluem regras adicionais
de relacionamento baseadas em campos estruturados que venham a ser emitidos
pelo Facts Engine, métricas de explicabilidade e novos testes de qualidade de
texto. Novos níveis de prioridade, novos tipos, consultas externas e
recomendações de investimento não fazem parte dessa expansão.
