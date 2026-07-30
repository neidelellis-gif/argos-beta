# Data Quality Engine

## Responsabilidade

`DataQualityEngine` é um componente puro e isolado. Ele recebe carteira, agenda,
contexto decisório e data de referência; não altera as entradas, não persiste
estado e não cria análises ou recomendações. A fachada o executa sobre os dados
canônicos validados antes de compor a experiência diária.

Fluxo:

`Carteira + Agenda + Contexto → DataQualityEngine → DailyExperienceComposer`

Os motores analíticos existentes permanecem inalterados. Um diagnóstico informa
a qualidade da sessão; `can_continue` descreve a gravidade do dado e não muda
prioridades, impactos ou contextos.

## Contrato do diagnóstico

Cada item contém exatamente:

```json
{
  "id": "portfolio.missing_currency",
  "severity": "WARNING",
  "category": "PORTFOLIO",
  "title": "Moedas ausentes",
  "description": "Há posições sem moeda informada.",
  "affected_items": ["GLD"],
  "can_continue": true
}
```

Severidades aceitas: `ERROR` (Erro), `WARNING` (Atenção) e `INFO`
(Informação). Categorias aceitas: `PORTFOLIO`, `MARKET_AGENDA`,
`DECISION_CONTEXT`, `CROSS_VALIDATION` e `SYSTEM`.

O resultado consolidado contém `status`, `summary` e `diagnostics`. `ERROR`
prevalece sobre `WARNING`; `HEALTHY` é usado somente quando não existem erros
nem alertas. Informações isoladas não retiram o estado saudável.

## Validações determinísticas

- **Carteira:** ausência, itens fora do modelo canônico, duplicatas,
  identificador, moeda e instituição ausentes.
- **Agenda:** ausência informativa, itens/datas inválidos, eventos expirados,
  duplicados e sem fonte.
- **Contexto:** ausência, modelo inválido, objetivos vazios, moeda-base ausente e
  revisão vencida.
- **Cruzamentos:** identificadores da agenda ausentes na carteira, eventos sem
  relacionamento, contexto `COMPANY` aplicado a carteira pessoal e moeda-base
  ausente nas moedas da carteira.

As coleções são materializadas em tuplas e nunca ordenadas ou modificadas. IDs
e itens afetados são normalizados de forma determinística; o motor não consulta
internet, API, relógio global ou estado de sessão.

## Interface

O Cockpit mostra **Qualidade dos dados** somente quando o status público é
`WARNING` ou `ERROR`. O renderer aceita contratos 1.0 a 1.4, trata versões
anteriores como ausência de diagnóstico e cria todo o conteúdo com
`document.createElement`, `textContent` e `appendChild`.
