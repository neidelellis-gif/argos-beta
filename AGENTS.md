# ARGOS — Instruções para Agentes de IA

## Missão

Simplificar para melhorar a decisão.

O ARGOS é uma plataforma de inteligência para gestão patrimonial. Seu objetivo é reduzir o tempo entre receber informação e tomar uma decisão de investimento de alta qualidade.

## Patrimônios

Os patrimônios devem permanecer totalmente separados.

### JOLIKA

Perfil institucional.

Instituições atuais:
- UBS
- Santander

Meta-base:
- 12% a.a.

Faixa aceitável:
- 10% a 12% a.a.

Objetivo:
- superar 12% quando houver oportunidades assimétricas sem aumento excessivo de risco;
- controle de risco;
- preservação patrimonial;
- clareza para prestação de contas aos sócios.

A UBS e o Santander devem ser analisados separadamente e somente depois consolidados na visão total da Jolika.

### NEI

Perfil pessoal e mais arrojado.

Estrutura atual:
- Bradesco
  - Ágora
- Monte Bravo
- espaço para novas instituições
- múltiplas exchanges e carteiras cripto

Nunca misturar NEI com JOLIKA.

## Princípios

1. Simplificar para melhorar a decisão.
2. Menos informação, mais decisão.
3. Toda recomendação deve ter evidências.
4. Toda evidência deve ser rastreável até a fonte.
5. O ARGOS recomenda; o gestor decide.
6. A tela principal deve ser simples, leve e rápida.
7. O resumo executivo deve ter no máximo 10 linhas.
8. Valores financeiros ficam ocultos por padrão.
9. Deve existir botão Mostrar/Ocultar valores.
10. A análise externa considera por padrão as últimas 48 horas.
11. Eventos estruturais permanecem visíveis enquanto forem relevantes.
12. Não adicionar complexidade sem melhorar decisão ou economizar tempo.

## Arquitetura

Evolução em camadas simples:

1. Connectors
2. Normalização
3. Portfolio Engine
4. Consolidação
5. ARGOS AI
6. Interface
7. Relatórios

Cada instituição possui seu próprio conector.

Os conectores transformam formatos externos em estrutura interna padronizada.

O restante do sistema não deve depender diretamente de CSV, XLS, XLSX, PDF ou API.

## Regras de Desenvolvimento

- Leia este arquivo antes de alterar código.
- Trabalhe somente no repositório local atual.
- GitHub é a fonte oficial.
- Não usar Google Drive como fonte de código.
- Não alterar arquivos fora da tarefa sem necessidade.
- Não criar arquitetura excessiva.
- Reutilizar código existente.
- Evitar duplicação.
- Manter compatibilidade com o que já funciona.
- Criar mensagens de erro claras.
- Adicionar testes quando possível.
- Nunca afirmar que algo foi testado se não foi executado.
- Não fechar tarefa com bugs conhecidos.
- Não apagar arquivos ou dados sem autorização explícita.
- Antes de executar comandos, explicar em uma frase o que será feito e por quê.
- Não iniciar background agents ou Explore agents sem autorização explícita do usuário.
- Quando a tarefa pedir poucos arquivos, não inspecionar áreas não relacionadas.

## Git

Branches:
- main: produção estável
- develop: integração
- release/0.4: release atual

Toda alteração deve ser pequena, testável e registrada.

## Regra final

Quando houver dúvida entre uma solução sofisticada e uma solução simples, escolha a solução simples que preserve qualidade, segurança e capacidade de evolução.
