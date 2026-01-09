## Plano do Bot de Registro de Membros (Discord) — Status Inicial

### Escopo atual (confirmado)
- Bot em Python.
- Armazenamento em SQLite.
- Configuração central em `config.json` contendo tokens, IDs de cargos e canais.
- Biblioteca: `discord.py` (v2+, com views/modals).
- Comandos: `!setup` (configurar `config.json`), `!set` (publicar embed de cadastro persistente).
- Fluxo de cadastro: embed com botão -> modal (Nome, ID no servidor, ID de quem recrutou) -> validação -> envio para canal de aprovação -> botão Aprovar/Recusar -> se aprovado, dá cargo Membro e remove cargo SET; se recusado, avisa usuário.
- Todos que entrarem recebem automaticamente cargo SET.
- Estrutura escalável: comandos modulares em pasta `actions/`.
- Suporte a múltiplos servidores (guilds).
- Logs em stdout estruturado.

### Etapas concluídas
- Criação inicial do plano do projeto.
- Criação de `chat.md` com resumo do chat.
- Definição de arquitetura Python com `discord.py`, SQLite, config em `config.json`.
- Implementados cogs/comandos: `!setup` (wizard interativo admin) e `!set` (publica/atualiza embed persistente).
- Views e modal de cadastro com validações e fluxo de aprovação/reprovação via botões.
- Listener `on_member_join` atribui cargo SET automaticamente.
- Persistência de mensagens/views e restauração de pendências na inicialização.
- Comando `!purge` (admin) para limpar canal; autodeleção das mensagens de comando.
- Canal de boas-vindas configurável; embed de boas-vindas com dados do membro.
- Embeds aprimorados: `!set` com regras e estilo; aprovação/cadastro com thumbnail/avatar e campos extras.

### Próximas etapas
- Documentar passos de execução (instalar deps, rodar bot, preencher config).
- Ajustar mensagens/UX conforme feedback real do servidor.
- Adicionar testes manuais/roteiro de validação.
- Registrar bugs/soluções se surgirem.

### Bugs conhecidos e soluções
- Nenhum bug registrado até o momento.

