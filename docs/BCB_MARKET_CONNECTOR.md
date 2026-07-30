# Conector oficial de mercado do Banco Central

## Arquitetura

`BcbMarketConnector` é o primeiro provedor remoto do framework `MarketConnector`.
Ele encapsula integralmente HTTP, URLs e formatos do Banco Central do Brasil (BCB)
e entrega somente `MarketFact` e `MarketAgendaEvent`. Não calcula prioridade,
impacto ou recomendação, e nenhum motor analítico conhece o provedor.

```text
ConnectorManager -> BcbMarketConnector -> modelos canônicos -> motores
       | falha
       +----------> LocalMarketConnector
```

O servidor registra `BCB` como provedor preferencial e `LOCAL` como fallback. A
seleção e a recarga são síncronas e sob demanda; não há tarefa em background.

## Fontes utilizadas

Esta versão consulta exclusivamente duas fontes públicas oficiais, cujos detalhes
de protocolo permanecem privados ao conector:

- Sistema Gerenciador de Séries Temporais (SGS), série 432, meta da taxa Selic;
- calendário oficial de reuniões do Copom publicado pelo BCB.

O valor mais recente da série é normalizado como fato econômico. Cada data do
calendário é normalizada como evento de banco central, preservando BCB como fonte
rastreável. Respostas vazias, datas inválidas, valores inválidos e estruturas
inesperadas invalidam toda a carga remota.

Categoria e importância são os valores canônicos previamente definidos pelo projeto
para essas duas fontes (os mesmos usados nos arquivos oficiais locais). O conector
não infere, pontua nem reclassifica esses campos a partir dos valores recebidos.

## Fallback e operação offline

Em cada recarga o manager tenta novamente o BCB. Se a verificação de disponibilidade
ou qualquer etapa da carga falhar, ele carrega fatos e agenda dos arquivos oficiais
por meio do `LocalMarketConnector`. Assim, uma indisponibilidade de rede não alcança
os motores nem interrompe o Cockpit. Se o BCB se recuperar, a próxima recarga manual
volta automaticamente à fonte remota.

## Cache e diagnóstico

O cache em memória substitui fatos e agenda atomicamente. A entrada registra horário,
conector/origem usados, quantidades, resultado da tentativa remota e erro, quando
existir. Após uma falha do BCB, a entrada contém os dados locais válidos e também
registra `last_reload_success: false`; não há mistura de coleções entre provedores.

`GET /api/market/status` apenas diagnostica. `POST /api/market/reload` tenta uma nova
atualização imediatamente e devolve o mesmo diagnóstico. Os campos incluem
`active_connector`, `fallback_available`, `last_reload`, `source`, contagens,
`last_reload_success` e `last_error`. O contrato público do Cockpit permanece `1.5`.

## Limitações conhecidas

- cache somente em memória, perdido ao reiniciar o processo;
- atualização exclusivamente manual ou na primeira leitura, sem agendamento;
- um único provedor ativo por carga, sem combinação BCB/LOCAL;
- somente SGS 432 e calendário do Copom nesta versão;
- disponibilidade e formato das respostas continuam sujeitos ao serviço público do BCB.
