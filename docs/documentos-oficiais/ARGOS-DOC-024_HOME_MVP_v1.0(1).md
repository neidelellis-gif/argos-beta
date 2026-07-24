# ARGOS

# DOCUMENTO OFICIAL Nº 024

# ESPECIFICAÇÃO FUNCIONAL OFICIAL

## HOME DO ARGOS (MVP v1.0)

**Versão:** 1.0  
**Status:** Documento Oficial  
**Objetivo:** Base funcional para implementação do Sprint 1.5

---

# PARTE 1

## Capítulo 1
### Finalidade

A Home do ARGOS não é uma página inicial.

Também não é um dashboard.

Muito menos um conjunto de gráficos financeiros.

A Home é o Centro de Comando Executivo do patrimônio do usuário.

Sua finalidade é responder imediatamente à pergunta:

> "O que realmente precisa da minha atenção hoje?"

Todo o restante do sistema existe para responder essa pergunta da forma mais rápida, objetiva e inteligente possível.

## Capítulo 2
### Princípio Fundamental

O ARGOS não foi criado para gerar análises.

Análises são apenas matéria-prima.

O verdadeiro objetivo do ARGOS é transformar informações dispersas em decisões executivas.

Portanto:

Dados

↓

Informações

↓

Análises

↓

Conclusões

↓

Decisões

↓

Plano de Ação

↓

Execução

Toda a Home será construída para conduzir o usuário por esse fluxo.

## Capítulo 3
### Filosofia da Home

Ao abrir o ARGOS o usuário não deseja estudar.

Ele deseja compreender.

Não deseja procurar.

Deseja encontrar.

Não deseja navegar.

Deseja decidir.

Por isso a Home obedecerá cinco princípios.

#### 3.1 Clareza

Nada poderá competir pela atenção.

Cada informação deverá possuir um propósito.

#### 3.2 Prioridade

Tudo será organizado pela importância.

Nunca pela origem dos dados.

Nem pela ordem dos módulos.

#### 3.3 Contexto

Toda informação deverá responder:

Por que isso importa hoje?

#### 3.4 Ação

Toda conclusão importante deverá possuir um próximo passo.

Nunca apenas um diagnóstico.

#### 3.5 Simplicidade

A experiência deverá transmitir serenidade.

Mesmo quando houver dezenas de eventos acontecendo simultaneamente.

## Capítulo 4
### Objetivo da Sessão

Ao terminar de utilizar a Home, o usuário deverá ser capaz de responder cinco perguntas.

#### Pergunta 1

O patrimônio está saudável hoje?

#### Pergunta 2

Existe algum risco relevante?

#### Pergunta 3

Existe alguma oportunidade importante?

#### Pergunta 4

Existe alguma decisão pendente?

#### Pergunta 5

Qual deverá ser minha agenda hoje?

Se essas cinco respostas estiverem claras, a Home cumpriu seu papel.

## Capítulo 5
### Abertura do ARGOS

Ao iniciar o sistema, nenhuma análise deverá ser apresentada imediatamente.

Primeiro o ARGOS deverá contextualizar o momento.

Exemplo:

> Bom dia, Nei.
>
> Hoje é terça-feira.
>
> Mercados americanos abrirão em 2 horas.
>
> Existem 4 assuntos relevantes para hoje.
>
> Duas decisões exigem atenção.
>
> Uma oportunidade foi identificada.
>
> Nenhum risco crítico foi detectado.

Esse bloco possui uma única função:

Preparar o usuário.

## Capítulo 6
### Ordem de Construção da Tela

A Home será organizada de cima para baixo.

Sempre nesta sequência.

1. Cabeçalho Executivo
2. Resumo do Dia
3. Prioridades
4. Cockpit Executivo
5. Agenda Inteligente
6. Ações Recomendadas
7. Navegação para os módulos

Essa ordem não poderá ser alterada sem justificativa funcional.

## Capítulo 7
### Cabeçalho Executivo

O cabeçalho deverá ocupar pouca altura.

Ele não existe para impressionar.

Existe para orientar.

Conterá:

- saudação;
- data;
- horário;
- ambiente ativo (Pessoa Física ou Jolika);
- indicador de atualização dos dados.

Não deverá conter gráficos.

Nem notícias.

Nem menus complexos.

## Capítulo 8
### Resumo do Dia

Logo abaixo do cabeçalho aparecerá um resumo executivo.

