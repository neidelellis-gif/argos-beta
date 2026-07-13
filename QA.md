# ARGOS — Controle de Qualidade

## Release 0.4

A Release só pode ser encerrada quando todos os itens abaixo forem validados pelo usuário no navegador.

### Inicialização
- [ ] Servidor inicia com `python3 -m backend.server`
- [ ] Interface abre em `http://localhost:8080`
- [ ] Não existem erros no Terminal

### Upload
- [ ] UBS aceita CSV, XLS e XLSX
- [ ] Santander aceita XLS e XLSX
- [ ] Arquivos reais dos bancos são processados sem conversão manual
- [ ] Mensagens de erro são claras

### Consolidação
- [ ] Total UBS confere
- [ ] Total Santander confere
- [ ] Total consolidado confere
- [ ] Pesos estão corretos
- [ ] GLD está consolidado entre UBS e Santander
- [ ] ICE e aliases relevantes estão normalizados
- [ ] Nenhuma conta ou categoria aparece como ativo

### Top Holdings
- [ ] Colunas Ativo, UBS, Santander e Consolidado aparecem
- [ ] Cada instituição mostra valor e percentual dentro da própria carteira
- [ ] Consolidado mostra valor e percentual dentro da Jolika
- [ ] Ativo ausente em instituição mostra “—”
- [ ] Ticker e nome não aparecem duplicados
- [ ] ISIN/CUSIP só aparece quando não houver nome legível

### Privacidade
- [ ] Valores ficam ocultos por padrão
- [ ] Percentuais permanecem visíveis
- [ ] ARGOS AI não expõe valores quando ocultos
- [ ] Mostrar/Ocultar valores funciona em toda a tela

### Validação final
- [ ] Testado visualmente no Safari
- [ ] Usuário confirmou: “Agora ficou certo”
- [ ] Git status revisado
- [ ] Commit realizado na branch release/0.4
- [ ] Push realizado para o GitHub

## Definição de concluído

Uma tarefa não está concluída apenas porque compilou ou porque o agente informou sucesso.

Ela termina somente quando:
1. o código foi testado;
2. a interface foi validada;
3. o usuário aprovou o resultado.
