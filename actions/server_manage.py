import logging
import discord
from discord.ext import commands

LOGGER = logging.getLogger(__name__)

class ServerManageView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guilds):
        super().__init__(timeout=60)
        self.bot = bot
        # Criamos um select menu se houver muitos servidores, 
        # ou apenas botões se forem poucos. Aqui usaremos botões para facilitar.
        for guild in guilds[:25]:  # Limite de 25 botões por linha/view do Discord
            button = discord.ui.Button(
                label=f"Sair de: {guild.name[:20]}",
                style=discord.ButtonStyle.danger,
                custom_id=f"leave_{guild.id}"
            )
            button.callback = self.create_callback(guild)
            self.add_item(button)

    def create_callback(self, guild):
        async def callback(interaction: discord.Interaction):
            # Verificação extra de segurança: apenas o dono do bot ou admin
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("Você não tem permissão.", ephemeral=True)
                return

            try:
                guild_name = guild.name
                await guild.leave()
                await interaction.response.edit_message(
                    content=f"✅ Saí com sucesso do servidor: **{guild_name}**",
                    view=None
                )
            except Exception as e:
                await interaction.response.send_message(f"Erro ao sair: {e}", ephemeral=True)
        return callback

class ServerManageCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="servidores")
    @commands.has_permissions(administrator=True)
    async def list_servers(self, ctx: commands.Context):
        """Lista os servidores onde o bot está presente e permite sair deles."""
        guilds = list(self.bot.guilds)
        
        if not guilds:
            await ctx.reply("O bot não está em nenhum servidor.")
            return

        description = "\n".join([f"• **{g.name}** (ID: `{g.id}`)" for g in guilds])
        
        embed = discord.Embed(
            title="🌐 Servidores Conectados",
            description=description,
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Total: {len(guilds)} servidores")

        view = ServerManageView(self.bot, guilds)
        await ctx.reply(embed=embed, view=view)

async def setup(bot):
    """Função de setup para carregamento da extensão."""
    await bot.add_cog(ServerManageCog(bot))