Não serão exibidos números.

Serão exibidas conclusões.

Exemplo:

- Mercado favorável ao risco.
- Nenhum rebalanceamento urgente.
- Caixa acima da estratégia definida.
- Agenda com três decisões importantes.
- Uma oportunidade em acompanhamento.

Cada frase poderá ser expandida posteriormente.

## Capítulo 9
### Prioridades

As prioridades serão organizadas por níveis.

#### Nível 1

Exigem decisão hoje.

#### Nível 2

Merecem acompanhamento.

#### Nível 3

Informações úteis.

Nunca haverá mais de cinco prioridades de Nível 1 simultaneamente.

Caso existam mais de cinco, o ARGOS deverá consolidá-las por tema.

## Capítulo 10
### Filosofia do Cockpit Executivo

O Cockpit não mostrará dados.

Mostrará conclusões.

Os dados estarão disponíveis apenas quando o usuário desejar aprofundar a análise.

Isso evita sobrecarga cognitiva e mantém o foco na tomada de decisão.

### Encerramento da Parte 1

A Parte 1 estabelece os fundamentos da Home do ARGOS:

- finalidade;
- princípios;
- objetivo da sessão;
- abertura do sistema;
- estrutura macro da tela;
- organização das prioridades;
- filosofia do Cockpit Executivo.

Na Parte 2, será especificado detalhadamente o Cockpit Executivo, incluindo seus componentes, a lógica de apresentação das informações, a Agenda Inteligente e o fluxo operacional diário do usuário.

---

# PARTE 2

## Capítulo 11
### O Cockpit Executivo

O Cockpit Executivo é o núcleo do ARGOS.

Todo o restante do sistema existe para alimentá-lo.

Ele não é um painel financeiro.

Não é um dashboard.

Não é um relatório.

É um Centro de Decisão.

Sua função é transformar milhares de informações em poucas decisões objetivas.

O Cockpit deverá responder continuamente:

> "Se eu tivesse apenas cinco minutos hoje, o que realmente deveria saber?"

## Capítulo 12
### Estrutura Geral do Cockpit

O Cockpit será dividido em seis blocos.

Sempre na mesma ordem.

1. Estado Geral
2. Alertas
3. Oportunidades
4. Agenda
5. Acompanhamentos
6. Navegação

Essa sequência representa o fluxo natural de decisão do usuário.

Primeiro entende-se a situação.

Depois identificam-se problemas.

Em seguida oportunidades.

Depois define-se o plano do dia.

Por último ocorre a navegação.

Nunca o contrário.

## Capítulo 13
### Estado Geral

Este é o bloco mais importante do sistema.

Ele deverá responder imediatamente:

Como está meu patrimônio neste momento?

Não serão exibidos dezenas de indicadores.

Apenas aqueles que alteram decisões.

Exemplos:

- patrimônio consolidado;
- liquidez disponível;
- exposição ao risco;
- concentração;
- alocação estratégica;
- tendência geral.

Cada indicador possuirá uma classificação.

- Excelente
- Boa
- Atenção
- Crítica

O usuário deverá compreender a situação em poucos segundos.

## Capítulo 14
### Alertas

Alertas representam acontecimentos que exigem atenção.

Não são notícias.

São eventos relevantes para o patrimônio.

Exemplos:

- concentração excessiva;
- excesso de caixa;
- liquidez insuficiente;
- vencimentos próximos;
- ativos fora da estratégia;
- alteração significativa de cenário;
- documentação pendente;
- atualização necessária.

Cada alerta possuirá:

- prioridade;
- motivo;
- impacto;
- recomendação;
- botão "Ver análise".

## Capítulo 15
### Oportunidades

O ARGOS não deverá apenas identificar problemas.

Ele deverá procurar oportunidades.

Exemplos:

- ativo atingiu faixa de compra;
- oportunidade de rebalanceamento;
- benefício tributário;
- renda fixa mais eficiente;
- janela para realização parcial;
- ETF estratégico;
- oportunidade internacional.

Toda oportunidade responderá quatro perguntas.

- Por que surgiu?
- Qual benefício esperado?
- Qual risco?
- Qual ação sugerida?

## Capítulo 16
### Agenda Inteligente

A Agenda Inteligente é consequência das análises.

Ela nunca será preenchida manualmente pelo sistema.

Ela será construída automaticamente.

Exemplo:

09:00

Revisar posição em Bitcoin

