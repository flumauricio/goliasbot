import logging

import discord
from discord.ext import commands

from permissions import command_guard


LOGGER = logging.getLogger(__name__)


class PurgeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="purge")
    @commands.has_permissions(manage_messages=True)
    @command_guard("purge")
    async def purge_channel(self, ctx: commands.Context):
        """Limpa todas as mensagens do canal onde for executado."""
        channel: discord.TextChannel = ctx.channel  # type: ignore[assignment]
        await ctx.reply("Limpando este canal...", delete_after=3)
        deleted_total = 0
        try:
            while True:
                deleted = await channel.purge(limit=100, bulk=True)
                deleted_total += len(deleted)
                if len(deleted) < 100:
                    break
        except discord.Forbidden:
            await ctx.reply("Permissões insuficientes para excluir mensagens.", delete_after=5)
            return
        except discord.HTTPException as exc:
            LOGGER.warning("Falha ao purgar canal %s: %s", channel.id, exc)
            await ctx.reply("Falha ao purgar. Tente novamente.", delete_after=5)
            return
        await channel.send(f"Canal limpo. Mensagens removidas: {deleted_total}", delete_after=8)

