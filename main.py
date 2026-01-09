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
)
# IMPORTAR O NOVO COG
from actions.server_manage import ServerManageCog 

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

def build_bot() -> commands.Bot:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True

    config = ConfigManager(CONFIG_PATH)
    db = Database(DB_PATH)

    class RegistrationBot(commands.Bot):
        async def setup_hook(self) -> None:
            await self.add_cog(SetupCog(self, db, config))
            await self.add_cog(SetCog(self, db, config))
            await self.add_cog(PurgeCog(self))
            await self.add_cog(WarnCog(self, db, config))
            await self.add_cog(RegistrationCog(self, db, config))
            
            # ADICIONAR O NOVO COG AQUI
            await self.add_cog(ServerManageCog(self))
            
            self.add_view(RegistrationView(db, config))
            await restore_pending_views(self, db, config)

    bot = RegistrationBot(command_prefix="!", intents=intents)
    bot.config_manager = config
    bot.db = db

    @bot.event
    async def on_ready():
        LOGGER.info("Bot conectado como %s", bot.user)

    @bot.event
    async def on_command_error(ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("Você não tem permissão para usar este comando.")
        elif isinstance(error, commands.CommandNotFound):
            pass
        else:
            LOGGER.error("Erro no comando %s: %s", ctx.command, error)

    return bot

# --- Restante do arquivo (restore_pending_views e main) permanece igual ---
async def restore_pending_views(bot: commands.Bot, db: Database, config: ConfigManager):
    pending = db.list_pending_registrations()
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
            channel_id = (
                db.get_settings(int(reg["guild_id"])).get("channel_approval")
                or config.guild_channels(int(reg["guild_id"])).get("approval")
            )
            if not channel_id:
                continue
            channel = guild.get_channel(int(channel_id))
            if not channel:
                continue
            bot.add_view(view, message_id=int(message_id))
        except Exception as exc:
            LOGGER.warning("Falha ao restaurar view para registro %s: %s", reg["id"], exc)

async def main():
    bot = build_bot()
    config = bot.config_manager
    if not config.token:
        LOGGER.error("Token não configurado em config.json")
        return
    async with bot:
        await bot.start(config.token)

if __name__ == "__main__":
    asyncio.run(main())