↓

10:30

Enviar documentação UBS

↓

11:00

Avaliar reforço em ETF AIQ

↓

14:00

Conferir fechamento da renda fixa

↓

17:00

Executar rebalanceamento aprovado

Cada item deverá possuir origem rastreável.

Nenhuma tarefa poderá aparecer sem justificativa.

## Capítulo 17
### Acompanhamentos

Nem tudo exige ação.

Alguns assuntos apenas precisam ser monitorados.

Exemplos:

- CPI americano;
- decisão do FED;
- votação no Congresso;
- balanço da Nvidia;
- resultados de ETF;
- janela tributária.

Esses eventos permanecerão neste bloco até perderem relevância.

## Capítulo 18
### Filosofia dos Cards

Todo bloco do Cockpit utilizará Cards.

Cada Card representa um assunto.

Nunca um módulo.

Um assunto poderá envolver:

- investimentos;
- empresa;
- imóveis;
- impostos;
- seguros;
- planejamento.

O usuário pensa por assuntos.

Não por sistemas.

## Capítulo 19
### Estrutura de um Card

Todo Card deverá possuir exatamente cinco elementos.

1. Título.
2. Resumo executivo.
3. Impacto.
   - Baixo
   - Médio
   - Alto
   - Crítico
4. Próxima ação sugerida.
5. Botão: Ver análise completa

O detalhamento sempre ocorrerá fora da Home.

## Capítulo 20
### Expansão Progressiva

A Home nunca deverá mostrar tudo.

Ela mostrará apenas o necessário.

Cada Card poderá ser expandido.

Resumo

↓

Detalhes

↓

Análise

↓

Documentos

↓

Histórico

Esse princípio evita excesso de informação.

## Capítulo 21
### Hierarquia Visual

A interface obedecerá quatro níveis.

#### Nível 1

Decidir agora.

#### Nível 2

Acompanhar hoje.

#### Nível 3

Consultar quando necessário.

#### Nível 4

Histórico.

O usuário nunca deverá procurar uma decisão urgente no histórico.

## Capítulo 22
### Filosofia da Navegação

A Home não substituirá os módulos.

Ela conduzirá até eles.

O Cockpit responde:

"O que?"

O módulo responde:

"Como?"

Exemplo.

Cockpit

↓

Existe excesso de caixa.

↓

Clique.

↓

Módulo Patrimonial.

↓

Análise detalhada.

↓

Plano de rebalanceamento.

## Capítulo 23
### Ambiente Patrimonial

O ARGOS deverá trabalhar com ambientes independentes.

Exemplo.

Pessoa Física

↓

Jolika

↓

Consolidado

Trocar de ambiente nunca deverá reiniciar o sistema.

Apenas atualizar o contexto.

## Capítulo 24
### Continuidade

Ao finalizar a utilização da Home o usuário deverá sentir que:

- compreendeu sua situação;
- sabe quais decisões precisa tomar;
- conhece sua agenda;
- sabe onde aprofundar cada assunto.

Se isso não ocorrer, a Home falhou.

### Encerramento da Parte 2

A Parte 2 define o funcionamento do Cockpit Executivo, incluindo:

- sua estrutura;
- organização em blocos;
- filosofia dos Cards;
- Agenda Inteligente;
- lógica de navegação;
- integração com os ambientes patrimoniais.

Na Parte 3, será especificada a integração da Home com os módulos existentes do ARGOS, os estados da interface, as regras de interação e os fluxos completos de navegação entre Cockpit, análises e execução.

---

# PARTE 3

## Capítulo 25
### A Home como Orquestradora do Sistema

A Home não será proprietária das informações.

Ela será a orquestradora de todo o ARGOS.

Cada módulo continuará responsável pelos seus próprios dados, análises e processos.

A Home apenas responderá três perguntas:

- O que aconteceu?
- O que isso significa?
- O que devo fazer?

Toda informação detalhada permanecerá no módulo de origem.

## Capítulo 26
### Arquitetura Funcional

A Home será composta por três camadas.

CAMADA 1

Resumo Executivo

↓

CAMADA 2

Decisão

↓

CAMADA 3

Execução

#### Camada 1

Apresenta somente conclusões.

#### Camada 2

Permite compreender o problema.

#### Camada 3

Executa a ação.

O usuário jamais deverá executar uma ação sem antes entender sua justificativa.

## Capítulo 27
### Integração com os Módulos

