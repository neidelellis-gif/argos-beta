# Changelog

Todas as mudanças relevantes do ARGOS são registradas neste arquivo. Esta
baseline organiza retrospectivamente os marcos já presentes no histórico do
repositório; ela não modifica o comportamento do sistema.

## [v0.1-mvp-core] — 2026-07-29 — Fase 8 / Marco 8.0

### Documentação

- Estabelecida a primeira baseline oficial do núcleo do MVP.
- Atualizados visão geral, execução, testes e organização do repositório.
- Formalizados arquitetura, fluxo, contratos estáveis e situação dos módulos.

## Fase 7 — Consolidação do fluxo oficial do MVP

### Entregue

- Dashboard migrado para consumir o `DailyOrchestrator`.
- `build_daily_experience` descontinuado como caminho principal e mantido como
  camada de compatibilidade.
- Endpoints legados consolidados sobre o mesmo contrato oficial do dashboard.
- Janela de análise diária centralizada em 48 horas.
- Conceito de patrimônio (`JOLIKA` ou `NEI`) incorporado explicitamente ao MPU,
  reforçando a separação patrimonial.

## Fase 6 — Orquestração diária

### Entregue

- Criado o contrato do `DailyOrchestrator`.
- Integrados fatos, prioridades, agenda, análises e panorama ao orquestrador.
- Separadas as responsabilidades de contexto, experiência e orquestração.
- Ampliado o contrato diário sem acoplar o orquestrador à apresentação.

## Fase 5 — Configuração e infraestrutura do ARGOS Diário

### Entregue

- Adicionado carregamento automático do arquivo `.env` do projeto.
- Centralizadas as configurações do backend.
- Migrados cache diário, registry de provedores e credencial Finnhub para a
  configuração centralizada.
- Mantidos cache com validade, fallback entre provedores e funcionamento
  degradado quando a fonte externa não está disponível.

## Histórico anterior à Fase 5

- Criados o MPU e os conectores TipRanks, UBS e Santander.
- Implementados consolidação, diagnóstico, importação inteligente e dashboard
  operacional.
- Estruturados o ARGOS Diário e a inteligência de mercado inicial.
