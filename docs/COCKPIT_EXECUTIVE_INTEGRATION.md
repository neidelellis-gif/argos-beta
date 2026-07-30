# Integração do Cockpit Executivo

## Finalidade

O Marco 24 conecta a Experiência Diária real ao Cockpit Executivo existente. A
integração transforma a resposta pública já produzida pelo backend em uma
apresentação curta, segura e orientada à decisão. Ela não cria motores, fatos,
análises, prioridades, recomendações ou eventos.

## Fluxo backend/frontend

```text
Carteira canônica
  → DailyFactsEngine
  → DailyAnalysisEngine
  → DailyPriorityEngine
  → DailyExperienceComposer
  → POST /api/daily-experience
  → DailyFrontendClient
  → DailyExperienceRenderer
  → Cockpit Executivo
```

`app.js` preserva `canonicalPortfolioPositions`, usa `DailyRequestBuilder` para
montar o envelope e delega o HTTP ao `DailyFrontendClient`. Depois do sucesso,
entrega a resposta sem transformação ao `DailyExperienceRenderer`.

## Contrato público consumido

A inspeção do endpoint confirmou `contract_version: "1.0"` e os campos públicos:

- `status` e `error`: resultado da operação e erro público;
- `generated_at`: instante de geração;
- `header.greeting` e `header.display_date`: saudação e data de referência;
- `facts`: fatos com `id`, `category`, `text` e `importance`;
- `priorities`: prioridades com `fact_id`, `level`, `label`, `title` e `reason`;
- `analyses`: análises com `fact_id`, `action`, `title` e `reason`;
- `blocks`, `message`, `summary` e `experience_status`: metadados oficiais da
  experiência.

O contrato 1.0 **não contém agenda de mercado** nem ativos afetados. Por isso, o
frontend não inventa essas informações: o contêiner de agenda fica preparado e
oculto. Nenhum campo paralelo foi adicionado e a versão do contrato permaneceu
inalterada.

## Responsabilidade do renderer

`frontend/daily_experience_renderer.js` tem responsabilidade exclusivamente de
apresentação:

- recebe uma resposta `SUCCESS` compatível com a versão 1.0;
- preserva a saudação e prioriza `header.display_date`;
- mantém a ordem recebida e aplica apenas os limites visuais;
- constrói nós DOM com `createElement`, `textContent` e `appendChild`;
- oculta coleções vazias;
- controla os estados de carregamento e erro;
- nunca altera o payload recebido.

IDs (`id` e `fact_id`) e relacionamentos técnicos (`related_facts` e
`related_analyses`) não são renderizados. O renderer não ordena, classifica,
recalcula ou interpreta o conteúdo dos motores.

## Blocos e limites visuais

| Bloco | Limite | Regra quando vazio |
|---|---:|---|
| Fatos importantes | 5 | oculto |
| Prioridades do dia | 2 | oculto |
| Análises | 2 | oculto |
| Agenda de mercado | contrato não disponível | oculto |

Os níveis `HIGH`, `MEDIUM`/`MODERATE` e `LOW` são apresentados como **Alta**,
**Moderada** e **Baixa**. Os tipos `ANALYZE` e `DECIDE` são apresentados como
**Analisar** e **Decidir**. Os valores públicos já localizados do contrato
(`Analisar` e `Decidir`) também são preservados.

## Estados

- **Carregando:** mostra discretamente “Preparando sua visão do dia…”.
- **Sucesso com conteúdo:** mostra somente os blocos com itens válidos.
- **Sucesso sem conteúdo:** mantém somente saudação e data; não inventa mensagem
  de ausência de ações.
- **Erro:** encerra o carregamento e mostra “Não foi possível preparar a
  experiência diária.”. O erro técnico fica exclusivamente no console.

Uma falha na Experiência Diária não limpa a carteira canônica nem interfere no
dashboard e na importação.

## Segurança de renderização

Nenhum dado do backend é atribuído a `innerHTML`. Todo valor é tratado como texto,
de modo que marcação HTML ou JavaScript recebida aparece literalmente e não é
executada. Objetos desconhecidos não são convertidos implicitamente, impedindo a
exibição de JSON bruto ou `[object Object]`.

## Compatibilidade

A integração não altera importadores, motores, persistência, endpoints legados,
`DailyRequestBuilder`, `DailyFrontendClient` ou o contrato 1.0. Ela reutiliza a
página, o tema e o estado `canonicalPortfolioPositions` existentes.

## Validação visual

A validação deve confirmar saudação e data públicas, ordem e limites dos blocos,
agenda oculta, ausência de conteúdo técnico, legibilidade em desktop e largura
reduzida, ausência de duplicações e encerramento dos estados de carregamento e
erro. Quando um navegador automatizado estiver disponível, uma captura de tela
deve ser gerada; sua ausência não muda a segurança coberta pelos testes DOM.

## Limites do marco

Não fazem parte do Marco 24 notícias externas, APIs de mercado, geração de agenda,
preços de entrada, notificações, histórico, novas telas, regras analíticas,
recomendações financeiras, persistência adicional ou mudanças em importadores e
motores. A agenda só poderá ser exibida depois que fizer parte de um contrato
público oficial, sem alteração silenciosa da versão 1.0.
