# MARCO 30 — Auditoria Técnica e Funcional do MVP ARGOS

**Data da auditoria:** 30 de julho de 2026  
**Baseline auditada:** branch `work`, commit `7503121`  
**Escopo:** implementação acumulada dos Marcos 20 a 29  
**Natureza:** auditoria independente; nenhuma funcionalidade ou refatoração foi realizada

## 1. Resumo executivo

1. O MVP apresenta boa disciplina de domínio: os motores auditados são determinísticos,
   majoritariamente imutáveis, têm contratos explícitos e são amplamente testados.
2. A suíte disponível passou integralmente: **534 testes Python e 80 testes JavaScript**.
3. O contrato diário evoluiu de modo aditivo entre 1.0 e 1.5, mas o backend só produz e
   valida 1.5; a compatibilidade histórica é uma responsabilidade de leitura do frontend.
4. Não foram encontrados ciclos entre imports Python internos pela análise estática AST.
5. O frontend usa criação de nós e `textContent`; não foi encontrado uso de `innerHTML`,
   `outerHTML`, `insertAdjacentHTML`, `document.write`, `eval` ou `new Function`.
6. Foram identificadas **duas não conformidades altas** na sessão HTTP: crescimento sem
   limpeza/expiração e aceitação de identificador fornecido pelo cliente sem rotação.
7. A API possui limites inconsistentes: o endpoint diário limita o corpo, enquanto uploads
   multipart e endpoints JSON legados confiam no `Content-Length` sem teto global.
8. Há duplicação relevante entre o fluxo diário oficial (`backend/daily/`) e motores/fluxos
   de compatibilidade na raiz de `backend`, elevando custo de manutenção e risco de desvio.
9. A experiência diária cumpre ordem, ocultação de vazios, privacidade inicial dos valores
   e tratamento seguro de conteúdo, embora a Home ainda exponha áreas auxiliares que tornam
   o caminho executivo menos direto que a especificação funcional aprovada.
10. **Decisão técnica: MVP aprovado com ressalvas**, adequado a uso diário local/controlado,
    mas ainda não a uma implantação multiusuário ou exposta sem estabilização das sessões,
    limites de entrada e hardening HTTP.

### Situação geral e maturidade

| Dimensão | Classificação | Síntese |
| --- | --- | --- |
| Arquitetura | Atenção | Fluxo oficial documentado e sem ciclos; compatibilidade mantém caminhos paralelos e acoplamento concentrado na fachada diária. |
| Motores | Conforme | Responsabilidades claras, resultados estáveis, limites e estados vazios cobertos; ressalvas pontuais de mutabilidade profunda. |
| Contratos | Conforme | Evolução 1.0–1.5 aditiva e leitura compatível; somente 1.5 é produzido pelo backend atual. |
| APIs | Atenção | Boa cobertura e erros estruturados no diário; limites e formatos de erro são inconsistentes entre endpoints. |
| Sessões | Não Conforme | Isolamento lógico existe, mas faltam expiração, limite, persistência segura e rotação de ID. |
| Frontend | Conforme | Ordem, visibilidade, erros e DOM seguro são testados. |
| Segurança | Atenção | DOM seguro e validação de contrato; sessão, uploads, headers e cache `pickle` requerem hardening. |
| Performance | Atenção | Sem gargalo algorítmico crítico no MVP; recomposição e armazenamento sem limite podem crescer. |
| Testes | Conforme | 614 testes executados e aprovados; falta métrica de cobertura e alguns cenários operacionais. |
| Documentação | Atenção | Motores novos têm documentação; roadmap/status e duplicatas documentais não estão totalmente sincronizados. |
| Experiência do usuário | Atenção | Fluxo diário é claro, mas a Home contém blocos auxiliares concorrendo com o Cockpit. |

**Nível de maturidade:** MVP funcional e bem testado para execução local/single-process,
com maturidade de produção ainda limitada por estado volátil, segurança de sessão e ausência
de controles operacionais de entrada.

## 2. Metodologia e evidências

A auditoria combinou:

- leitura das regras do repositório, arquitetura oficial, status do MVP e especificação da Home;
- inspeção integral dos oito motores, contrato, fachada diária, adaptador HTTP, servidor,
  renderer, cliente e testes relacionados;
- busca estática de APIs de DOM inseguras, execução dinâmica de testes e compilação Python;
- análise AST do grafo de imports internos;
- comparação das versões públicas 1.0–1.5 e de sua apresentação no frontend;
- avaliação arquitetural de performance, sem benchmark, conforme solicitado.

Comandos executados e resultados:

