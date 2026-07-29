# RELATÓRIO DE AUDITORIA — MARCO 9.1

Data: 29 de julho de 2026  
Escopo: arquitetura implementada até o Marco 9.0  
Resultado: **✅ APROVADO COM ALERTAS**

## Arquitetura

| # | Verificação | Estado | Evidência |
|---:|---|---|---|
| 1 | Sentido das dependências da cadeia oficial | ✅ APROVADO | Conectores dependem do MPU; validação, consolidação e snapshot consomem o MPU. |
| 2 | Dependências circulares | ✅ APROVADO | Grafo AST de 48 módulos e 53 arestas: zero ciclos após a correção. |
| 3 | Imports de todos os módulos backend | ✅ APROVADO | 47 módulos importados na linha de base sem falhas; suíte final cobre o novo módulo daily. |
| 4 | Definições duplicadas dos contratos auditados | ✅ APROVADO | Uma definição oficial para cada contrato da cadeia; contratos daily compartilhados centralizados. |
| 5 | Imports e código inequivocamente mortos | ✅ APROVADO | `ruff check backend tests` sem ocorrências após a limpeza. |
| 6 | Compatibilidade do `PortfolioConnector` | ✅ APROVADO | Protocolo alinhado ao parâmetro `file_path` usado pelos quatro módulos registrados. |

## Compatibilidade

| # | Verificação | Estado | Evidência |
|---:|---|---|---|
| 7 | Registry oficial | ✅ APROVADO | UBS, Santander e Bradesco ativos; TipRanks registrado e inativo para upload. |
| 8 | Contrato de saída UBS | ✅ APROVADO | Tupla exclusivamente de `backend.models.PortfolioPosition`. |
| 9 | Contrato de saída Santander | ✅ APROVADO | Tupla exclusivamente de `backend.models.PortfolioPosition`. |
| 10 | Contrato de saída Bradesco | ✅ APROVADO | Tupla exclusivamente de `backend.models.PortfolioPosition`. |
| 11 | Validação agnóstica aos conectores oficiais | ✅ APROVADO | Os três resultados foram aceitos pelo mesmo `ImportValidationEngine`. |
| 12 | Consolidação de saída validada | ✅ APROVADO | Os três conjuntos foram aceitos pelo mesmo `PortfolioConsolidationEngine`. |
| 13 | Snapshot usa somente motores oficiais | ✅ APROVADO | Builder injeta/instancia `ImportValidationEngine` e `PortfolioConsolidationEngine`. |
| 14 | Análise estática estrita completa | ⚠️ ALERTA | `mypy` e `pyright` ainda registram dívida de anotações em módulos legados; não houve erro de runtime correspondente na suíte. |

## Fluxo ponta a ponta

Fluxo executado dez vezes por instituição: arquivo → registry → conector →
`PortfolioPosition` → `ImportValidationEngine` →
`PortfolioConsolidationEngine` → `DailyPortfolioSnapshot`.

| # | Instituição | Estado | Resultado |
|---:|---|---|---|
| 15 | UBS | ✅ APROVADO | 28 posições, JOLIKA, USD, fixture CSV sanitizada. |
| 16 | Santander | ✅ APROVADO | 1 posição, JOLIKA, USD, XLSX sintético sanitizado. |
| 17 | Bradesco | ✅ APROVADO | 50 posições, NEI, BRL, fixture TXT sanitizada. |
| 18 | Fixture bancária real de Santander no repositório | ⚠️ ALERTA | Não existe fixture Santander versionada; a validação usou XLSX sintético com a estrutura oficial. |

## Integridade

| # | Verificação | Estado | Evidência |
|---:|---|---|---|
| 19 | Separação JOLIKA/NEI na chave econômica | ✅ APROVADO | Proprietário integra a chave de consolidação. |
| 20 | Consolidação respeita proprietário | ✅ APROVADO | Ativos iguais de JOLIKA e NEI permanecem separados. |
| 21 | Estatísticas respeitam proprietário | ✅ APROVADO | Contagens são segregadas em `positions_by_owner`. |
| 22 | Preservação de BRL | ✅ APROVADO | Bradesco permaneceu integralmente em BRL. |
| 23 | Preservação de USD | ✅ APROVADO | UBS e Santander permaneceram em USD. |
| 24 | Separação de moedas na consolidação | ✅ APROVADO | Moeda integra a chave econômica e totais são mapas por moeda. |
| 25 | Ausência de conversão implícita | ✅ APROVADO | Nenhum motor auditado contém taxa ou rotina de conversão cambial. |
| 26 | Imutabilidade de `PortfolioPosition` | ✅ APROVADO | Dataclass congelado; entradas permaneceram iguais antes/depois do fluxo. |
| 27 | Imutabilidade de `ImportValidationReport` | ✅ APROVADO | Tuplas e mapas protegidos por `MappingProxyType`, com regressão de mutação. |
| 28 | Imutabilidade de `ConsolidatedPortfolio` | ✅ APROVADO | Grafo de dataclasses congelados, tuplas e mapas protegidos, com regressão. |
| 29 | Imutabilidade de `DailyPortfolioSnapshot` | ✅ APROVADO | Dataclasses congelados e mapas protegidos; teste de mutação passa. |
| 30 | Determinismo | ✅ APROVADO | Dez execuções por instituição idênticas após normalizar somente `generated_at`. |

