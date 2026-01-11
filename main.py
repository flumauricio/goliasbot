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
    TicketControlView,
    ActionConfigCog,
    ActionCog,
    ActionView,
    InviteCog,
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
            await self.add_cog(ActionConfigCog(self, db))
            await self.add_cog(ActionCog(self, db))
            
            # ADICIONAR O NOVO COG AQUI
            await self.add_cog(ServerManageCog(self))
            await self.add_cog(HelpCog(self))
            await self.add_cog(InviteCog(self))
            
            self.add_view(RegistrationView(db, config))
            self.add_view(TicketOpenView(db))
            self.add_view(TicketControlView(db))
            await restore_pending_views(self, db, config)
            await restore_ticket_views(self, db)

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
    """Restaura views de registros pendentes."""
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

async def restore_action_views(bot: commands.Bot, db: Database):
    """Restaura views de ações ativas para garantir persistência."""
    try:
        # Busca todas as ações com status 'open' ou 'closed'
        for guild in bot.guilds:
            actions = await db.list_active_actions(guild.id, status="open")
            actions += await db.list_active_actions(guild.id, status="closed")
            
            for action in actions:
                message_id = action.get("message_id")
                if not message_id or not str(message_id).isdigit():
                    continue
                
                channel_id = action.get("channel_id")
                if not channel_id or not str(channel_id).isdigit():
                    continue
                
                try:
                    channel = guild.get_channel(int(channel_id))
                    if not channel:
                        channel = await guild.fetch_channel(int(channel_id))
                    
                    if channel:
                        try:
                            message = await channel.fetch_message(int(message_id))
                            view = ActionView(bot, db, action["id"])
                            bot.add_view(view, message_id=int(message_id))
                        except discord.NotFound:
                            LOGGER.warning("Mensagem de ação %s não encontrada", action["id"])
                        except Exception as exc:
                            LOGGER.warning("Erro ao restaurar view de ação %s: %s", action["id"], exc)
                except Exception as exc:
                    LOGGER.warning("Erro ao buscar canal para ação %s: %s", action["id"], exc)
    except Exception as exc:
        LOGGER.error("Erro ao restaurar views de ações: %s", exc, exc_info=True)

async def restore_ticket_views(bot: commands.Bot, db: Database):
    """Restaura views de tickets abertos para garantir persistência."""
    try:
        open_tickets = await db.list_open_tickets()
        restored_count = 0
        
        for ticket in open_tickets:
            try:
                # Converte guild_id com validação
                try:
                    guild_id = int(ticket["guild_id"]) if ticket.get("guild_id") and str(ticket["guild_id"]).isdigit() else None
                except (ValueError, TypeError):
                    guild_id = None
                
                if not guild_id:
                    continue
                
                guild = bot.get_guild(guild_id)
                if not guild:
                    continue
                
                # Converte channel_id com validação e fallback
                try:
                    channel_id = int(ticket["channel_id"]) if ticket.get("channel_id") and str(ticket["channel_id"]).isdigit() else None
                except (ValueError, TypeError):
                    channel_id = None
                
                if not channel_id:
                    continue
                
                channel = guild.get_channel(channel_id)
                if not channel or not isinstance(channel, discord.TextChannel):
                    try:
                        fetched = await guild.fetch_channel(channel_id)
                        if isinstance(fetched, discord.TextChannel):
                            channel = fetched
                        else:
                            continue
                    except (discord.NotFound, discord.HTTPException):
                        continue
                
                # Busca a mensagem com o embed do ticket
                ticket_id = ticket["id"]
                author_id = int(ticket["user_id"])
                # Apenas tickets abertos são restaurados (list_open_tickets já filtra)
                is_closed = False
                
                # Procura a mensagem com o embed do ticket
                async for msg in channel.history(limit=100):
                    if msg.embeds and msg.embeds[0].footer:
                        footer_text = str(msg.embeds[0].footer.text)
                        if f"Ticket #{ticket_id}" in footer_text:
                            # Restaura a view
                            view = TicketControlView(db, ticket_id, author_id, is_closed)
                            bot.add_view(view, message_id=msg.id)
                            restored_count += 1
                            break
            except Exception as exc:
                LOGGER.warning("Falha ao restaurar view para ticket %s: %s", ticket.get("id"), exc)
        
        if restored_count > 0:
            LOGGER.info("Restauradas %d views de tickets abertos", restored_count)
    except Exception as exc:
        LOGGER.error("Erro ao restaurar views de tickets: %s", exc, exc_info=exc)

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