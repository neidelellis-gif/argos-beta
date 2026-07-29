# Arquitetura Oficial do ARGOS

## Objetivo

A arquitetura do ARGOS transforma fontes heterogêneas em um contrato interno
estável e conduz esse contrato até uma interface executiva. A separação entre
adaptação, domínio, contexto e apresentação permite evoluir cada fonte sem
espalhar dependências de formatos externos pelo sistema.

## Fluxo oficial

```text
Arquivos Bancários
        ↓
Connectors
        ↓
MPU
        ↓
Diagnóstico
        ↓
Consolidação
        ↓
DailyContextService
        ↓
DailyOrchestrator
        ↓
Dashboard
        ↓
Frontend
```

Este é o único fluxo oficial do MVP. As camadas de compatibilidade descritas
abaixo delegam para ele e não constituem fluxos alternativos.

## Responsabilidades por camada

### 1. Arquivos Bancários

Fontes recebidas do usuário em CSV, XLS ou XLSX. São dados de entrada, não
contratos do domínio. PDF e APIs podem ser fontes futuras, mas o núcleo não deve
depender diretamente deles.

### 2. Connectors

Um conector por instituição reconhece sua estrutura, valida campos, normaliza
valores e cria posições do MPU. Atualmente existem conectores UBS, Santander e
TipRanks. Particularidades de planilhas e cabeçalhos terminam nesta camada.

### 3. MPU

O Modelo de Portfólio Universal é representado por `PortfolioPosition`. Ele
carrega identidade do ativo, instituição, patrimônio, moeda, quantidade, valor,
classe e rastreabilidade da fonte. O patrimônio aceita somente `JOLIKA` ou
`NEI`; essa informação é obrigatória e impede consolidações implícitas entre
patrimônios.

### 4. Diagnóstico

O motor valida e resume primeiro uma única instituição. O diagnóstico
consolidado recebe diagnósticos institucionais já separados, preservando totais,
contagens e alertas rastreáveis.

### 5. Consolidação

Agrupa posições normalizadas por ativo e instituição dentro do patrimônio.
Produz visão executiva, Top Holdings, alocação por classe, liquidez,
concentração e contribuição estrutural à meta. UBS e Santander permanecem
visíveis separadamente antes da visão total da JOLIKA.

### 6. DailyContextService

Relaciona as posições do MPU a fatos e eventos de agenda externos. Aplica a
janela padrão de 48 horas, ajusta prioridade por aderência à carteira e mantém
metadados de fonte. Provedores externos são acessados por contrato e registry,
com cache e fallback.

### 7. DailyOrchestrator

Compõe o contrato diário completo a partir do serviço de contexto. Reúne fatos,
prioridades, agenda, análises e panorama sem conhecer HTML nem detalhes de
renderização.

### 8. Dashboard

Combina diagnóstico, consolidação e saída do `DailyOrchestrator` em um contrato
serializável. `build_dashboard` é o ponto oficial de composição; `load_dashboard`
fornece a carga inicial usada pelo servidor.

### 9. Frontend

Consome as APIs do servidor e renderiza a experiência executiva. O navegador
controla a exibição, inclusive Mostrar/Ocultar valores, mas não redefine regras
de domínio nem interpreta arquivos bancários como fonte canônica.

## Princípios arquiteturais

1. **Separação patrimonial:** JOLIKA e NEI nunca são misturados.
2. **Separação institucional:** instituições são analisadas individualmente
   antes da consolidação permitida.
3. **Normalização na borda:** formatos externos são conhecidos pelos
   conectores, não pelo núcleo.
4. **Contrato interno único:** o MPU é a linguagem entre importação e motores de
   domínio.
5. **Rastreabilidade:** posição, fato e evento preservam origem suficiente para
   chegar à fonte.
6. **Degradação controlada:** indisponibilidade externa não derruba o dashboard;
   cache e estado da fonte permanecem explícitos.
7. **Orquestração sem apresentação:** o fluxo diário produz dados e não HTML.
8. **Compatibilidade por delegação:** interfaces antigas reutilizam o fluxo
   oficial, sem duplicar regra.
9. **Simplicidade:** uma nova camada só se justifica quando melhora decisão,
   segurança ou tempo operacional.

## Camadas de compatibilidade

- `backend.daily.experience.build_daily_experience` permanece disponível para
  consumidores anteriores, mas delega à composição diária atual e não é o
  caminho oficial.
- As respostas legadas de fatos e cockpit em `backend.server` são projeções do
  dashboard oficial.
- `backend.consolidation` preserva a consolidação executiva usada pela
  experiência existente, enquanto `backend.portfolio_consolidation` fornece o
  contrato consolidado baseado no MPU.
- A compatibilidade é unidirecional: componentes antigos podem adaptar a saída
  oficial; o núcleo não depende das formas legadas.

## Contratos estáveis da baseline

| Contrato | Responsabilidade estável |
| --- | --- |
| `PortfolioOwner` | Identificar explicitamente `JOLIKA` ou `NEI`. |
| `PortfolioPosition` | Representar uma posição normalizada do MPU com origem rastreável. |
| `load_positions` dos conectores | Converter uma fonte reconhecida em posições do MPU. |
| `import_portfolios` | Reconhecer arquivos e encaminhá-los aos conectores. |
| `diagnose_institution` | Diagnosticar posições de uma única instituição. |
| `diagnose_consolidated` | Consolidar diagnósticos institucionais compatíveis. |
| `consolidate_portfolio_positions` | Consolidar posições MPU sem depender do arquivo original. |
| `DailyContextService` | Produzir contexto diário relacionado à carteira. |
| `DailyOrchestrator.build` | Compor o contrato diário oficial. |
| `build_dashboard` | Produzir o payload oficial consumido pelo servidor e frontend. |

“Estável” nesta baseline significa que consumidores devem depender dessas
responsabilidades, e não de detalhes internos. Não significa congelamento
permanente da implementação ou impedimento de evolução versionada.

## Dependências permitidas

O sentido normal das dependências acompanha o fluxo: conectores dependem do
MPU; motores consomem MPU; contexto diário consome posições normalizadas;
dashboard consome motores e orquestrador; frontend consome o dashboard. Nenhuma
camada posterior deve voltar a interpretar diretamente CSV, XLS ou XLSX.