## Performance

Médias de dez execuções locais; arquivos pequenos representativos, sem I/O de rede:

| # | Etapa/instituição | Estado | Média |
|---:|---|---|---:|
| 31 | Importação | ✅ APROVADO | UBS 0,548 ms; Santander 0,555 ms; Bradesco 11,671 ms. |
| 32 | Validação | ✅ APROVADO | UBS 0,226 ms; Santander 0,034 ms; Bradesco 0,401 ms. |
| 33 | Consolidação | ✅ APROVADO | UBS 0,866 ms; Santander 0,077 ms; Bradesco 1,370 ms. |
| 34 | Snapshot | ✅ APROVADO | UBS 1,982 ms; Santander 0,222 ms; Bradesco 3,274 ms. |

Não foi identificado gargalo relevante para os volumes auditados. O parser de
texto Bradesco é a etapa mais lenta, mas permanece abaixo de 12 ms para 50
posições e não justifica otimização neste marco.

## Segurança

| # | Verificação | Estado | Evidência |
|---:|---|---|---|
| 35 | Credenciais e chaves privadas | ✅ APROVADO | Busca no conteúdo versionado sem ocorrências; `.env.example` contém apenas placeholder. |
| 36 | Dados pessoais em fixtures | ✅ APROVADO | Identificador/nome de conta UBS substituído por `SYNTHETIC-ACCOUNT`; buscas sem marcadores pessoais. |
| 37 | Caminhos absolutos | ✅ APROVADO | Busca por caminhos de workspace/home/usuário sem ocorrências. |
| 38 | Temporários versionados | ✅ APROVADO | Nenhum cache, bytecode, log ou arquivo temporário é rastreado; artefatos locais estão ignorados. |
| 39 | Dependências quebradas instaladas | ✅ APROVADO | `python -m pip check`: nenhuma dependência quebrada no ambiente corrente. |

## Testes

| # | Verificação | Estado | Evidência |
|---:|---|---|---|
| 40 | Suíte, integração, compilação e instalação limpa | ⚠️ ALERTA | Suítes Python/JS, fluxo E2E, imports e `compileall` passaram. Virtualenv foi criado, mas o proxy 403 impediu baixar `openpyxl`, `xlrd` e `pytest` do índice. |

## Problemas encontrados

1. **❌ FALHA (corrigida):** mapas internos de relatórios congelados ainda eram mutáveis.
2. **❌ FALHA (corrigida):** fixture UBS continha identificador/nome com formato de conta.
3. **❌ FALHA (corrigida):** Santander possuía parser XLSX interno, mas o fluxo oficial exigia `openpyxl` desnecessariamente.
4. **❌ FALHA (corrigida):** protocolo dos conectores divergia no nome do parâmetro e havia imports mortos.
5. **❌ FALHA (corrigida):** contratos daily compartilhados criavam dependências circulares.

Não restou falha funcional conhecida no escopo obrigatório após as correções e
a repetição da auditoria.

## Correções realizadas

- Mapas de estatísticas oficiais protegidos com `MappingProxyType` e testes de regressão.
- Conta UBS substituída por marcador sintético em todas as linhas da fixture.
- Leitura Santander XLSX direcionada ao parser ZIP/XML já existente, com teste sem mock.
- Contrato `PortfolioConnector` alinhado e imports mortos removidos.
- Contratos daily imutáveis extraídos para `backend.daily.models`, eliminando ciclos.

## Riscos remanescentes

- **⚠️ ALERTA:** a instalação limpa não pôde ser concluída por bloqueio externo do proxy; deve ser repetida em CI com acesso ao índice de pacotes.
- **⚠️ ALERTA:** não há fixture Santander real e sanitizada versionada; o teste estrutural sintético reduz, mas não elimina, risco de variação futura do banco.
- **⚠️ ALERTA:** `mypy`/`pyright` expõem dívida preexistente de tipagem em módulos legados. A suíte e a compilação passam, mas o saneamento deve ocorrer incrementalmente.

## Recomendações

1. Repetir `pip install -r requirements.txt` e a suíte em CI com cache/índice disponível.
2. Adicionar, mediante autorização e sanitização, uma fixture Santander representativa.
3. Criar baseline gradual de tipagem, começando pela cadeia de portfólio, sem bloquear correções funcionais não relacionadas.
4. Manter o benchmark atual como referência e só otimizar Bradesco se volumes reais demonstrarem impacto perceptível.

## Fechamento

- **Total de verificações executadas:** 40.
- **Falhas remanescentes:** 0.
- **Alertas remanescentes:** 3.
- **Estado esperado da árvore Git após a entrega:** limpa.
- **SHA do commit:** preenchido pela entrega Git do relatório.
- **Merge automático:** não realizado.
