import logging

import discord
from discord.ext import commands

LOGGER = logging.getLogger(__name__)


class InviteCog(commands.Cog):
    """Cog para comando de convite do bot."""
    
    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    @commands.command(name="convite")
    async def invite_command(self, ctx: commands.Context):
        """Gera um link de convite oficial do bot com permissões de administrador."""
        if not self.bot.user:
            await ctx.reply("❌ Bot não está pronto ainda. Tente novamente em alguns instantes.")
            return
        
        # Gera link de convite usando OAuth URL
        invite_url = discord.utils.oauth_url(
            client_id=self.bot.user.id,
            permissions=discord.Permissions(administrator=True),
            scopes=["bot", "applications.commands"]
        )
        
        # Cria embed elegante
        embed = discord.Embed(
            title="Siga o GoliasBot para outros servidores!",
            description=(
                "Clique no botão abaixo para me convidar. "
                "Lembre-se que você precisa ter permissão de Gerenciar Servidor no destino."
            ),
            color=discord.Color.blue()
        )
        
        # Cria view com botão de link
        view = discord.ui.View()
        view.add_item(
            discord.ui.Button(
                label="Convidar Bot",
                url=invite_url,
                style=discord.ButtonStyle.link,
                emoji="➕"
            )
        )
        
        await ctx.reply(embed=embed, view=view)
        
        # Deleta o comando após execução
        try:
            await ctx.message.delete()
        except:
            pass
