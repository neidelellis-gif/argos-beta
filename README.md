# ARGOS Beta

ARGOS Beta é uma plataforma de inteligência para investimentos.

## Objetivo

Construir um sistema capaz de:

- coletar dados automaticamente;
- calcular indicadores;
- registrar histórico;
- apoiar decisões de investimento.

## Arquitetura

- ARGOS Data Engine
- ARGOS Core
- ARGOS ID

## Estrutura

backend/
database/
docs/
frontend/
scripts/
tests/

## Primeira implementação

Ativo inicial:

ICE — Intercontinental Exchange

Objetivo:

Receber automaticamente os preços,
calcular indicadores
e alimentar o ARGOS ID.

## Versão

Beta 0.1

## Dados do ARGOS Diário

O fluxo diário usa um contrato independente de provedor. A implementação atual
adota o Finnhub para notícias gerais, calendário econômico, resultados e
dividendos. A escolha concentra as consultas em uma integração HTTP simples,
mantendo a normalização isolada do restante da aplicação.

Copie `.env.example` para sua configuração local e informe:

- `FINNHUB_API_KEY`: credencial do Finnhub;
- `ARGOS_DAILY_PROVIDERS`: ordem dos provedores registrados, separados por
  vírgula (opcional, `finnhub` por padrão);
- `ARGOS_DAILY_CACHE_TTL_SECONDS`: validade do cache local (opcional, 900 por
  padrão);
- `ARGOS_DAILY_CACHE_DIR`: diretório do cache (opcional, `.cache/daily` por
  padrão).

Na inicialização do provedor, o ARGOS carrega automaticamente o arquivo `.env`
da raiz do projeto. Variáveis já exportadas no processo têm precedência e não
são sobrescritas.

Sem credencial ou durante falhas externas, o dashboard permanece disponível e
identifica a fonte como indisponível. Fatos e agenda possuem caches separados;
depois que a validade expira, o último resultado correto pode ser reutilizado
durante uma falha temporária e é identificado no contrato como conteúdo em
cache.

Provedores adicionais podem ser registrados por nome no
`DailyProviderRegistry`. A ordem configurada determina a precedência: todos os
provedores ativos são consultados, uma falha aciona automaticamente os próximos
e eventos equivalentes são deduplicados preservando a primeira fonte da lista.