| Comando | Resultado |
| --- | --- |
| `python -m pytest -q` | 534 aprovados em 11,93 s |
| `node --test frontend/app.test.js` | 61 aprovados |
| `node --test frontend/daily_experience_renderer.test.js` | 19 aprovados |
| `python -m compileall -q backend tests` | concluído sem erro |
| análise AST local dos imports `backend.*` | zero ciclos encontrados |
| `python -m pytest --cov=backend --cov-report=term-missing -q` | não executado: plugin `pytest-cov` indisponível |

A ausência de uma métrica percentual de cobertura é tratada como lacuna de observabilidade,
não como falha da suíte. Não foram realizados testes com navegador real, carga, concorrência
ou provedor Finnhub real.

## 3. Arquitetura

### 3.1 Matriz de conformidade

| Item | Classificação | Evidência e análise |
| --- | --- | --- |
| Separação de responsabilidades | Conforme | Connectors normalizam entradas; MPU representa posições; motores produzem domínio; fachada compõe; renderer apresenta. |
| Ausência de dependências circulares | Conforme | A análise AST de imports internos encontrou zero ciclos. |
| Isolamento entre motores | Conforme | Os motores recebem modelos/iteráveis e não dependem de HTTP ou DOM. |
| Acoplamento excessivo | Atenção | `DailyApiFacade` conhece motores antigos, motores 1.0–1.5, serializers e orquestradores; é um ponto de composição amplo. |
| Duplicação de lógica | Atenção | Há pares conceitualmente próximos: `backend/daily/orchestrator.py` e `backend/daily_orchestrator.py`; `backend/daily/experience.py` e `backend/daily_experience.py`; dois motores de prioridade e dois de impacto. |
| Fluxo ponta a ponta | Conforme | Arquivo → connector → MPU → diagnóstico/consolidação → contexto/orquestração → dashboard/API → frontend está implementado e coberto por testes integrados. |
| Aderência à arquitetura | Atenção | O fluxo oficial existe, mas a fachada diária paralela dos contratos 1.0–1.5 não é apenas uma projeção simples do `backend.daily.orchestrator`; recompõe vários motores. |

### 3.2 Fluxo observado

1. `portfolio_import` seleciona conectores e produz `PortfolioPosition`.
2. O servidor guarda posições por sessão e reconstrói o dashboard.
3. O dashboard usa diagnóstico, consolidação e o orquestrador de `backend.daily`.
4. O endpoint `/api/daily-experience` usa `DailyHttpAdapter` e `DailyApiFacade`, que
   executam a cadeia versionada dos motores dos Marcos 20–29.
5. O frontend monta posições canônicas, chama o endpoint diário e delega a renderização ao
   `DailyExperienceRenderer`.

O desenho funciona, porém há **duas composições diárias** com modelos diferentes. Essa
duplicidade não configura ciclo ou bug comprovado, mas aumenta a possibilidade de dashboard
e experiência diária divergirem à medida que um caminho evoluir.

## 4. Motores

### 4.1 Resultado consolidado

| Motor | Resp. única | Determinismo | Imutabilidade | Ordenação | Deduplicação | Rastreabilidade | Vazio | Erro | Resultado |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `DataQualityEngine` | Sim | Sim | Atenção | Sim | Sim | Sim | Sim | Sim | Conforme |
| `DailyFactsEngine` | Sim | Sim | Sim | Sim | Sim | Sim | Sim | Sim | Conforme |
| `MarketAgendaEngine` | Sim | Sim com relógio injetável | Sim | Sim | Sim | Sim | Sim | Sim | Conforme |
| `PortfolioImpactAssessmentEngine` | Sim | Sim | Sim | Sim | Sim | Sim | Sim | Sim | Conforme |
| `DailyAnalysisEngine` | Sim | Sim | Sim | Sim | Sim | Sim | Sim | Sim | Conforme |
| `DailyPriorityEngine` | Sim | Sim | Sim | Sim | Sim | Sim | Sim | Sim | Conforme |
| `DecisionContextEngine` | Sim | Sim | Sim | Sim | Sim | Sim | Sim | Sim | Conforme |
| `DailyExperienceOrchestrator` | Sim | Sim | Sim | N/A | N/A | Sim | Sim | Sim | Conforme |

### 4.2 `DataQualityEngine`

- **Responsabilidade:** somente diagnostica carteira, agenda, contexto e cruzamentos; não
  emite decisão de investimento.
- **Determinismo/ordenação:** materializa iteráveis e produz diagnósticos em ordem fixa;
  itens afetados são `sorted(set(...))`.
- **Imutabilidade:** não altera entradas, mas retorna `dict`/`list` mutáveis. É uma
  imutabilidade comportamental, não profunda; por isso o ponto merece atenção, embora a
  fronteira contratual reconverta a estruturas controladas.
- **Vazios:** carteira vazia é `ERROR`, agenda vazia é `INFO`, contexto ausente é `WARNING`.
- **Erros:** rejeita data inválida e transforma itens canônicos inválidos em diagnóstico
  bloqueante, preservando continuidade explícita por `can_continue`.

