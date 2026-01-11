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
- Listener `on_member_remove` para registrar saídas de membros no canal configurado.
- Sistema de advertências progressivas: comando `!adv` com ADV 1, ADV 2 e banimento automático.
- Sistema de permissões por cargos: tabela `command_permissions` no banco de dados, decorator `command_guard()` e comando `!setup_cargos`.
- Comando `!servidores` para listar e gerenciar servidores onde o bot está presente.
- Comando `!ficha` para exibir ficha completa do membro (aceita server_id, discord_id ou menção).
- Comando `!comandos` para listar todos os comandos disponíveis do bot de forma dinâmica.

### Funcionalidades implementadas (detalhamento)

#### Sistema de Cadastro
- Comando `!setup`: wizard interativo para configurar canais e cargos por servidor.
- Comando `!set`: publica/atualiza embed persistente de cadastro com botão interativo.
- Modal de cadastro: coleta Nome, ID no servidor, ID do recrutador.
- Fluxo de aprovação: botões Aprovar/Recusar com embed detalhado, atualização de apelido (Nome | IDServidor), atribuição de cargos.

#### Sistema de Advertências
- Comando `!adv <server_id> <motivo>`: sistema progressivo
  - 1ª advertência: atribui cargo ADV 1
  - 2ª advertência: atribui cargo ADV 2
  - 3ª advertência: banimento automático
- Logs no canal de advertências configurado.
- Notificações via DM para o usuário.

#### Sistema de Permissões
- Tabela `command_permissions` no banco de dados.
- Comando `!setup_cargos`: configura quais cargos podem usar cada comando.
- Decorator `command_guard()` aplicado em: `!set`, `!purge`, `!adv`.
- Administradores sempre têm permissão.

#### Gerenciamento de Servidores
- Comando `!servidores`: lista todos os servidores conectados.
- View com botões para sair de servidores (limitado a admins).

#### Ajuda e Informações
- Comando `!comandos`: lista todos os comandos disponíveis do bot.
  - Agrupa comandos por categoria para melhor organização.
  - Mostra nome do comando e descrição de cada um.
  - Atualização automática quando novos comandos são adicionados.

#### Eventos Automáticos
- `on_member_join`: atribui cargo SET, remove cargo Membro se presente, envia embed de boas-vindas.
- `on_member_remove`: registra saída no canal configurado com informações do membro.

### Melhorias Implementadas

#### Migração para Banco de Dados Assíncrono
- **Migrado de sqlite3 para aiosqlite**
  - Todos os métodos do `Database` são agora assíncronos (`async`)
  - Inicialização através de `await db.initialize()`
  - Fechamento adequado da conexão no `main()` com `finally`
  - Todas as chamadas ao banco atualizadas para usar `await`
  - Melhora significativa na performance e responsividade do bot
  - Elimina bloqueios no loop de eventos do Discord.py
  - `requirements.txt` atualizado com `aiosqlite`

#### Consolidação de Configurações
- **Configurações de servidor centralizadas no banco de dados**
  - `_get_settings()` agora usa apenas o banco de dados como fonte única de verdade
  - `config.json` usado apenas para dados globais (token)
  - Removida sincronização duplicada entre config.json e banco de dados
  - Simplificação do código e redução de pontos de falha

#### Validação e Tratamento de Erros
- **Validação de entrada no `!setup`**
  - Validação de IDs antes de converter para inteiro
  - Mensagens de erro amigáveis para IDs inválidos
  - Prevenção de exceções não tratadas
  
- **Melhorias no tratamento global de erros**
  - Tratamento melhorado para `MissingPermissions`, `BotMissingPermissions`, `CommandOnCooldown`
  - Verificação prévia de permissões no comando `!purge`
  - Mensagens de erro mais informativas e amigáveis
  - Logs de erro mais detalhados

#### Otimização de Performance
- **Busca otimizada de membros no `!adv`**
  - Nova tabela `member_server_ids` para mapeamento server_id -> discord_id
  - Busca otimizada de O(N) para O(1) usando índice do banco
  - Fallback para busca manual quando necessário
  - Atualização automática do mapeamento ao aprovar cadastro
  - Limpeza automática quando membro sai do servidor