Cada módulo do ARGOS terá uma função clara dentro da Home.

#### Patrimônio

Responsável por:

- patrimônio consolidado;
- liquidez;
- concentração;
- exposição;
- evolução.

#### Consolidação

Responsável por:

- unificação das posições;
- sincronização entre instituições;
- consolidação dos ambientes.

#### Upload

Responsável por:

- novos documentos;
- extratos;
- notas;
- comprovantes;
- arquivos pendentes.

#### Conectores

Responsáveis pela atualização automática dos dados.

Nunca deverão aparecer como protagonistas da interface.

O usuário quer saber o resultado.

Não o mecanismo.

#### Agenda

Responsável pela organização das atividades do dia.

#### Inteligência

Responsável por:

- riscos;
- oportunidades;
- recomendações;
- cenários.

## Capítulo 28
### Estados da Home

A Home possuirá estados distintos.

Cada estado altera apenas o conteúdo.

Nunca a estrutura.

#### Estado 1

Primeiro acesso.

O sistema ainda não possui dados suficientes.

A interface deverá orientar o usuário.

Jamais ficará vazia.

#### Estado 2

Importação em andamento.

O usuário deverá acompanhar o progresso.

Sem interromper a utilização do sistema.

#### Estado 3

Atualização concluída.

O Cockpit será recalculado.

Sem necessidade de reiniciar.

#### Estado 4

Uso diário.

Estado padrão.

#### Estado 5

Alerta crítico.

Quando houver uma situação prioritária.

O sistema reorganizará automaticamente a Home.

#### Estado 6

Modo Consulta.

Nenhuma decisão pendente.

A interface torna-se predominantemente informativa.

## Capítulo 29
### Atualização Dinâmica

Sempre que uma informação relevante mudar:

O ARGOS atualizará somente o componente necessário.

Jamais recarregará toda a página.

Isso reduz distrações.

## Capítulo 30
### Filosofia da Navegação

Todo clique deverá obedecer à mesma lógica.

Resumo

↓

Explicação

↓

Análise

↓

Decisão

↓

Execução

Nunca:

Resumo

↓

Tabela

↓

Planilha

↓

Documento

↓

Confusão

## Capítulo 31
### Fluxo de Decisão

Cada assunto seguirá exatamente este ciclo.

Evento

↓

Análise

↓

Conclusão

↓

Recomendação

↓

Decisão

↓

Execução

↓

Monitoramento

O ARGOS deverá saber em qual etapa cada assunto se encontra.

## Capítulo 32
### Centro de Decisão

O Centro de Decisão será o mecanismo responsável por consolidar todas as recomendações.

Ele responderá:

- decisões aguardando aprovação;
- decisões em execução;
- decisões concluídas;
- decisões adiadas.

O usuário poderá encerrar seu dia sabendo exatamente o que ficou pendente.

## Capítulo 33
### Histórico de Decisões

O histórico não registrará apenas ações executadas.

Também registrará:

- motivo;
- cenário;
- premissas;
- riscos considerados;
- expectativa de resultado.

No futuro, o ARGOS poderá comparar:

o que foi decidido versus o que realmente aconteceu.

Esse será um dos principais ativos de inteligência do sistema.

## Capítulo 34
### Filosofia das Recomendações

O ARGOS nunca dará ordens.

Ele fará recomendações fundamentadas.

Cada recomendação conterá:

- contexto;
- justificativa;
- benefícios;
- riscos;
- impacto esperado;
- confiança da recomendação.

A decisão final sempre será do usuário.

## Capítulo 35
### Princípio da Não Repetição

Uma informação nunca deverá aparecer duplicada.

Exemplo.

Se um alerta já está visível no Cockpit:

Ele não deverá ocupar novamente espaço na Agenda.

A Agenda conterá apenas a ação decorrente desse alerta.

## Capítulo 36
### Inteligência Contextual

O ARGOS deverá compreender o contexto antes de priorizar.

Exemplos.

Uma posição concentrada pode ser aceitável:

- durante uma estratégia previamente definida;
- durante um rebalanceamento;
- durante um ciclo específico do mercado.

Portanto.

O sistema nunca avaliará indicadores isoladamente.

Sempre avaliará contexto.

## Capítulo 37
### Fluxo entre Home e Módulos

HOME

↓

Resumo Executivo

↓

Clique

↓

Módulo Especializado

↓

Análise

↓

