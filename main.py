import asyncio
import logging
import threading
from pathlib import Path

import discord
from discord.ext import commands

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
            # Inicializa variáveis de controle de processamento
            self._processing_messages = set()
            self._processing_lock = threading.Lock()
            
            # Lista de extensões a carregar
            extensions = [
                'actions.setup_command',
                'actions.purge_command',
                'actions.ficha_command',
                'actions.set_command',
                'actions.warn_command',
                'actions.registration',
                'actions.ticket_command',
                'actions.action_config',
                'actions.action_system',
                'actions.server_manage',
                'actions.help_command',
                'actions.invite_command',
                'actions.voice_config',
                'actions.voice_monitor',
                'actions.voice_commands',
                'actions.naval_command',
                'actions.analytics',
                'actions.hierarchy.promotion_engine',
                'actions.hierarchy.commands',
            ]
            
            for ext in extensions:
                try:
                    await self.load_extension(ext)
                except Exception as e:
                    LOGGER.error("❌ Erro ao carregar %s: %s", ext, e, exc_info=True)
            
            # Restaura views persistentes
            from actions.registration import RegistrationView, ApprovalView
            from actions.ticket_command import TicketOpenView, TicketControlView
            from actions.action_system import ActionView
            from actions.hierarchy.approval_view import PromotionApprovalView
            from actions.hierarchy.repository import HierarchyRepository
            from actions.hierarchy.cache import HierarchyCache
            from actions.hierarchy.models import PromotionRequest
            
            self.add_view(RegistrationView(db, config))
            self.add_view(TicketOpenView(db))
            self.add_view(TicketControlView(db))
            
            # Restaura views de aprovação de hierarquia pendentes (com custom_id único)
            cache = HierarchyCache()
            repository = HierarchyRepository(db, cache)
            
            for guild in self.guilds:
                try:
                    async with db._conn.cursor() as cur:
                        await cur.execute(
                            """
                            SELECT * FROM promotion_requests
                            WHERE guild_id = ? AND status = 'pending' AND message_id IS NOT NULL
                            """,
                            (str(guild.id),)
                        )
                        rows = await cur.fetchall()
                    
                    if not rows:
                        continue
                    
                    # Busca colunas
                    await cur.execute("PRAGMA table_info(promotion_requests)")
                    col_info = await cur.fetchall()
                    columns = [col[1] for col in col_info]
                    
                    for row in rows:
                        try:
                            request_dict = dict(zip(columns, row))
                            request = PromotionRequest.from_dict(request_dict)
                            
                            if not request.id or not request.message_id:
                                continue
                            
                            # Cria view com custom_id único
                            detailed_reason = request.reason or "Atende todos os requisitos"
                            view = PromotionApprovalView(self, db, request, detailed_reason)
                            
                            # Registra view com message_id para persistência
                            # O custom_id único permite que o bot processe cliques mesmo após reinício
                            self.add_view(view, message_id=int(request.message_id))
                            
                            LOGGER.debug(
                                "View de aprovação restaurada: request_id=%d, message_id=%d",
                                request.id, request.message_id
                            )
                            
                        except Exception as exc:
                            LOGGER.warning("Erro ao restaurar view de aprovação: %s", exc)
                except Exception as exc:
                    LOGGER.warning("Erro ao restaurar views de aprovação em %s: %s", guild.id, exc)
            
            # Restaura views de aprovação de hierarquia pendentes (método antigo para compatibilidade)
            await restore_hierarchy_approval_views(self, db)
            
            await restore_pending_views(self, db, config)
            await restore_ticket_views(self, db)

    bot = RegistrationBot(command_prefix="!", intents=intents)
    
    # Armazena referências para uso nas extensões (antes do setup_hook)
    bot.db = db
    bot.config_manager = config

    @bot.event
    async def on_ready():
        LOGGER.info("Bot conectado como %s", bot.user)
        
        # Limpa sessões órfãs de voz
        for guild in bot.guilds:
            try:
                # Coleta IDs de usuários realmente em call
                active_user_ids = set()
                for channel in guild.voice_channels:
                    for member in channel.members:
                        active_user_ids.add(member.id)
                
                # Limpa sessões de usuários que não estão mais em call
                await db.cleanup_stale_sessions(guild.id, active_user_ids)
            except Exception as exc:
                LOGGER.error("Erro ao limpar sessões órfãs em %s: %s", guild.id, exc)

    @bot.event
    async def on_command_error(ctx, error):
        # MissingPermissions: usuário não tem permissão
        if isinstance(error, commands.MissingPermissions):
            missing = [perm.replace("_", " ").replace("guild", "servidor").title() for perm in error.missing_permissions]
            await ctx.send(
                f"❌ Você não tem permissão para usar este comando.\n"
                f"**Permissões necessárias:** {', '.join(missing)}",
                delete_after=15
            )
        
        # BotMissingPermissions: bot não tem permissão
        elif isinstance(error, commands.BotMissingPermissions):
            missing = [perm.replace("_", " ").replace("guild", "servidor").title() for perm in error.missing_permissions]
            await ctx.send(
                f"❌ Eu não tenho as permissões necessárias para executar este comando.\n"
                f"**Permissões necessárias:** {', '.join(missing)}\n"
                f"Por favor, verifique as permissões do bot no servidor.",
                delete_after=20
            )
        
        # MissingRequiredArgument: argumento obrigatório faltando
        elif isinstance(error, commands.MissingRequiredArgument):
            param_name = error.param.name if error.param else "argumento"
            await ctx.send(
                f"❌ Faltando argumento obrigatório: `{param_name}`.\n"
                f"💡 Use `!help {ctx.command.name}` para ver a sintaxe correta.",
                delete_after=15
            )
        
        # CommandNotFound: comando não existe (ignora silenciosamente)
        elif isinstance(error, commands.CommandNotFound):
            pass
        
        # CheckFailure: check de permissão falhou (command_guard já enviou mensagem)
        elif isinstance(error, commands.CheckFailure):
            # O command_guard já envia mensagem ao usuário, então apenas logamos em nível debug
            LOGGER.debug("Check de permissão falhou para comando %s: %s", ctx.command, error)
            pass
        
        # CommandOnCooldown: comando em cooldown
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(
                f"⏳ Este comando está em cooldown. Tente novamente em {error.retry_after:.1f} segundos.",
                delete_after=5
            )
        
        # BadArgument: argumento inválido
        elif isinstance(error, commands.BadArgument):
            await ctx.send(
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
            await ctx.send(
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
            await ctx.send(
                "❌ Ocorreu um erro ao executar este comando. Tente novamente ou verifique os logs.",
                delete_after=10
            )

    return bot

# --- Restante do arquivo (restore_pending_views e main) permanece igual ---
async def restore_pending_views(bot: commands.Bot, db: Database, config: ConfigManager):
    """Restaura views de registros pendentes."""
    from actions.registration import ApprovalView
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
                            from actions.action_system import ActionView
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

async def restore_hierarchy_approval_views(bot: commands.Bot, db: Database):
    """Restaura views de aprovação de hierarquia pendentes."""
    try:
        from actions.hierarchy.repository import HierarchyRepository
        from actions.hierarchy.cache import HierarchyCache
        from actions.hierarchy.approval_view import PromotionApprovalView, build_approval_embed
        from actions.hierarchy.models import PromotionRequest
        
        cache = HierarchyCache()
        repository = HierarchyRepository(db, cache)
        
        # Busca todos os pedidos pendentes
        for guild in bot.guilds:
            try:
                # Busca pedidos pendentes usando repository
                async with db._conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT * FROM promotion_requests
                        WHERE guild_id = ? AND status = 'pending' AND message_id IS NOT NULL
                        """,
                        (str(guild.id),)
                    )
                    rows = await cur.fetchall()
                
                if not rows:
                    continue
                
                # Busca colunas
                await cur.execute("PRAGMA table_info(promotion_requests)")
                col_info = await cur.fetchall()
                columns = [col[1] for col in col_info]
                
                for row in rows:
                    try:
                        request_dict = dict(zip(columns, row))
                        # Converte valores None para None explicitamente
                        for key in request_dict:
                            if request_dict[key] is None:
                                request_dict[key] = None
                        request = PromotionRequest.from_dict(request_dict)
                        
                        if not request.message_id:
                            continue
                        
                        # Busca canal de staff
                        settings = await db.get_settings(guild.id)
                        staff_channel_id = settings.get("channel_warnings")
                        
                        if not staff_channel_id:
                            continue
                        
                        staff_channel = guild.get_channel(int(staff_channel_id))
                        if not staff_channel:
                            continue
                        
                        # Tenta buscar mensagem
                        try:
                            message = await staff_channel.fetch_message(int(request.message_id))
                            
                            # Recria view (usa reason do request como detailed_reason)
                            detailed_reason = request.reason or "Atende todos os requisitos"
                            view = PromotionApprovalView(bot, db, request, detailed_reason)
                            bot.add_view(view, message_id=int(request.message_id))
                            
                            LOGGER.debug(
                                "View de aprovação restaurada: request_id=%d, message_id=%d",
                                request.id, request.message_id
                            )
                            
                        except discord.NotFound:
                            LOGGER.debug("Mensagem de aprovação %s não encontrada", request.message_id)
                        except Exception as exc:
                            LOGGER.warning(
                                "Erro ao restaurar view de aprovação %s: %s",
                                request.id, exc
                            )
                    except Exception as exc:
                        LOGGER.warning("Erro ao processar pedido de aprovação: %s", exc)
            except Exception as exc:
                LOGGER.warning("Erro ao restaurar views de aprovação em %s: %s", guild.id, exc)
    except Exception as exc:
        LOGGER.error("Erro ao restaurar views de aprovação: %s", exc, exc_info=True)

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
                from actions.ticket_command import TicketControlView
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