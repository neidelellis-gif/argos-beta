# ARGOS — Controle de Qualidade

## Release 0.4

A Release só pode ser encerrada quando todos os itens abaixo forem validados pelo usuário no navegador.

### Inicialização
- [x] Servidor inicia com `python3 -m backend.server`
- [x] Interface abre em `http://localhost:8080`
- [x] Não existem erros no Terminal

### Upload
- [ ] UBS aceita CSV, XLS e XLSX
- [ ] Santander aceita XLS e XLSX
- [x] Arquivos reais dos bancos são processados sem conversão manual
- [ ] Mensagens de erro são claras

### Consolidação
- [x] Total UBS confere
- [x] Total Santander confere
- [x] Total consolidado confere
- [x] Pesos estão corretos
- [x] GLD está consolidado entre UBS e Santander
- [x] ICE e aliases relevantes estão normalizados
- [x] Nenhuma conta ou categoria aparece como ativo

### Top Holdings
- [x] Colunas Ativo, UBS, Santander e Consolidado aparecem
- [x] Cada instituição mostra valor e percentual dentro da própria carteira
- [x] Consolidado mostra valor e percentual dentro da Jolika
- [x] Ativo ausente em instituição mostra “—”
- [x] Ticker e nome não aparecem duplicados
- [x] ISIN/CUSIP só aparece quando não houver nome legível

### Privacidade
- [x] Valores ficam ocultos por padrão
- [x] Percentuais permanecem visíveis
- [x] ARGOS AI não expõe valores quando ocultos
- [x] Mostrar/Ocultar valores funciona em toda a tela

### Validação final
- [x] Testado visualmente no Safari
- [x] Usuário confirmou: “Agora ficou certo”
- [x] Git status revisado
- [x] Commit realizado na branch release/0.4
- [x] Push realizado para o GitHub

## Release 0.5 — Cockpit Executivo

### Cockpit
- [x] Resumo Executivo exibe posições consolidadas, instituições e participação percentual
- [x] Alocação por classe usa todas as posições consolidadas (não apenas Top 20)
- [x] Soma dos weights das classes fecha aproximadamente 100%
- [x] ETF/Fundo resolvido analiticamente por item (não exibido como classe final)
- [x] Liquidez separa Caixa e Caixa Remunerado
- [x] BIL permanece ativo gerador de retorno (não tratado como caixa inerte)
- [x] Concentração acima de 5% identificada e exibida com alerta
- [x] Nomenclatura executiva usa ticker amigável (GLD, não SPDR GOLD TRUST)
- [x] Próxima Ação deriva dos dados reais da carteira (determinística)
- [x] Mostrar/Ocultar valores controla também o Cockpit
- [x] Validação visual confirmada pelo usuário

### Validação final
- [x] Testado visualmente no Safari
- [x] Usuário confirmou: Release 0.5 validada visualmente
- [ ] Commit realizado na branch release/0.5
- [ ] Push realizado para o GitHub

## Definição de concluído

Uma tarefa não está concluída apenas porque compilou ou porque o agente informou sucesso.

Ela termina somente quando:
1. o código foi testado;
2. a interface foi validada;
3. o usuário aprovou o resultado.