### 4.3 `DailyFactsEngine`

- Relaciona fatos já estruturados à carteira; não interpreta arquivos nem apresenta HTML.
- Materializa entradas, valida tipos e não modifica objetos.
- Deduplica por ID e título normalizados, ordena por prioridade/título/ID e limita a cinco.
- Preserva `id` e ativos afetados, fornecendo rastreabilidade suficiente para a próxima camada.
- Sem posições retorna lista vazia; tipos inválidos geram `TypeError` claro.
- O filtro lexical de recomendações é propositalmente simples; falso negativo linguístico é
  dívida técnica, não não conformidade do contrato atual.

### 4.4 `MarketAgendaEngine`

- Seleciona eventos relevantes dentro da janela e relaciona-os às posições.
- O relógio é injetável, permitindo determinismo em testes; a data de referência explícita
  prevalece quando fornecida.
- Deduplica eventos, ordena por data/hora/importância/identidade e limita o resultado.
- Eventos preservam fonte, timezone e ativos afetados.
- Iteráveis vazios produzem resultado vazio; tipos e datas inválidos são rejeitados.

### 4.5 `PortfolioImpactAssessmentEngine`

- Avalia impacto qualitativo de fatos/eventos sobre posições, sem cálculo financeiro ou ação.
- Entradas são materializadas/validadas; saídas são registros imutáveis e serialização pública
  elimina IDs internos, posições e valores financeiros.
- Há ordenação oficial, deduplicação e limite de cinco avaliações.
- A rastreabilidade pública retém ID, tipo de fonte, fatores e ativos, sem vazar a estrutura
  canônica completa.
- Estados vazios retornam coleção vazia; referências inválidas falham com erro explícito.

### 4.6 `DailyAnalysisEngine`

- Produz somente análises acionáveis a partir de fatos e posições já validados.
- É determinístico, não muta entrada, deduplica, ordena e limita o resultado.
- Mantém vínculo pelo ID do fato e lista de ativos relacionados.
- Carteira ou fatos vazios não inventam análise; tipos inválidos são rejeitados.

### 4.7 `DailyPriorityEngine`

- Prioriza análises sem executar decisões.
- Usa critérios e desempates explícitos, deduplica e limita o conjunto.
- Preserva vínculo com a análise/fato e fatores de prioridade.
- Entrada vazia produz saída vazia; objetos inválidos geram erro de fronteira.
- O nome colide conceitualmente com `backend.daily_priority.DailyPriorityEngine`, o que é risco
  de manutenção, embora aliases explícitos evitem erro atual na fachada.

### 4.8 `DecisionContextEngine`

- Confronta carteira/impactos com perfil decisório e produz contexto, não recomendação.
- Ordena por relevância/tipo/identidade, deduplica e limita a cinco.
- Mantém fatores, limitações e ativos relacionados; campos internos não são serializados.
- Ausência de perfil ou carteira gera coleção vazia; tipos inválidos são rejeitados.

### 4.9 `DailyExperienceOrchestrator`

- Sua responsabilidade é estritamente verificar se um contrato 1.0–1.5 está apresentável e
  emitir estado público `READY`, `EMPTY`, `PARTIAL` ou `ERROR`.
- Resultado e mapas são congelados; a mesma entrada produz o mesmo estado.
- Não reordena nem deduplica conteúdo, corretamente, pois não recompõe blocos de domínio.
- Reconhece todas as versões históricas; versão incompatível e payload inválido resultam em
  diagnóstico explícito, sem exceção vazando ao frontend.

## 5. Contratos 1.0–1.5

### 5.1 Evolução incremental

| Versão | Incremento | Compatibilidade observada | Classificação |
| --- | --- | --- | --- |
| 1.0 | fatos, prioridades, análises, blocos e resumo | Base preservada nas versões seguintes | Conforme |
| 1.1 | `market_agenda` | Frontend aceita ausência em 1.0 e exige lista a partir de 1.1 | Conforme |
| 1.2 | `impact_assessments` | Campos internos são filtrados; versões anteriores tratam como vazio | Conforme |
| 1.3 | `decision_contexts` | Frontend exige lista em 1.3+; limite público de cinco | Conforme |
| 1.4 | `data_quality` | Estrutura, enums, contadores e status são validados | Conforme |
| 1.5 | `experience` | Adição de um único estado de apresentabilidade | Conforme |

### 5.2 Serialização, validação e campos públicos

- O backend atual define uma única versão oficial de emissão, `1.5`, e rejeita outra versão
  ao construir/validar `DailyApiResponse`.
