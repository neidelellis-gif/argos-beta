# ARGOS

Plataforma de inteligência para gestão patrimonial que reduz o tempo entre o
recebimento de informações e uma decisão de investimento. O sistema importa
arquivos bancários, normaliza posições no Modelo de Portfólio Universal (MPU),
produz diagnósticos e consolidações, acrescenta contexto diário de mercado e
entrega uma visão executiva no navegador.

Esta é a baseline oficial `v0.1-mvp-core`. O ARGOS recomenda e organiza
evidências; a decisão permanece com o gestor.

## Princípios do produto

- JOLIKA e NEI são patrimônios independentes e nunca devem ser consolidados
  entre si.
- UBS e Santander são diagnosticados separadamente antes da consolidação da
  JOLIKA.
- Valores financeiros permanecem ocultos por padrão na interface.
- O contexto externo considera as últimas 48 horas, preservando eventos
  estruturais enquanto relevantes.
- O restante do sistema depende do MPU, não dos formatos CSV, XLS, XLSX, PDF
  ou de APIs externas.

## Arquitetura oficial

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

Os conectores UBS, Santander e TipRanks convertem fontes externas em
`PortfolioPosition`, o contrato do MPU. O diagnóstico opera por instituição e
no consolidado. O contexto diário combina fatos e agenda de provedores
registrados; o orquestrador compõe o contrato consumido pelo dashboard. O
servidor HTTP expõe esse resultado e serve o frontend estático.

Detalhes, responsabilidades e contratos estão em [ARCHITECTURE.md](ARCHITECTURE.md).

## Fluxo oficial

1. O usuário seleciona arquivos de carteira no frontend.
2. `backend.server` recebe os arquivos e aciona a importação.
3. Cada arquivo reconhecido é encaminhado ao conector da instituição.
4. O conector converte as posições para o MPU e registra patrimônio e origem.
5. As posições são diagnosticadas separadamente e depois consolidadas dentro
   do mesmo patrimônio.
6. `DailyContextService` relaciona carteira, fatos e agenda das últimas 48
   horas.
7. `DailyOrchestrator` reúne contexto, prioridades, análises e panorama.
8. `build_dashboard` produz o contrato oficial entregue ao frontend.

## Estado dos módulos

### Concluídos

- MPU (`PortfolioPosition`) e identificação explícita do patrimônio.
- Conectores UBS, Santander e TipRanks.
- Importação inteligente de carteiras.
- Diagnóstico por instituição e diagnóstico consolidado.
- Consolidação da JOLIKA, Top Holdings, alocação, liquidez e motor de
  contribuição à meta.
- Infraestrutura diária: configuração, cache, provedores e registry.
- `DailyContextService` com janela padrão de 48 horas.
- `DailyOrchestrator` e contrato do dashboard.
- Servidor HTTP, dashboard operacional e frontend com ocultação de valores.
- Testes automatizados de backend e do contrato principal do frontend.

### Em desenvolvimento

- Ampliação dos conectores para novas instituições e formatos.
- Cobertura operacional completa do patrimônio NEI.
- Evolução da inteligência de mercado e das evidências externas.
- Relatórios e rotinas de prestação de contas.

O recorte completo do MVP está em [MVP_STATUS.md](MVP_STATUS.md), e o histórico
dos marcos está em [CHANGELOG.md](CHANGELOG.md).

## Como executar

Requisitos: Python 3.10 ou superior e `pip`.

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m backend.server
```

Acesse <http://localhost:8080>.

Para habilitar dados externos do ARGOS Diário, crie `.env` na raiz (o sistema
continua disponível sem credencial):

```dotenv
FINNHUB_API_KEY=sua_chave
ARGOS_DAILY_PROVIDERS=finnhub
ARGOS_DAILY_CACHE_TTL_SECONDS=900
ARGOS_DAILY_CACHE_DIR=.cache/daily
```

`FINNHUB_API_KEY` habilita o provedor atual. As demais variáveis são opcionais
e os valores acima correspondem aos padrões. Provedores adicionais podem ser
registrados no `DailyProviderRegistry`; falhas acionam o próximo provedor da
ordem configurada, e o último cache válido pode sustentar uma falha temporária.

## Como rodar os testes

Com o ambiente virtual ativo:

```bash
python -m pytest -q
```

O teste unitário JavaScript do frontend não depende de pacotes externos e pode
ser executado separadamente quando Node.js estiver disponível:

```bash
node --test frontend/app.test.js
```

## Organização das pastas

```text
backend/
  config/       # ambiente, settings e premissas do motor de contribuição
  connectors/   # adaptadores UBS, Santander e TipRanks para o MPU
  daily/        # contexto, cache, provedores, transformações e orquestração
  market/       # infraestrutura e consolidação de inteligência de mercado
  models.py     # MPU e identificação de patrimônio
  portfolio_*   # importação, diagnóstico e consolidação do portfólio
  dashboard.py  # composição do contrato oficial do dashboard
  server.py     # servidor HTTP, APIs e arquivos estáticos
frontend/       # interface web estática e teste JavaScript
tests/          # testes automatizados Python
data/           # dados locais usados pela experiência atual
docs/           # documentação histórica e oficial anterior à baseline
```

## Documentação da baseline

- [Arquitetura oficial](ARCHITECTURE.md)
- [Histórico de versões](CHANGELOG.md)
- [Situação do MVP](MVP_STATUS.md)
