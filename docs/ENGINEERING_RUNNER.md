# Runner oficial de engenharia

O runner `scripts/argos-engineering-check` é o ponto único de entrada para as
validações locais existentes no ARGOS. Ele somente coordena comandos já usados
pelo projeto: não instala dependências, não altera a aplicação e não introduz
novas regras de validação.

## Arquitetura

O runner é um script Bash autocontido. Cada validação é implementada por uma
função pequena e registrada pelo executor `run_step`, que preserva o resultado
sem interromper as etapas seguintes. Ao final, `print_summary` reúne os
resultados e retorna:

- código `0` quando todas as etapas passam;
- código diferente de `0` quando uma ou mais etapas falham.

O diretório de trabalho é sempre ajustado para a raiz do repositório. Assim, o
comando pode ser chamado de qualquer diretório.

## Fluxo

1. **Ambiente e dependências:** confirma a disponibilidade de Python, Node.js,
   Ruff, mypy e Pyright e verifica os imports de `openpyxl`, `xlrd` e `pytest`.
2. **Testes Python:** executa `python -m pytest -q`.
3. **Testes JavaScript:** executa com o test runner nativo do Node.js todos os
   arquivos `frontend/*.test.js`.
4. **Lint:** executa `ruff check backend tests`.
5. **Type checking:** executa `mypy backend` e `pyright backend tests`.
6. **Resumo final:** exibe `PASSOU` ou `FALHOU` para cada etapa.

Uma falha não impede a execução das etapas seguintes. Isso permite obter um
diagnóstico completo em uma única execução.

## Como executar

Na raiz do repositório:

```bash
./scripts/argos-engineering-check
```

Por padrão, os executáveis são `python` e `node`. Ambientes que usam nomes
diferentes podem defini-los sem editar o script:

```bash
PYTHON_BIN=python3 NODE_BIN=node ./scripts/argos-engineering-check
```

O runner apenas verifica dependências. Caso alguma esteja ausente, prepare o
ambiente do projeto antes de executar novamente; o runner nunca fará instalações.

## Exemplo de resumo

```text
PASSO 6
Resumo final

Verificando ambiente e dependências PASSOU
Executando testes Python          PASSOU
Executando testes JavaScript      PASSOU
Executando lint                   PASSOU
Executando type checking          PASSOU

PASSOU
```

## Como adicionar uma etapa

1. Crie uma função que execute a validação e retorne `0` para sucesso ou um
   código diferente de `0` para falha.
2. Antes de `print_summary`, registre-a com o próximo número sequencial:

   ```bash
   run_step 6 "Descrição da validação" nome_da_funcao
   ```

3. Atualize o número do resumo final e esta documentação.
4. Execute o runner completo e confirme tanto a saída quanto o código de retorno.

Novas etapas devem corresponder a validações adotadas oficialmente pelo projeto;
o runner não é o lugar para criar regras implícitas ou instalar ferramentas.