- As versões 1.0–1.4 são compatibilidade de **leitura** no frontend e no orquestrador de
  experiência; não há serializers backend independentes capazes de reemitir snapshots de cada
  versão. Isso é aceitável para evolução aditiva, mas deve permanecer explícito.
- Dataclasses congeladas validam enums, timezone, tipos, ordem dos blocos, contadores e coerência
  entre coleções.
- A serialização pública dos impactos e contextos restringe os campos documentados.
- `validate_daily_api_response_payload` valida a forma superior e enums centrais, mas não valida
  recursivamente todos os campos de todos os itens serializados. A construção por dataclasses
  reduz o risco no produtor; como função pública de validação isolada, ela é permissiva.
- A validação de payload requer campos mínimos por inclusão (`required <= keys`) e aceita campos
  extras. Isso está alinhado à compatibilidade futura aditiva documentada.

### 5.3 Risco de regressão

O risco é baixo para a forma produzida pela fachada, dado o conjunto de testes. O principal risco
é confundir “suporta 1.0–1.5” com “backend negocia/emite 1.0–1.5”. Ele não negocia: emite somente
1.5, enquanto consumidores históricos são tolerados no navegador.

## 6. APIs

### 6.1 Endpoints identificados

| Método | Endpoint | Função | Avaliação |
| --- | --- | --- | --- |
| GET | `/api/dashboard` | dashboard oficial e posições da sessão | Conforme com ressalva de erro genérico |
| GET | `/api/cockpit` | projeção legada | Conforme |
| GET | `/api/facts` | projeção legada | Conforme |
| GET/POST/PUT | `/api/daily-experience` | contrato diário 1.5 | Conforme |
| POST | `/api/portfolios/import` | importação multipart | Atenção: sem limite global de corpo |
| DELETE | `/api/portfolios` | limpeza da carteira | Conforme funcionalmente |
| GET/DELETE | `/api/market-agenda` | leitura/limpeza da agenda | Conforme |
| POST | `/api/market-agenda/import` | importação de agenda | Atenção: sem limite HTTP global |
| GET/DELETE | `/api/decision-context` | leitura/limpeza do perfil | Conforme |
| POST | `/api/decision-context/import` | importação do perfil | Atenção: sem limite HTTP global |
| POST | `/api/analyze` | análise legada | Atenção: JSON/base64 sem limite de corpo |
| POST | `/api/santander/inspect` | inspeção legada | Atenção: JSON/base64 sem limite de corpo |

### 6.2 Códigos, inválidos e erros

- O adaptador diário diferencia sucesso, método não permitido, tipo de conteúdo, JSON inválido,
  payload inválido, corpo excessivo e falha interna, sempre no contrato 1.5.
- Endpoints desconhecidos retornam 404; PUT fora do diário retorna 501.
- Importações retornam 400 para conteúdo/formato inválido e 200 no sucesso.
- Há inconsistência na forma de erros: diário usa envelope versionado; endpoints de importação
  usam `{ok, error}`; dashboard usa apenas `{error}`; `send_error` produz HTML. Consumidores
  precisam conhecer três formas.
- Exceções são devolvidas com `str(exc)`. Isso auxilia diagnóstico local, porém pode expor
  detalhes de parser/caminhos/bibliotecas em implantação exposta.
- `_decode_file_payload` usa `base64.b64decode` sem `validate=True`; lixo não alfabético pode ser
  tolerado antes de o parser subsequente falhar.
- A sessão da carteira é usada pelo dashboard; o endpoint diário recebe posições do request.
  O frontend reconcilia isso enviando seu estado canônico, mas um cliente HTTP que faça apenas
  importação + GET diário não obtém automaticamente a carteira da sessão. O comportamento é
  contratual, porém merece documentação explícita.

## 7. Sessões

| Item | Classificação | Evidência |
| --- | --- | --- |
| Isolamento | Conforme | Três mapas são indexados pelo mesmo ID e testes cobrem clientes distintos. |
| Limpeza | Não Conforme | DELETE limpa cada domínio, mas não há TTL, expiração global, limite ou coleta de sessões abandonadas. |
| Reutilização | Conforme | Nova importação preserva instituições não substituídas e reutiliza a sessão. |
| Interferência entre domínios | Conforme | Carteira, agenda e contexto têm stores separados e operações específicas. |
| Concorrência | Atenção | O servidor atual é single-threaded; mapas globais não possuem lock nem abstração para futura execução concorrente. |
| Identidade da sessão | Não Conforme | Qualquer valor não vazio do cookie é aceito e reutilizado; o servidor só gera ID se o cookie estiver ausente. Não há rotação. |
| Persistência/escala | Atenção | Estado é memória local do processo; reinício perde tudo e múltiplos processos divergem. |

### Riscos de sessão