Recomendação

↓

Retorno à Home

A Home será sempre o ponto de partida e de retorno.

## Capítulo 38
### Critérios de Performance

A Home deverá transmitir sensação de velocidade.

Mesmo quando houver milhares de registros.

Para isso:

- carregar primeiro o essencial;
- atualizar componentes em paralelo;
- priorizar informações críticas;
- adiar conteúdos secundários.

A percepção de rapidez faz parte da experiência do usuário.

## Capítulo 39
### Continuidade Operacional

O usuário nunca deverá perder o contexto.

Ao retornar à Home, o ARGOS deverá lembrar:

- ambiente ativo;
- filtros;
- análises abertas;
- tarefas em andamento;
- decisões pendentes.

O sistema continuará exatamente do ponto onde o usuário parou.

## Capítulo 40
### Encerramento Operacional da Home

Ao finalizar o uso da Home, o usuário deverá ter:

- compreendido o estado do patrimônio;
- identificado riscos;
- identificado oportunidades;
- definido prioridades;
- organizado sua agenda;
- iniciado ou concluído as decisões relevantes.

A Home terá cumprido sua função quando o usuário puder fechar o ARGOS com a sensação de que seu dia foi planejado de forma objetiva e consciente.

### Encerramento da Parte 3

A Parte 3 estabelece como a Home se integra ao restante do ARGOS:

- arquitetura funcional;
- integração entre módulos;
- estados da interface;
- fluxo de decisão;
- Centro de Decisão;
- Histórico de Decisões;
- regras de navegação;
- princípios de atualização e continuidade.

Na Parte 4, serão definidos os critérios de qualidade da interface, as regras de negócio da Home, os cenários excepcionais, os critérios de aceite do Sprint 1.5 e as diretrizes finais para implementação do MVP.

---

# PARTE 4

## Capítulo 41
### Princípio da Experiência

O ARGOS não foi desenvolvido para demonstrar tecnologia.

Foi desenvolvido para aumentar a capacidade de decisão do usuário.

Toda decisão de interface deverá responder primeiro:

> "Isso ajuda o usuário a decidir melhor?"

Se a resposta for negativa, a funcionalidade deverá ser revista.

## Capítulo 42
### Critérios de Qualidade da Home

A Home somente poderá ser considerada pronta quando atender simultaneamente aos seguintes critérios.

#### Clareza

O usuário compreende imediatamente a situação.

#### Rapidez

Em menos de 30 segundos o usuário identifica:

- riscos;
- oportunidades;
- prioridades.

#### Objetividade

Nenhum elemento visual poderá existir apenas para decoração.

Todo componente deverá possuir função executiva.

#### Consistência

A mesma informação deverá possuir sempre a mesma representação.

Exemplo.

Se um alerta crítico utiliza vermelho:

Ele nunca aparecerá em amarelo em outro módulo.

#### Continuidade

O usuário nunca deverá perder o contexto durante a navegação.

## Capítulo 43
### Regras Visuais

Toda a interface seguirá regras únicas.

#### Espaçamento

A interface deverá transmitir organização.

Nunca excesso de elementos.

#### Hierarquia

O olhar deverá percorrer naturalmente:

Cabeçalho

↓

Resumo

↓

Prioridades

↓

Cockpit

↓

Agenda

↓

Navegação

#### Contraste

O contraste será utilizado para destacar decisões.

Nunca apenas estética.

#### Cores

As cores deverão representar significado.

Nunca gosto pessoal.

Exemplo.

Verde.

Boa situação.

Amarelo.

Atenção.

Vermelho.

Prioridade.

Cinza.

Informação.

## Capítulo 44
### Regras de Negócio

A Home obedecerá regras permanentes.

#### Regra 1

Nunca apresentar uma informação sem contexto.

#### Regra 2

Nunca recomendar uma ação sem justificativa.

#### Regra 3

Nunca esconder um risco relevante.

#### Regra 4

Nunca gerar tarefas duplicadas.

#### Regra 5

Nunca apresentar indicadores conflitantes.

#### Regra 6

Sempre informar a origem da recomendação.

## Capítulo 45
### Tratamento de Cenários Excepcionais

O ARGOS deverá prever situações incomuns.

#### Dados indisponíveis

A interface continuará funcionando.

Informará claramente quais informações ainda estão sendo carregadas.

#### Atualização interrompida

O usuário poderá continuar utilizando a versão anterior dos dados.

