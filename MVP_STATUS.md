# Situação do MVP

Estado dos módulos na baseline oficial `v0.1-mvp-core`, em 29 de julho de 2026.
“Concluído” indica que o módulo integra o núcleo atual e possui cobertura
automatizada relevante; não impede evolução posterior.

## CONCLUÍDO

### Entrada, normalização e patrimônio

- **MPU (`PortfolioPosition`):** modelo normalizado de posições.
- **Identificação de patrimônio:** `JOLIKA` e `NEI` explícitos no MPU.
- **Conector UBS:** leitura de CSV, XLS e XLSX reconhecidos.
- **Conector Santander:** inspeção e leitura de XLS e XLSX reconhecidos.
- **Conector TipRanks:** leitura e conversão para o MPU.
- **Importação inteligente:** reconhecimento e encaminhamento de arquivos.

### Motores de portfólio

- **Diagnóstico institucional:** validação e resumo por instituição.
- **Diagnóstico consolidado:** visão agregada a partir dos diagnósticos.
- **Consolidação MPU:** agrupamento normalizado de posições.
- **Consolidação executiva JOLIKA:** UBS e Santander separados e consolidados.
- **Top Holdings:** exposição por ativo, instituição e consolidado.
- **Alocação, liquidez e concentração:** blocos determinísticos do cockpit.
- **Motor de contribuição à meta:** análise estrutural por premissas explícitas.

### ARGOS Diário e mercado

- **Carregamento de ambiente e settings:** configuração centralizada.
- **Cache diário:** validade e reaproveitamento controlado do último resultado.
- **Contrato de provedor diário:** isolamento da fonte externa.
- **Finnhub:** provedor atual de fatos e agenda.
- **Registry e fallback de provedores:** precedência e deduplicação.
- **DailyContextService:** contexto ligado à carteira, com janela de 48 horas.
- **Transformações diárias:** prioridades e análises.
- **DailyOrchestrator:** contrato oficial de fatos, prioridades, agenda,
  análises e panorama.
- **Infraestrutura de inteligência de mercado:** modelos, validação,
  consolidação, confiança, cache e serviço.

### Entrega

- **Dashboard 2.2:** contrato oficial de diagnóstico, consolidação e daily.
- **Servidor HTTP:** APIs, sessão de carteiras e frontend estático.
- **Frontend:** importação, cockpit, contexto diário e privacidade de valores.
- **Compatibilidade legada:** projeções antigas delegando ao fluxo oficial.
- **Testes automatizados:** contratos principais de backend e frontend.

## EM ANDAMENTO

- **Cobertura NEI:** o patrimônio está modelado, mas seus conectores e sua visão
  operacional completa ainda não compõem o MVP atual.
- **Novas instituições:** arquitetura preparada para conectores adicionais;
  somente UBS, Santander e TipRanks estão implementados.
- **Inteligência externa:** expansão de fontes, cobertura e qualidade das
  evidências além do provedor atual.
- **Robustez operacional:** evolução contínua de mensagens de erro, formatos
  reais aceitos e validação de interface.
- **Relatórios:** definição das saídas executivas e de prestação de contas.

## PLANEJADO

- Conectores para Bradesco/Ágora, Monte Bravo, novas instituições, exchanges e
  carteiras cripto.
- Consolidação operacional completa do NEI, sempre separada da JOLIKA.
- Provedores externos adicionais e ampliação da agenda econômica.
- Histórico persistente de carteiras, diagnósticos e decisões.
- Relatórios versionados e exportáveis.
- Evolução dos motores de risco e oportunidades, com evidências rastreáveis.
- Autenticação e persistência adequadas a uma implantação multiusuário.

## FORA DO ESCOPO DO MVP

- Execução automática de ordens, rebalanceamentos ou movimentações financeiras.
- Custódia de ativos, chaves privadas ou credenciais bancárias.
- Mistura ou compensação entre os patrimônios JOLIKA e NEI.
- Substituição da decisão do gestor por decisão automática do ARGOS.
- Dependência direta do núcleo em formatos bancários ou APIs específicas.
- Arquitetura distribuída, microserviços ou infraestrutura complexa sem ganho
  comprovado de decisão, segurança ou tempo.
- Garantia de retorno financeiro ou recomendação sem evidência rastreável.
