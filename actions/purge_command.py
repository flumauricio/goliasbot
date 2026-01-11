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
        
        # Verifica se o bot tem permissão para gerenciar mensagens
        if not channel.permissions_for(ctx.guild.me).manage_messages:  # type: ignore[union-attr]
            await ctx.reply("❌ Eu não tenho permissão para gerenciar mensagens neste canal.", delete_after=10)
            return
        
        await ctx.reply("Limpando este canal...", delete_after=3)
        deleted_total = 0
        try:
            while True:
                deleted = await channel.purge(limit=100, bulk=True)
                deleted_total += len(deleted)
                if len(deleted) < 100:
                    break
        except discord.Forbidden:
            await ctx.reply("❌ Permissões insuficientes para excluir mensagens. Verifique se eu tenho permissão para gerenciar mensagens.", delete_after=10)
            return
        except discord.HTTPException as exc:
            LOGGER.warning("Falha ao purgar canal %s: %s", channel.id, exc)
            await ctx.reply(f"❌ Falha ao purgar canal: {str(exc)}. Tente novamente.", delete_after=10)
            return
        except Exception as exc:
            LOGGER.error("Erro inesperado ao purgar canal %s: %s", channel.id, exc)
            await ctx.reply("❌ Erro inesperado ao limpar o canal. Verifique os logs para mais detalhes.", delete_after=10)
            return
        
        await channel.send(f"✅ Canal limpo. Mensagens removidas: {deleted_total}", delete_after=8)

