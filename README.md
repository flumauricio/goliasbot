# 🛡️ GoliasBot - Sistema de Gerenciamento para Discord

O **GoliasBot** é um bot multifuncional desenvolvido em Python para automatizar a moderação, registro de membros e suporte via tickets em servidores do Discord.

## 🚀 Funcionalidades Atuais

* **🎫 Sistema de Tickets:** Abertura de canais de suporte privados com botões persistentes (não expiram).
* **👮 Moderação:** Comandos de advertência (`!warn`), limpeza de chat (`!purge`) e gestão de cargos.
* **📝 Registro:** Sistema de cadastro de membros para novos usuários.
* **📊 Banco de Dados:** Integração com SQLite para salvar configurações e histórico de moderação.
* **🛠️ Configuração Dinâmica:** Painéis configuráveis para facilitar o setup do servidor.

## 🛠️ Tecnologias Utilizadas

* [Python 3.10+](https://www.python.org/)
* [Discord.py](https://discordpy.readthedocs.io/en/stable/)
* [SQLite3](https://www.sqlite.org/index.html) (Armazenamento de dados local)

## 📋 Pré-requisitos

Antes de começar, você precisará ter instalado em sua máquina:
* Python 3.10 ou superior.
* Um Token de Bot criado no [Discord Developer Portal](https://discord.com/developers/applications).

## 🔧 Instalação e Execução

1. **Clone o repositório:**
   ```bash
   git clone [https://github.com/flumauricio/goliasbot.git](https://github.com/flumauricio/goliasbot.git)
   cd goliasbot

2. Instale as dependências:

    Bash

    pip install -r requirements.txt

3. Configure as credenciais:

    Crie ou edite o arquivo config.json.

    Adicione o seu Token e o prefixo desejado.

    Nota: Nunca envie seu config.json para o GitHub (o arquivo já está no .gitignore por segurança).

        Inicie o bot:

        Bash

        python main.py

📂 Estrutura do Projeto
main.py: Ponto de entrada do bot e inicialização das views persistentes.

db.py: Gerenciamento e conexão com o banco de dados SQLite.

actions/: Pasta contendo todos os módulos de comandos do bot.

config_manager.py: Utilitário para leitura e salvamento de configurações.

🤝 Contribuição
Contribuições são sempre bem-vindas! Se você tiver alguma ideia para melhorar o bot, sinta-se à vontade para abrir uma Issue ou enviar um Pull Request.

Desenvolvido por Mauricio
