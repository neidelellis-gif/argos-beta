# RELATÓRIO DE IMPLEMENTAÇÃO — MARCO 9.2

Data: 29 de julho de 2026  
Resultado: **✅ APROVADO**

## Diagnóstico inicial

A dívida registrada ao encerrar o Marco 9.1 era:

- `mypy backend`: **22 erros**;
- `pyright backend tests`: **55 erros e 2 avisos**.

Na reprodução feita no início do Marco 9.2, o mypy confirmou os mesmos 22
erros. O pyright encontrou 47 erros e 2 avisos, pois oito diagnósticos do
inventário histórico já haviam sido removidos por ajustes do Marco 9.1.

### Arquivos e categorias

| Categoria | Arquivos principais | Causa e risco |
|---|---|---|
| Contratos e opcionais | `config/settings.py`, `connectors/registry.py`, `server.py` | Defaults implícitos, IDs/cookies opcionais e payloads dinâmicos sem estreitamento. |
| Coleções | `portfolio_import.py`, `portfolio_diagnostics.py`, `connectors/bradesco_connector.py` | Listas, sets e dicionários sem parâmetros concretos. |
| Monetário | `portfolio_consolidation.py`, `consolidation.py`, `import_validation.py` | `Counter` inferido como inteiro e `Decimal | None` sem estreitamento. |
| Dependências opcionais | `connectors/io.py` | Bibliotecas runtime sem stubs instalados (`openpyxl` e `xlrd`). |
| XLSX Santander | `connectors/santander_connector.py` | Texto XML opcional antes de `int`/`float`. |
| Modelos daily/mercado | `daily/models.py`, `market/models.py` | `Any` propagado em coleções e serialização. |
| Testes | dez arquivos em `tests/` | Stubs incompletos, opcionais não estreitados e mutações deliberadamente inválidas. |

## Correções

### Contratos, protocolos e opcionais

- `get_setting` recebeu overloads que distinguem chamada sem default e chamada
  com default.
- `ConnectorRegistry` passou a declarar o conjunto de IDs ativos como
  `set[str]`; o protocolo existente continuou correspondendo às assinaturas
  reais de UBS, Santander e Bradesco.
- Payloads, cookies, sessões e multipart foram estreitados somente após
  verificações reais de runtime.
- `PortfolioPosition.__post_init__`, chaves econômicas e helpers do snapshot
  receberam tipos completos de entrada e retorno.

### Coleções, imutabilidade e valores financeiros

- Agrupamentos passaram a usar `list`, `dict`, `set`, `tuple`, `Iterable` e
  `Mapping` parametrizados de acordo com mutabilidade e direção do contrato.
- Mapas públicos somente-leitura continuam protegidos por `MappingProxyType`.
- Totais monetários passaram de `Counter` inadequadamente inferido para
  `dict[str, Decimal]`; os valores e resultados permaneceram `Decimal`.
- Nenhum `float` substituiu valor financeiro e nenhuma conversão cambial foi
  adicionada.

### Uso de `Any`

- Todas as ocorrências de `Any` no backend foram removidas.
- `ExternalDataResult` agora é genérico e preserva o tipo concreto dos itens.
- Serializações heterogêneas de mercado retornam `dict[str, object]`, sem
  propagar `Any` às demais camadas.

### Testes

- O provedor dummy de mercado implementa o contrato real e constrói `Quote`
  completo.
- Helpers e cookies opcionais são estreitados por condições verificáveis.
- Mutações deliberadas foram isoladas em helpers que usam `setattr` ou cast
  local para `MutableMapping`; a tentativa inválida continua acontecendo em
  runtime e continua coberta por `pytest.raises`.
- Chamadas deliberadamente inválidas ao construtor e spies daily usam casts
  locais, restritos ao teste, sem exclusão de arquivo ou regra.

### Configuração e exceções locais

Nenhum arquivo de configuração de mypy/pyright foi criado ou alterado e nenhum
nível de rigor foi reduzido.

Existem somente duas exceções locais no backend, ambas na fronteira de formatos
opcionais de `connectors/io.py`:

- `openpyxl`: `type: ignore[import-untyped]` e
  `pyright: ignore[reportMissingModuleSource]`;
- `xlrd`: `type: ignore[import-untyped]` e
  `pyright: ignore[reportMissingModuleSource]`.

Justificativa: as bibliotecas são imports opcionais em runtime, já protegidos
por `ImportError` e erro de domínio claro, mas seus pacotes de stubs não estão
instalados. As exceções abrangem apenas as duas linhas de import e não ocultam
erros de uso; o workbook, worksheet e argumentos são tipados/estreitados logo
após a importação.

## Compatibilidade

Confirmações explícitas:

- ✅ nenhuma regra financeira foi alterada;
- ✅ nenhum reconhecimento ou parsing de conector foi alterado;
- ✅ nenhum resultado monetário foi alterado;
- ✅ todos os valores financeiros auditados permanecem `Decimal`;
- ✅ JOLIKA e NEI permanecem separados;
- ✅ BRL e USD permanecem separados, sem soma ou conversão implícita;
- ✅ Dashboard, API, frontend, experiência daily e orquestradores não tiveram
  contrato funcional alterado;
- ✅ nenhuma entrada recebida foi modificada;
- ✅ imutabilidade profunda do Marco 9.1 foi preservada.

## Fluxo ponta a ponta

O fluxo registry → conector → `PortfolioPosition` → validação → consolidação →
snapshot foi repetido dez vezes para cada cenário:

| Cenário | Posições | Proprietários | Moedas | Totais preservados |
|---|---:|---|---|---|
| UBS | 28 | JOLIKA | USD | USD 2.655.027,03 |
| Santander | 1 | JOLIKA | USD | USD 250,25 |
| Bradesco | 50 | NEI | BRL | BRL 734.375,98 |
| Todas | 79 | JOLIKA, NEI | BRL, USD | BRL 734.375,98; USD 2.655.277,28 |

Todas as execuções foram determinísticas, exceto `generated_at`, e todas as
posições originais permaneceram iguais antes e depois do processamento.

## Resultados

| Comando | Resultado |
|---|---|
| `mypy backend` | ✅ Success: no issues found in 48 source files |
| `pyright backend tests` | ✅ 0 errors, 0 warnings, 0 informations |
| `python -m pytest -q` | ✅ 189 passed |
| `node --test frontend/app.test.js` | ✅ 36 passed |
| `ruff check backend tests` | ✅ All checks passed |
| `python -m compileall -q backend tests` | ✅ aprovado, sem saída de erro |
| `git diff --check` | ✅ aprovado, sem saída |
| `git status --short --branch` | ✅ árvore limpa após os commits |

## Git

Commits do Marco 9.2, em ordem:

1. `0cc66e6` — `fix: complete backend static type contracts`;
2. `18d4297` — `test: align static checks with runtime guards`;
3. `dd7d657` — `refactor: remove propagated Any contracts`;
4. `e7e962f` — `refactor: complete portfolio type signatures`;
5. `7a5d85e` — `docs: publish Marco 9.2 implementation report`;
6. commit final de preservação estrita do runtime, identificado na entrega final.

- O commit final possui **1 pai**; não é commit de merge.
- Estado final da árvore: **limpa**.
- Nenhum merge foi realizado.
