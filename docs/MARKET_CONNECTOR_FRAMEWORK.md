# Framework de conectores de mercado

## Objetivo

O framework separa a aquisição de dados de mercado da análise. Provedores externos
entregam fatos e eventos nos modelos canônicos do ARGOS; os motores continuam
recebendo esses modelos e não conhecem arquivos, formatos ou conectores.

```text
data/market -> LocalMarketConnector -> ConnectorManager -> modelos canônicos -> motores
                                             |
                                      cache em memória
```

Esta operação não adiciona provedores remotos, atualização automática, streaming,
WebSocket, IA, recomendações ou lógica de investimento.

## Componentes

- `MarketConnector`: interface única para provedores.
- `LocalMarketConnector`: lê `data/market/facts` e `data/market/agenda`, preservando
  integralmente a validação e normalização da Operação Real 02.
- `ConnectorManager`: registra conectores, seleciona um conector ativo e fornece
  somente tuplas dos modelos canônicos aos consumidores.
- `ConnectorCache`: mantém, apenas durante a vida do processo, o último carregamento
  concluído com sucesso.

O módulo legado `backend.market_data_loader` permanece como fachada de importação
para compatibilidade, mas o servidor utiliza exclusivamente o `ConnectorManager`.

## Interface de um provedor

Todo conector implementa:

- `is_available()`: informa se a origem pode ser usada;
- `load_facts()`: retorna `tuple[MarketFact, ...]`;
- `load_agenda()`: retorna `tuple[MarketAgendaEvent, ...]`;
- `metadata()`: descreve o conector e a origem, sem expor payloads do provedor.

Um conector deve normalizar dados antes de retorná-los. Nenhum formato específico
de provedor pode atravessar essa fronteira.

## Registro, seleção e fluxo

Na composição da aplicação, o conector local é registrado como `LOCAL` e marcado
como ativo. O manager rejeita nomes vazios e registros duplicados. A seleção de
outro conector limpa o cache para impedir que dados de origens diferentes sejam
misturados.

Quando um consumidor solicita fatos ou agenda antes do primeiro carregamento, o
manager faz uma carga síncrona sob demanda. Depois disso, ambos são lidos do mesmo
cache. Não existe tarefa ou atualização em segundo plano.

## Cache

Cada entrada contém:

- instante UTC da última recarga bem-sucedida;
- tupla de fatos canônicos;
- tupla de eventos canônicos;
- origem dos dados.

Uma falha de disponibilidade ou carregamento não substitui a última entrada válida.
O cache não é persistido em arquivo ou banco e é perdido ao encerrar o processo.

## Operação manual e diagnóstico

### `POST /api/market/reload`

Executa imediatamente uma nova carga pelo conector ativo e, em sucesso, retorna o
mesmo diagnóstico do endpoint de status. Se o conector estiver indisponível ou a
origem for inválida, responde HTTP `503` com uma mensagem de erro clara.

### `GET /api/market/status`

Não inicia uma carga. Retorna o conector ativo, disponibilidade atual, instante da
última recarga e quantidades presentes no cache:

```json
{
  "connector": "LOCAL",
  "available": true,
  "last_reload": "2026-07-30T15:00:00+00:00",
  "facts": 12,
  "agenda": 8
}
```

Antes da primeira carga, `last_reload` é `null` e as quantidades são zero.

## Integração e compatibilidade

O fluxo diário obtém fatos e agenda do manager e entrega as mesmas tuplas canônicas
aos motores já existentes. Nenhum motor analítico foi alterado. Os contratos
públicos do Cockpit e da experiência diária permanecem na versão `1.5`.