1. **Fixação:** um cliente pode escolher previamente `argos_session=<valor>`; a primeira
   importação grava dados nesse identificador em vez de rotacioná-lo.
2. **Exaustão de memória:** IDs ilimitados e payloads de posições/agenda/contexto permanecem até
   DELETE ou reinício.
3. **Cookie:** `HttpOnly` e `SameSite=Strict` são positivos; falta `Secure` para ambientes HTTPS
   e não há `Max-Age`/`Expires` coerente com uma política de retenção.
4. **Sem autenticação:** está documentado como fora da maturidade atual; portanto o MVP deve
   permanecer em ambiente local/controlado.

## 8. Frontend

| Item | Classificação | Evidência |
| --- | --- | --- |
| Ordem dos blocos | Conforme | Header/mensagem → fatos → prioridades → análises → agenda → impactos → contexto → qualidade. |
| Regras de visibilidade | Conforme | Coleções ausentes/vazias são ocultadas e a renderização posterior limpa estado anterior. |
| Estados vazios | Conforme | Payload vazio mantém saudação/data e não inventa cartões. |
| Compatibilidade 1.0–1.5 | Conforme | Cliente e renderer reconhecem cada versão e exigem suas adições incrementais. |
| Segurança do DOM | Conforme | Elementos são criados e conteúdo externo é atribuído via `textContent`. |
| Renderização | Conforme | Limites de apresentação, traduções e imutabilidade estão testados. |
| Ausência de duplicidade visual | Conforme | O renderer substitui/limpa listas e os testes verificam repetição determinística. |
| Comportamento em erro | Conforme | Loading, prevenção de chamadas concorrentes e mensagem segura de falha estão cobertos. |

### Observações funcionais

- Valores monetários começam ocultos e existe controle Mostrar/Ocultar.
- O frontend não exibe IDs, relacionamentos técnicos ou JSON bruto nos cartões diários.
- A camada impõe limites visuais sem reordenar as decisões do backend.
- A versão 1.5 somente é apresentada quando `experience.status` é renderizável.
- Não houve teste em navegador real nem screenshot nesta auditoria, pois não houve mudança visual;
  a conformidade visual foi inferida de HTML/CSS, renderer e testes de DOM simulado.

## 9. Segurança

### 9.1 Conformidades

- Nenhum uso das APIs de injeção de HTML pesquisadas foi encontrado no frontend.
- Conteúdo externo é tratado como texto; testes usam payloads com HTML/script e confirmam que
  não são executados.
- O contrato público filtra posições/IDs internos dos impactos e contextos.
- Uploads usam nome-base (`Path(...).name`) e diretórios temporários separados, reduzindo path
  traversal e colisão.
- Cookie emitido usa `HttpOnly` e `SameSite=Strict`.
- Respostas recebem `Cache-Control: no-store, no-cache, must-revalidate`.
- O endpoint diário impõe limite de bytes e valida método/content-type/JSON/modelos.

### 9.2 Pontos de atenção/não conformidade

- Sessão fornecida pelo cliente, sem rotação, expiração ou limite (Alta).
- Uploads multipart e JSON legados sem tamanho máximo (Alta).
- Não há headers explícitos `Content-Security-Policy`, `X-Content-Type-Options`,
  `Referrer-Policy` ou proteção de framing (Média para exposição web).
- Mensagens de exceção internas chegam ao cliente (Média).
- O cache diário usa `pickle.load`. O arquivo é local e não vem diretamente do request, mas
  pickle executa objetos ao desserializar; permissões inadequadas do diretório/cache tornam isso
  um vetor local. Preferir formato não executável ou garantir diretório privado (Média).
- `_session_id` não valida comprimento/alfabeto do cookie; IDs arbitrariamente longos podem ser
  usados como chaves de memória (Média).
- Não há autenticação/autorização. Isso é reconhecido como não pronto para multiusuário, mas
  impede aprovação para exposição pública (Alta fora do uso local).

## 10. Performance

Não foram feitos benchmarks. A análise encontrou:

| Risco | Nível | Análise |
| --- | --- | --- |
| Stores de sessão sem limite | Alto | Crescimento permanente de mapas e objetos até reinício. |
| Corpo HTTP carregado integralmente | Alto | Multipart/JSON é lido inteiro em memória antes de validar/parser. |
| Recomposição do dashboard | Médio | Importação recompõe dashboard; GET recompõe; exclusão recompõe vazio. Aceitável no MVP, mas evitável com snapshot por sessão. |
| Cadeias de motores materializando iteráveis | Baixo | Cópias em tuplas/listas favorecem determinismo; com limites atuais são adequadas. |
| Relacionamentos posição × fato/evento | Médio | Vários motores fazem produto cartesiano conceitual; para carteiras pequenas é aceitável, mas deve ser monitorado ao ampliar fontes. |
| Dois fluxos diários | Médio | Reprocessamento e manutenção duplicada podem aumentar custo e inconsistência. |
| DOM reconstruído por resposta | Baixo | Listas são pequenas e limitadas; abordagem simples é adequada ao MVP. |

