# ARGOS — Marco Validado: Premissas Mestres da JOLIKA

**Data:** 08/09/2026  
**Branch:** `feature/jolika-master-assumptions`  
**Base anterior auditada:** `5b74f60`

## Escopo concluído

Este marco registra a formalização e integração das Premissas Mestres da JOLIKA à Etapa 3 do Método ARGOS de Análise Patrimonial em 5 Etapas.

## Premissas Mestres formalizadas

A fonte oficial versionada é:

`docs/jolika/PREMISSAS_MESTRES_JOLIKA_v1.0.md`

Foram aprovadas cinco premissas:

1. Objetivo Patrimonial;
2. Retorno Esperado;
3. Risco Aceitável;
4. Alocação e Diversificação;
5. Regras de Decisão.

A meta-base de retorno é 12% a.a. em USD como referência, não como piso nem teto.

## Integração da Etapa 3

A Etapa 3 — Aderência às Premissas Mestres da JOLIKA — passou a utilizar a fonte oficial.

A análise preserva a regra de evidência: o ARGOS não presume aderência quando a fotografia atual da carteira não permite medir determinada premissa. Retorno, qualidade das teses e processo decisório somente podem receber conclusões quando houver evidência suficiente.

A integração foi aplicada às análises individuais UBS/Santander e à análise consolidada JOLIKA.

## Etapa 4

A Etapa 4 — Carteira × ambiente de mercado — permanece deliberadamente em **BASE LIMITADA**.

O contexto editorial de mercado e newsletters ainda não foi conectado à análise. Nenhuma conclusão externa deve ser presumida até a implementação desse bloco.

## Validação automatizada

Após a integração das Premissas Mestres:

- testes específicos: 6 passed;
- suíte completa: **1085 passed, 1 skipped, 0 failures**.

Comando oficial: `python -m pytest`.

## Validação visual

A análise consolidada JOLIKA foi validada no navegador com:

- patrimônio consolidado: US$ 5,939,098.22;
- 66 posições consolidadas;
- 63 ativos econômicos consolidados;
- Etapa 3 exibida como **ANALISADA**;
- cinco Premissas Mestres apresentadas individualmente;
- Etapa 4 mantida como **BASE LIMITADA**;
- Etapa 5 preservada.

## Correção do carregamento consolidado

Durante a validação foi identificado um flash visual: ao entrar em `consolidated=1`, a página podia mostrar momentaneamente o conteúdo da última instituição individual antes da apresentação consolidada.

A correção foi aplicada para impedir a exibição do estado individual durante o carregamento. A tela consolidada agora é revelada somente quando o relatório consolidado está pronto.

Validação visual final: a navegação passou diretamente para **JOLIKA consolidada**, sem exibir Santander ou UBS durante a transição.

## Estado deste marco

O bloco **Premissas Mestres da JOLIKA + Etapa 3** está funcionalmente e visualmente validado.

Este marco deve ser preservado antes do início do próximo bloco:

**Etapa 4 — Carteira × ambiente de mercado.**