#### Conector indisponível

O problema será tratado como operacional.

Nunca como erro do usuário.

#### Falha de consolidação

O sistema informará:

- instituição afetada;
- impacto;
- ação sugerida.

## Capítulo 46
### Modo Executivo

Sempre que o usuário abrir o ARGOS pela primeira vez no dia, a Home entrará automaticamente em Modo Executivo.

Esse modo elimina distrações.

Mostra apenas:

- resumo do dia;
- prioridades;
- decisões;
- agenda.

Todo o restante permanece acessível, porém recolhido.

## Capítulo 47
### Modo Exploração

Quando o usuário desejar aprofundar um assunto, a Home entrará em Modo Exploração.

Nesse modo:

- gráficos completos;
- documentos;
- análises;
- históricos;
- indicadores técnicos.

A mudança entre os modos deverá ser natural e reversível.

## Capítulo 48
### Critérios de Aceite do Sprint 1.5

A implementação da nova Home somente será considerada concluída quando atender aos seguintes critérios.

#### Estrutura

- Cabeçalho Executivo implementado.
- Resumo do Dia implementado.
- Prioridades implementadas.
- Cockpit Executivo implementado.
- Agenda Inteligente implementada.
- Navegação preservada.

#### Funcionalidade

- Nenhuma funcionalidade existente removida.
- Integração com backend funcionando.
- Atualização dinâmica funcionando.
- Ambientes patrimoniais preservados.

#### Experiência

O usuário deverá conseguir abrir o ARGOS e compreender sua situação patrimonial sem navegar para nenhum outro módulo.

## Capítulo 49
### Critérios de Evolução

Após a entrada em produção do MVP.

Nenhuma alteração significativa será realizada baseada apenas em opinião.

Toda evolução deverá seguir o ciclo.

Uso Real

↓

Observação

↓

Identificação

↓

Discussão

↓

Aprovação

↓

Implementação

Este princípio já foi aprovado anteriormente para todo o projeto ARGOS.

## Capítulo 50
### Encerramento da Especificação Funcional

A Home do ARGOS deixa de ser definida como uma página inicial.

Passa a ser oficialmente definida como:

> O Centro de Comando Executivo do usuário.

Seu propósito é transformar um grande volume de informações patrimoniais, financeiras, empresariais e operacionais em decisões objetivas, priorizadas e acionáveis.

Todos os módulos do ARGOS existirão para alimentar essa experiência.

Nenhum módulo substituirá a Home.

Nenhuma Home substituirá os módulos.

Cada componente terá responsabilidade clara, preservando a simplicidade para o usuário e a escalabilidade da plataforma.

### Encerramento da Parte 4

Com esta parte, fica concluída a especificação funcional da experiência da Home e definidos:

- princípios de UX;
- regras visuais;
- regras de negócio;
- cenários excepcionais;
- modos de operação;
- critérios de aceite do Sprint 1.5;
- critérios oficiais de evolução do produto.

Na Parte 5, será feito o mapeamento entre esta especificação e a implementação técnica, definindo exatamente como cada elemento será incorporado à base atual do ARGOS, quais arquivos serão alterados, quais componentes serão reutilizados e qual será a sequência segura de desenvolvimento do Sprint 1.5. Isso servirá como ponte direta entre o documento funcional e o código-fonte.

---

# PARTE 5

## Capítulo 51
### Objetivo da Implementação

Esta parte estabelece a ligação oficial entre a especificação funcional e a implementação técnica.

Até este momento definimos o que o ARGOS deve fazer.

A partir daqui definimos como implementar, preservando integralmente a base existente.

Este documento passa a ser a referência obrigatória para qualquer alteração futura na Home.

## Capítulo 52
### Princípio da Evolução

O ARGOS não será reescrito.

Será evoluído.

Todo desenvolvimento deverá obedecer ao seguinte princípio:

Código existente

↓

Compreensão

↓

Integração

↓

Validação

↓

Nova funcionalidade

Nunca:

Código existente

↓

Substituição

↓

Retrabalho

Este princípio é permanente.

## Capítulo 53
### Arquivos que serão preservados

O Sprint 1.5 trabalhará sobre os arquivos existentes.

Nenhum deles será substituído integralmente.

Arquivos principais:

- frontend/index.html
- frontend/app.js
- frontend/style.css
- backend/server.py

Os demais módulos permanecerão responsáveis por suas funções atuais.