Não há evidência de gargalo crítico para o volume atual. Os riscos dominantes são limites de
entrada e retenção, não os loops determinísticos dos motores.

## 11. Testes

### 11.1 Cobertura observada

- Todos os oito motores possuem arquivos de teste dedicados.
- Contrato e fachada diária têm testes positivos, negativos e de incompatibilidade.
- HTTP possui testes para métodos, content types, JSON inválido, tamanho, erros internos,
  importação, leitura e isolamento de sessão.
- Frontend possui 80 testes sobre importação, contratos, renderização, HTML hostil, vazios,
  limites, erros e imutabilidade.
- Há testes integrados de estabilidade, endpoints legados, dashboard, connectors e patrimônio.

### 11.2 Lacunas prioritárias

1. Não existe limiar de cobertura automatizado; `pytest-cov` não está instalado.
2. Não há teste de ciclo de vida/TTL/limite de sessões, porque esses controles não existem.
3. Não há teste concorrente ou servidor multithread/multiprocesso.
4. Não há teste de upload acima de um limite nos endpoints multipart/legados.
5. Não há teste de fixação/rotação de cookie nem atributos `Secure`/expiração.
6. Não há teste de segurança para arquivo `pickle` adulterado.
7. Não há E2E em navegador real, auditoria de acessibilidade automatizada ou snapshot visual.
8. Não há teste de carga extrema (1.000 eventos × carteira grande) — benchmark não era exigido,
   mas um teste de limite funcional evitaria regressão.
9. A compatibilidade histórica é muito bem testada no frontend, mas faltam fixtures JSON
   versionadas completas para 1.0–1.5 como artefatos de contrato independentes.
10. Chamadas reais ao provedor externo não foram testadas nesta auditoria; os testes usam
    doubles, abordagem correta para determinismo, mas insuficiente para homologação operacional.

## 12. Documentação

### 12.1 Conforme

- Existem documentos específicos para `DataQualityEngine`, `DailyFactsEngine`,
  `MarketAgendaEngine`, `PortfolioImpactAssessmentEngine`, `DailyAnalysisEngine`,
  `DailyPriorityEngine`, `DecisionContextEngine` e `DailyExperienceOrchestrator`.
- `DAILY_API_CONTRACT.md` descreve claramente 1.5 e a evolução incremental.
- `ARCHITECTURE.md` explicita o fluxo oficial, responsabilidades, compatibilidade e MPU.
- `MVP_STATUS.md` declara limitações de NEI, persistência, autenticação e relatórios.

### 12.2 Atenção

- `docs/ROADMAP.md` ainda mostra apenas Sprints 16–23 e itens como Dashboard HTML em “próximos”,
  divergindo do `MVP_STATUS.md` e da implementação concluída.
- A especificação oficial da Home aparece em dois diretórios com nomes quase idênticos
  (`documentos -oficiais` e `documentos-oficiais`), além de PDF/DOCX; isso cria risco de fonte
  documental ambígua.
- Não há documentos individuais intitulados Marcos 21–29; a rastreabilidade depende do histórico
  Git e dos documentos de cada motor.
- A documentação de sessão não estabelece política de retenção, ameaça de fixação ou condição
  explícita de implantação exclusivamente local.
- A diferença entre contrato de dashboard `2.2` e contrato diário `1.5` é tecnicamente válida,
  mas pode confundir consumidores e deveria ter uma página curta de fronteiras/versionamento.

## 13. Experiência do usuário

### 13.1 Comparação com o fluxo aprovado

| Critério | Classificação | Resultado |
| --- | --- | --- |
| Abertura do Cockpit | Conforme | A Home carrega dashboard e experiência diária sem navegação adicional. |
| Sequência dos blocos | Conforme | Saudação/contexto antecedem fatos, prioridades e análises; extensões 1.1–1.4 aparecem depois. |
| Ocultação de vazios | Conforme | Blocos diários vazios são ocultados; apenas saudação/data permanecem quando tudo está vazio. |
| Consistência visual | Conforme | Componentes compartilham grid, painéis, hierarquia e badges; responsividade está definida. |
| Abrir → entender → decidir | Atenção | O núcleo diário cumpre o fluxo, mas importação, cards executivos genéricos, módulos e configuração competem por atenção na mesma Home. |
| Privacidade financeira | Conforme | Valores ficam ocultos inicialmente e o usuário controla Mostrar/Ocultar. |
| Resumo executivo ≤ 10 linhas | Atenção | Motores limitam itens, mas a página completa pode mostrar diversos blocos aditivos; não há verificação automática de dez linhas visuais. |

