# Daily Experience Orchestrator

## Responsabilidade

`DailyExperienceOrchestrator` é a camada final de apresentação do Cockpit. Ele recebe exclusivamente `data_quality`, `facts`, `priorities`, `analyses`, `decision_contexts`, `impact_assessments` e `market_agenda`. A camada não cria fatos, recalcula impactos, muda prioridades nem altera itens produzidos pelos motores.

## Ordem e exibição

A ordem oficial é: saudação/data, fatos importantes, prioridades do dia, análises, contexto da decisão, impacto potencial, agenda de mercado e qualidade dos dados. Cada coleção é copiada para uma tupla, preservando ordem e conteúdo.

Uma coleção aparece somente quando possui itens. Qualidade dos dados é a única exceção: aparece apenas com status `WARNING` ou `ERROR` e diagnósticos. Não há mensagens de vazio no Cockpit.

## Integridade e status

O diagnóstico interno confirma que os sete blocos foram avaliados, que as quantidades foram preservadas e que a versão é compatível. Ele não integra o contrato público nem é renderizado.

O status público da experiência é `READY` quando todos os componentes foram processados, `PARTIAL` quando um componente opcional não foi fornecido e `ERROR` quando a versão, um componente obrigatório ou sua estrutura torna a montagem impossível.

O resultado e seus mapas são imutáveis. As versões `1.0` a `1.5` são reconhecidas para permitir a leitura de respostas históricas.
