# Padrão de Desenvolvimento do ARGOS

## Objetivo

Este documento define o fluxo mínimo e permanente para alterar o ARGOS. A regra
central é simples: toda mudança deve ser pequena, rastreável, testada de acordo
com seu impacto e revisada antes do merge.

O GitHub é a fonte oficial do código. `main` representa produção estável,
`develop` representa integração e `release/<versão>` representa a preparação de
uma versão. Exceções ao fluxo devem ser justificadas no pull request.

## Fluxo de branches

Cada branch deve ter um objetivo único e vida curta. Antes do merge, deve estar
atualizada em relação ao destino e atender aos testes mínimos aplicáveis.

| Origem | Destino | Objetivo |
| --- | --- | --- |
| `develop` | `feature/<descrição>` | Desenvolver uma funcionalidade ou melhoria isolada. |
| `develop` | `fix/<descrição>` | Corrigir comportamento ainda não publicado em produção. |
| `develop` | `docs/<descrição>` | Alterar somente documentação. |
| `develop` | `release/<versão>` | Estabilizar uma versão, permitindo apenas correções necessárias à liberação. |
| `release/<versão>` | `main` | Publicar uma versão validada. |
| `main` | `hotfix/<descrição>` | Corrigir com urgência um problema em produção. |
| `hotfix/<descrição>` | `main` | Publicar a correção urgente validada. |

Após o merge de `release/<versão>` ou `hotfix/<descrição>` em `main`, as mesmas
alterações devem ser incorporadas a `develop` para impedir divergência. Não são
permitidos commits diretos em `main`, salvo indisponibilidade do fluxo normal e
com registro da justificativa.

## Papéis e responsabilidades

| Papel | Responsabilidade |
| --- | --- |
| **Autor** | Implementar a mudança, manter o escopo, classificar o risco, executar e registrar os testes aplicáveis e corrigir os problemas encontrados. |
| **Revisor** | Avaliar correção, clareza, compatibilidade, segurança, testes e aderência ao escopo; solicitar ajustes quando necessário. |
| **Responsável técnico** | Resolver dúvidas de arquitetura ou risco, confirmar exceções ao padrão e definir validações adicionais para mudanças de risco alto ou crítico. |
| **Aprovador do merge** | Confirmar que revisão, testes e aprovações exigidas foram concluídos e então autorizar o merge no destino correto. |

Uma pessoa pode exercer mais de um papel quando a equipe for pequena, mas o
autor não deve ser o único aprovador de mudanças de risco alto ou crítico.

## Classificação de risco

O autor classifica a mudança pelo maior impacto plausível. Em caso de dúvida,
adota-se o nível superior. A classificação determina a profundidade da revisão,
sem criar etapas que não reduzam risco real.

| Nível | Critério | Exemplos | Tratamento mínimo |
| --- | --- | --- | --- |
| **Baixo** | Sem efeito no comportamento em produção ou mudança isolada e facilmente reversível. | Documentação, texto, teste sem alteração funcional. | Revisão do escopo e testes aplicáveis. |
| **Médio** | Altera comportamento limitado, sem afetar dados sensíveis, segurança ou disponibilidade geral. | Regra local, endpoint não crítico, componente de interface. | Revisão técnica e testes do fluxo alterado. |
| **Alto** | Pode afetar dados, integrações, cálculos, disponibilidade ou vários fluxos. | Conector, normalização, consolidação, migração compatível, autenticação. | Revisão independente, testes de integração e plano de reversão. |
| **Crítico** | Pode causar perda ou exposição de dados, decisão patrimonial incorreta, indisponibilidade ampla ou quebra irreversível. | Separação entre patrimônios, cálculo financeiro central, credenciais, migração destrutiva. | Aprovação do responsável técnico, validação ponta a ponta e plano de reversão testado antes do merge. |

## Testes mínimos por tipo de alteração

Devem ser executadas apenas as linhas aplicáveis à mudança. Falhas conhecidas
não podem ser ignoradas: devem ser corrigidas ou impedir o merge. O pull request
registra os comandos executados e seus resultados.

| Tipo de alteração | Testes mínimos |
| --- | --- |
| Somente documentação | Revisão de links, comandos e consistência; `git diff --check`. |
| Backend ou regra de negócio | Testes unitários do código alterado; testes de regressão do fluxo afetado; lint e análise de tipos aplicáveis. |
| API ou contrato | Testes unitários e de integração; compatibilidade dos consumidores; validação de erros e respostas. |
| Conector, importação ou normalização | Testes com amostras representativas; dados inválidos e ausentes; garantia de separação por patrimônio e instituição; regressão da estrutura normalizada. |
| Cálculo, consolidação ou dado financeiro | Testes unitários com resultados esperados; casos-limite; integração; regressão e conferência da separação entre JOLIKA e NEI. |
| Frontend | Testes automatizados do componente ou fluxo; verificação manual do estado alterado; responsividade e Mostrar/Ocultar valores quando aplicável. |
| Configuração, dependência ou infraestrutura | Validação em ambiente equivalente; inicialização da aplicação; regressão dos fluxos afetados e procedimento de reversão. |
| Segurança, autenticação ou dados sensíveis | Testes de autorização, negação de acesso, exposição de dados e regressão; validação do responsável técnico. |

Quando a mudança atingir mais de um tipo, os mínimos se acumulam. Para a suíte
completa de engenharia, usar `./scripts/argos-engineering-check`.

## Evidências e merge

O pull request deve informar objetivo, risco, impacto, testes executados e, para
risco alto ou crítico, como reverter a mudança. Evidências devem ser suficientes
para que o revisor reproduza a validação e rastreie a origem de dados ou decisões
relevantes. O merge somente ocorre com os testes aplicáveis aprovados, sem bugs
conhecidos no escopo e com a aprovação definida na seção de papéis.

## Checklist operacional

- [ ] O escopo está limitado ao objetivo declarado.
- [ ] A branch segue a matriz de fluxo.
- [ ] O risco foi classificado pela matriz de risco.
- [ ] Os testes da matriz aplicável foram executados e registrados.
- [ ] A revisão e a aprovação previstas para o risco foram concluídas.
- [ ] Não há bug conhecido no escopo nem divergência pendente com `develop`.

Este checklist confirma a aplicação das normas anteriores; ele não cria regras
adicionais.