## Capítulo 54
### Estratégia de Implementação

A implementação ocorrerá em cinco etapas.

#### Etapa 1

Reorganização da Home.

Sem alterar funcionalidades.

Apenas estrutura visual.

#### Etapa 2

Integração dos módulos existentes.

Tudo que já existe será conectado ao Cockpit.

#### Etapa 3

Implantação dos novos componentes.

Resumo.

Prioridades.

Agenda.

Cards.

#### Etapa 4

Integração dinâmica.

Atualizações.

Eventos.

Estado dos módulos.

#### Etapa 5

Refinamento.

UX.

Performance.

Pequenos ajustes.

## Capítulo 55
### Componentes Reutilizados

O inventário técnico identificou componentes que já existem.

Eles deverão ser reutilizados.

Exemplos.

- Cockpit JSON
- Facts JSON
- Upload
- Consolidação
- Conectores
- Servidor
- Ambientes Patrimoniais

Não haverá duplicação.

## Capítulo 56
### Novos Componentes

Os seguintes componentes serão adicionados.

- Cabeçalho Executivo
- Resumo do Dia
- Painel de Prioridades
- Agenda Inteligente
- Centro de Decisão
- Cards Executivos
- Acompanhamentos
- Barra de Estado

Todos serão independentes.

## Capítulo 57
### Arquitetura da Home

A Home será dividida em componentes.

Home

│

├── ExecutiveHeader

├── DailySummary

├── PrioritiesPanel

├── ExecutiveCockpit

├── AgendaPanel

├── DecisionCenter

├── MonitoringPanel

└── NavigationPanel

Essa divisão reduz o crescimento do app.js.

## Capítulo 58
### Fluxo de Dados

O backend continuará sendo a única fonte oficial.

Fluxo.

Conectores

↓

Consolidação

↓

Backend

↓

JSON

↓

Frontend

↓

Cockpit

A Home nunca calculará regras de negócio.

Ela apenas apresentará resultados.

## Capítulo 59
### Responsabilidades

#### Backend

- cálculo;
- consolidação;
- validação;
- integração.

#### Frontend

- apresentação;
- interação;
- navegação.

#### Home

- orquestração.

#### Módulos

- profundidade analítica.

## Capítulo 60
### Princípios de Desenvolvimento

Todo Sprint deverá respeitar os princípios aprovados durante este projeto.

#### Regra 001

Compreender antes de alterar.

#### Regra 002

Preservar funcionalidades existentes.

#### Regra 003

Honestidade técnica.

Nunca afirmar que algo foi implementado ou testado sem realmente ter sido.

#### Regra 004

Após aprovação.

Executar.

Não rediscutir.

#### Regra 005 (nova)

Todo Sprint deverá terminar com um produto utilizável.

Mesmo que incompleto.

Nunca entregar código parcialmente quebrado.

## Capítulo 61
### Critérios para Encerramento do Sprint 1.5

O Sprint somente será encerrado quando:

- nova Home implementada;
- Home funcional;
- navegação preservada;
- integração com backend funcionando;
- Cockpit Executivo operacional;
- Agenda Inteligente visível;
- módulos existentes acessíveis;
- regressão igual a zero.

## Capítulo 62
### Roadmap Pós-MVP

Após a conclusão do Sprint 1.5.

Os próximos Sprints serão:

#### Sprint 1.6

Integração completa dos módulos.

#### Sprint 1.7

Motores de Inteligência.

#### Sprint 1.8

Agenda Inteligente evoluída.

#### Sprint 1.9

Centro de Decisão.

#### Sprint 2.0

Aprendizado baseado no uso real.

## Capítulo 63
### Definição Oficial do ARGOS

O ARGOS passa oficialmente a ser definido como:

> Um Sistema Operacional Executivo para Gestão Patrimonial, Financeira e Estratégica.

Sua missão é transformar dados em decisões e decisões em execução.

Não substitui o julgamento humano.

Amplia sua capacidade.

## Capítulo 64
### Encerramento do Documento

Com este documento, fica oficialmente especificada a experiência da Home do ARGOS.

Toda implementação futura deverá manter aderência a esta especificação ou ser precedida de uma nova aprovação formal.

Este documento substitui descrições informais anteriores da Home e passa a ser a referência oficial para o desenvolvimento do MVP.

---

# FIM DO DOCUMENTO OFICIAL Nº 024
