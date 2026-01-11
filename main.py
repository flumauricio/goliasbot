import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands

from actions import (
    ApprovalView,
    RegistrationCog,
    RegistrationView,
    SetCog,
    SetupCog,
    PurgeCog,
    WarnCog,
    FichaCog,
    TicketCog,
    TicketOpenView,
)
# IMPORTAR O NOVO COG
from actions.server_manage import ServerManageCog
from actions.help_command import HelpCog 

from config_manager import ConfigManager
from db import Database

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
LOGGER = logging.getLogger("bot")

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
DB_PATH = BASE_DIR / "bot.sqlite"

async def build_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    config = ConfigManager(CONFIG_PATH)
    db = Database(DB_PATH)
    await db.initialize()

    class RegistrationBot(commands.Bot):
        async def setup_hook(self) -> None:
            await self.add_cog(SetupCog(self, db, config))
            await self.add_cog(SetCog(self, db, config))
            await self.add_cog(PurgeCog(self))
            await self.add_cog(WarnCog(self, db, config))
            await self.add_cog(RegistrationCog(self, db, config))
            await self.add_cog(FichaCog(self, db))
            await self.add_cog(TicketCog(self, db))
            
            # ADICIONAR O NOVO COG AQUI
            await self.add_cog(ServerManageCog(self))
            await self.add_cog(HelpCog(self))
            
            self.add_view(RegistrationView(db, config))
            self.add_view(TicketOpenView(db))
            await restore_pending_views(self, db, config)

    bot = RegistrationBot(command_prefix="!", intents=intents)
    bot.config_manager = config
    bot.db = db

    @bot.event
    async def on_ready():
        LOGGER.info("Bot conectado como %s", bot.user)

    @bot.event
    async def on_command_error(ctx, error):
        # MissingPermissions: usuário não tem permissão
        if isinstance(error, commands.MissingPermissions):
            missing = [perm.replace("_", " ").replace("guild", "servidor").title() for perm in error.missing_permissions]
            await ctx.reply(
                f"❌ Você não tem permissão para usar este comando.\n"
                f"**Permissões necessárias:** {', '.join(missing)}",
                delete_after=15
            )
        
        # BotMissingPermissions: bot não tem permissão
        elif isinstance(error, commands.BotMissingPermissions):
            missing = [perm.replace("_", " ").replace("guild", "servidor").title() for perm in error.missing_permissions]
            await ctx.reply(
                f"❌ Eu não tenho as permissões necessárias para executar este comando.\n"
                f"**Permissões necessárias:** {', '.join(missing)}\n"
                f"Por favor, verifique as permissões do bot no servidor.",
                delete_after=20
            )
        
        # MissingRequiredArgument: argumento obrigatório faltando
        elif isinstance(error, commands.MissingRequiredArgument):
            param_name = error.param.name if error.param else "argumento"
            await ctx.reply(
                f"❌ Faltando argumento obrigatório: `{param_name}`.\n"
                f"💡 Use `!help {ctx.command.name}` para ver a sintaxe correta.",
                delete_after=15
            )
        
        # CommandNotFound: comando não existe (ignora silenciosamente)
        elif isinstance(error, commands.CommandNotFound):
            pass
        
        # CommandOnCooldown: comando em cooldown
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.reply(
                f"⏳ Este comando está em cooldown. Tente novamente em {error.retry_after:.1f} segundos.",
                delete_after=5
            )
        
        # BadArgument: argumento inválido
        elif isinstance(error, commands.BadArgument):
            await ctx.reply(
                f"❌ Argumento inválido: {str(error)}",
                delete_after=10
            )
        
        # Erros de banco de dados (SQLite/aiosqlite)
        elif isinstance(error, (RuntimeError, Exception)) and (
            "database" in str(error).lower() or 
            "sqlite" in str(error).lower() or
            "aiosqlite" in str(error).lower() or
            "Database não inicializado" in str(error)
        ):
            LOGGER.error(
                "Erro de banco de dados no comando %s: %s",
                ctx.command,
                error,
                exc_info=error
            )
            await ctx.reply(
                "❌ Ocorreu um erro interno ao processar sua solicitação.\n"
                "Por favor, tente novamente em alguns instantes. Se o problema persistir, entre em contato com um administrador.",
                delete_after=15
            )
        
        # Outros erros não tratados
        else:
            LOGGER.error(
                "Erro não tratado no comando %s: %s",
                ctx.command,
                error,
                exc_info=error
            )
            await ctx.reply(
                "❌ Ocorreu um erro ao executar este comando. Tente novamente ou verifique os logs.",
                delete_after=10
            )

    return bot

# --- Restante do arquivo (restore_pending_views e main) permanece igual ---
async def restore_pending_views(bot: commands.Bot, db: Database, config: ConfigManager):
    pending = await db.list_pending_registrations()
    for reg in pending:
        guild = bot.get_guild(int(reg["guild_id"]))
        if not guild:
            continue
        view = ApprovalView(db, config, requester_id=int(reg["user_id"]))
        view.registration_id = reg["id"]
        message_id = reg.get("approval_message_id")
        if not message_id:
            continue
        try:
            settings = await db.get_settings(int(reg["guild_id"]))
            channel_id = settings.get("channel_approval")
            if not channel_id:
                continue
            channel = guild.get_channel(int(channel_id))
            if not channel:
                continue
            bot.add_view(view, message_id=int(message_id))
        except Exception as exc:
            LOGGER.warning("Falha ao restaurar view para registro %s: %s", reg["id"], exc)

async def main():
    bot = await build_bot()
    config = bot.config_manager
    if not config.token:
        LOGGER.error("Token não configurado em config.json")
        return
    try:
        async with bot:
            await bot.start(config.token)
    finally:
        await bot.db.close()

if __name__ == "__main__":
    asyncio.run(main())