### 13.2 Divergências registradas

1. A tela principal é mais ampla que um Cockpit diário: inclui importação, preview, módulos e
   configuração. Isso é útil operacionalmente, mas reduz a simplicidade do primeiro olhar.
2. A regra “resumo executivo no máximo 10 linhas” não possui garantia semântica/visual testável;
   existem limites por coleção, não um orçamento global de linhas.
3. O status visual “Sistema operacional” é estático e pode sugerir saúde mesmo quando fonte
   externa ou backend diário falhou; os erros locais são mostrados, mas o rótulo global não deriva
   de health check.
4. Sem navegador real nesta auditoria, contraste, foco, leitor de tela e comportamento em dispositivos
   reais permanecem riscos não validados.

## 14. Não conformidades priorizadas

### Crítica

**Nenhuma não conformidade crítica foi comprovada** no escopo e ambiente atual. Não foram
observados mistura JOLIKA/NEI, execução de HTML externo, corrupção de contrato ou falha da suíte.

### Alta

#### NC-A01 — Sessões sem expiração, limite ou coleta

- **Descrição:** os três stores globais mantêm estado por ID indefinidamente e não existe TTL,
  cota de sessões ou limpeza coordenada.
- **Impacto:** esgotamento gradual de memória, dados retidos além do necessário e impossibilidade
  de operação previsível sob múltiplos clientes.
- **Recomendação:** implementar store único com TTL/cota e operação de limpeza de todos os domínios;
  documentar retenção e garantir testes de expiração. Para produção, usar armazenamento de sessão
  apropriado ao modelo de implantação.

#### NC-A02 — Fixação de sessão e ID não validado

- **Descrição:** qualquer cookie não vazio é aceito; numa importação o servidor reutiliza esse
  valor em vez de emitir/rotacionar um ID próprio.
- **Impacto:** um identificador conhecido pode ser fixado antes de dados serem importados; valores
  arbitrários e longos também ampliam abuso do store.
- **Recomendação:** aceitar somente IDs emitidos e existentes, rotacionar na criação/importação,
  validar formato/tamanho, usar comparação/política consistente e expirar o cookie.

#### NC-A03 — Entradas HTTP sem limite uniforme

- **Descrição:** somente o endpoint diário tem limite explícito. Multipart e JSON/base64 legados
  leem o corpo completo conforme `Content-Length`.
- **Impacto:** consumo excessivo de memória/disco e indisponibilidade por request grande.
- **Recomendação:** impor limite global antes da leitura, limites específicos por tipo/quantidade de
  arquivo e rejeição 413 consistente; validar também conteúdo decodificado.

#### NC-A04 — Sem autenticação para implantação exposta

- **Descrição:** qualquer cliente com acesso ao servidor pode ler/alterar dados associados ao cookie.
- **Impacto:** falta de controle de acesso e confidencialidade em ambiente compartilhado.
- **Recomendação:** manter o MVP restrito a ambiente local/controlado até introduzir autenticação,
  autorização, TLS e política de sessão. Esta lacuna já é reconhecida no status do MVP.

### Média

#### NC-M01 — Dois fluxos de composição diária

- **Descrição:** dashboard/orquestrador oficial e fachada versionada recompõem conceitos próximos
  por caminhos/modelos diferentes.
- **Impacto:** divergência funcional futura, processamento duplicado e maior custo de mudança.
- **Recomendação:** na estabilização, documentar uma matriz clara de ownership e fazer a camada de
  compatibilidade projetar uma única saída canônica, sem refatoração ampla prematura.

#### NC-M02 — Formatos de erro HTTP inconsistentes

- **Descrição:** coexistem envelope 1.5, `{ok,error}`, `{error}` e HTML de `send_error`.
- **Impacto:** tratamento duplicado no cliente, mensagens imprevisíveis e manutenção difícil.
- **Recomendação:** padronizar JSON para `/api/*`, preservando contratos legados por adaptadores e
  versionamento explícito.

#### NC-M03 — Detalhes internos em mensagens de exceção

- **Descrição:** vários handlers devolvem `str(exc)` diretamente.
- **Impacto:** possível exposição de nomes de arquivo, parser, estrutura ou configuração.
- **Recomendação:** registrar detalhes no servidor e retornar código/mensagem pública estável.

#### NC-M04 — Desserialização `pickle` no cache

- **Descrição:** cache local executa `pickle.load` em arquivo persistido.
- **Impacto:** alteração local do arquivo pode provocar execução de código na próxima leitura.
- **Recomendação:** usar serialização não executável ou restringir e verificar rigorosamente o
  diretório/arquivo; nunca compartilhar o cache com conteúdo controlável por usuário.

#### NC-M05 — Hardening de headers incompleto