### Próximas etapas
- Corrigir exportação de `ServerManageCog` no `actions/__init__.py`.
- Remover arquivo duplicado `set_command.py` da raiz (se obsoleto).
- Testes: Validar migração para aiosqlite em ambiente de produção.
- Documentar passos de execução (instalar deps, rodar bot, preencher config).
- Ajustar mensagens/UX conforme feedback real do servidor.
- Adicionar testes manuais/roteiro de validação.
- Registrar bugs/soluções se surgirem.

### Melhorias Técnicas de Robustez Implementadas

#### 1. Validação de Canais no !setup
- ✅ **Validação de existência**: Verifica se o canal realmente existe no servidor
- ✅ **Validação de tipo**: Garante que o ID pertence a um canal de texto (discord.TextChannel)
- ✅ **Validação de permissões**: Verifica se o bot tem permissões necessárias:
  - `view_channel`: Visualizar o canal
  - `send_messages`: Enviar mensagens
  - `embed_links`: Enviar embeds
- ✅ **Feedback claro**: Mensagens de erro específicas indicando qual canal e quais permissões estão faltando

#### 2. Tratamento de Erros Global Aprimorado
- ✅ **MissingPermissions**: Mensagem detalhada com lista de permissões necessárias que o usuário não possui
- ✅ **BotMissingPermissions**: Mensagem detalhada com lista de permissões que o bot precisa, orientando o usuário a verificar permissões do bot
- ✅ **Erros de banco de dados**: 
  - Log técnico detalhado no console para desenvolvedores
  - Mensagem amigável para usuários informando erro interno de processamento
  - Detecta erros relacionados a SQLite/aiosqlite/Database através de análise de string do erro
- ✅ **MissingRequiredArgument**: Sugere usar `!help <comando>` para ver sintaxe correta
- ✅ **BadArgument**: Mensagem clara sobre argumento inválido
- ✅ **CommandOnCooldown**: Informa tempo restante em segundos

#### 3. Centralização de Configurações (Single Source of Truth)
- ✅ **Estado atual**: `_get_settings()` já usa apenas banco de dados como fonte única de verdade
- ✅ **ConfigManager**: Ainda usado apenas para token e instanciação de Views (RegistrationView/ApprovalView)
- ✅ **Nota**: ConfigManager ainda é necessário para Views que precisam ser instanciadas antes da inicialização do bot no `setup_hook`

#### 4. Método get_user_registration no Database
- ✅ **Implementado**: Método `get_user_registration()` adicionado ao `db.py`
- ✅ **Funcionalidade**: Busca a registration mais recente de um usuário em um servidor
- ✅ **Parâmetros**: `guild_id`, `user_id`, `status` (opcional, padrão "approved")
- ✅ **Uso**: Utilizado pelo comando `!ficha` para buscar dados de cadastro

### Bugs conhecidos e soluções

#### Bugs Corrigidos Recentemente:
- ✅ **Erro de Indentação no método `migrate()`**: Corrigida indentação de linhas 46, 65, 66-79 que estavam fechando prematuramente o bloco `async with`
- ✅ **Erro de Sintaxe SQL na tabela `member_server_ids`**: Adicionadas definições das colunas antes das constraints PRIMARY KEY e UNIQUE
- ✅ **Erro de Sintaxe na linha 2007**: Separadas duas declarações que estavam na mesma linha (`raise RuntimeError` e `async with`)
- ✅ **ValueError no ticket_command.py (row 0)**: Corrigido layout UI onde botões "➕ Criar" estavam tentando compartilhar linha 0 com `ChannelSelect` que ocupa linha inteira. Botões movidos para linha 4 com lógica dinâmica para respeitar limite de 5 componentes por linha. Apenas 1-2 botões "➕ Criar" são adicionados para evitar overflow
- ✅ **AttributeError no voice_config.py**: Adicionado método `create_voice_channel` faltante na classe `VoiceChannelSelectView` com modal para criar novos canais de voz

#### Pendências:
- **Pendência**: `ServerManageCog` não está exportado no `actions/__init__.py` (precisa adicionar ao `__all__`).
- **Pendência**: Arquivo `set_command.py` na raiz parece ser duplicado/obsoleto (verificar e remover se necessário).