- **Descrição:** cache headers existem, mas faltam CSP, nosniff, frame policy e referrer policy.
- **Impacto:** defesa em profundidade reduzida em implantação web.
- **Recomendação:** definir headers no servidor/reverse proxy e testar sua presença.

#### NC-M06 — Validador público parcialmente superficial

- **Descrição:** `validate_daily_api_response_payload` não valida recursivamente todos os campos.
- **Impacto:** payload manual malformado pode ser considerado válido pela função, embora o produtor
  dataclass seja mais rigoroso.
- **Recomendação:** esclarecer que a função é verificação estrutural mínima ou reutilizar schemas
  dos modelos para validação profunda, sem duplicar enums.

### Baixa

#### NC-B01 — Roadmap desatualizado

- **Impacto:** leitura incorreta do estágio do projeto.
- **Recomendação:** alinhar roadmap, status e histórico após a decisão de estabilização.

#### NC-B02 — Fonte documental duplicada

- **Impacto:** risco de editar/consultar a cópia errada da especificação da Home.
- **Recomendação:** declarar uma cópia canônica e arquivar as demais sem apagá-las inadvertidamente.

#### NC-B03 — Nomes de motores ambíguos

- **Impacto:** imports/aliases propensos a erro (`DailyPriorityEngine`, impactos, orquestradores).
- **Recomendação:** documentar nomes canônicos e de compatibilidade; renomear somente numa etapa
  futura versionada, caso o benefício supere o risco.

#### NC-B04 — Saúde global estática na interface

- **Impacto:** indicação visual pode não refletir falha de integração.
- **Recomendação:** remover promessa operacional estática ou ligá-la a estado já disponível, em
  marco funcional futuro.

## 15. Principais conformidades

1. Separação patrimonial está presente no modelo e nas validações; não foi encontrada mistura
   implícita entre JOLIKA e NEI.
2. UBS e Santander permanecem identificáveis antes da consolidação.
3. Motores não conhecem HTTP/DOM e trabalham sobre estruturas canônicas.
4. Resultados são determinísticos, ordenados e limitados; relógios são injetáveis onde necessário.
5. Fatos, impactos e contextos preservam evidência/fatores sem expor posições internas completas.
6. Evolução 1.0–1.5 é aditiva e possui testes de regressão no frontend.
7. DOM é construído de forma segura, sem interpretação de strings externas como HTML.
8. Valores financeiros ficam ocultos por padrão e há controle explícito de exibição.
9. Estados vazios e falhas não fabricam recomendações nem derrubam silenciosamente a página.
10. A suíte automatizada é ampla e passou integralmente nesta baseline.
11. Arquitetura e limitações de produção estão, em grande parte, explicitadas.
12. A implementação evita microserviços ou infraestrutura excessiva para o estágio atual.

## 16. Dívida técnica não impeditiva

- Instalar/configurar cobertura com limiar por módulo e relatório em CI.
- Criar fixtures JSON congeladas para contratos 1.0–1.5.
- Adicionar E2E de navegador, acessibilidade e viewport móvel.
- Consolidar nomenclatura/ownership dos motores antigos e novos.
- Indexar relações de ativos caso carteira/fatos cresçam materialmente.
- Cachear snapshot de dashboard por versão de sessão somente se medição justificar.
- Atualizar roadmap e índice de documentos.
- Documentar diferença entre dashboard 2.2 e daily 1.5.
- Adicionar logging estruturado com correlation ID sem dados financeiros.
- Definir política de retenção, backup e descarte antes de persistência real.
- Verificar limites visuais do resumo executivo com teste funcional próprio.
- Homologar periodicamente o provedor externo em ambiente controlado.

## 17. Conclusão técnica

# MVP APROVADO COM RESSALVAS

A decisão é baseada nas evidências: motores e contratos são sólidos para o escopo, o fluxo
principal funciona, o frontend é seguro contra injeção DOM nas rotas auditadas e **todos os 614
testes executados passaram**. Não há evidência de defeito crítico que impeça uso diário local.

As ressalvas são objetivas: a implementação atual de sessão não possui controles mínimos de ciclo
de vida e aceita identificador fornecido pelo cliente; uploads não têm limite uniforme; e não há
autenticação. Portanto:

- **aprovado** para uso diário em ambiente local, single-process e com acesso controlado;
- **não aprovado para exposição pública ou uso multiusuário** antes de corrigir NC-A01 a NC-A04;
- recomenda-se que a próxima etapa seja **estabilização final**, priorizando sessão, limites de
  entrada, padronização de erros e hardening HTTP, sem adicionar complexidade funcional.

Essa conclusão não pressupõe capacidades futuras e não depende de preferência arquitetural; ela
decorre exclusivamente do código, documentação e testes observados na baseline auditada.
