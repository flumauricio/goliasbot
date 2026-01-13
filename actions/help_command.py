import logging

import discord
from discord.ext import commands

LOGGER = logging.getLogger(__name__)


class HelpCog(commands.Cog):
    """Cog para comandos de ajuda e informações do bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="comandos")
    async def list_commands(self, ctx: commands.Context):
        """Lista todos os comandos disponíveis do bot com suas descrições."""
        # Obtém todos os comandos registrados no bot (exceto comandos ocultos)
        all_commands = sorted(
            [cmd for cmd in self.bot.commands if not cmd.hidden],
            key=lambda c: c.name
        )

        if not all_commands:
            await ctx.reply("Nenhum comando encontrado.")
            return

        # Cria embed principal
        embed = discord.Embed(
            title="🤖 Comandos do Bot",
            description="Lista completa de comandos disponíveis e suas funções",
            color=discord.Color.blue()
        )

        # Organiza comandos por categoria (cog) para melhor organização
        commands_by_cog = {}
        uncategorized = []

        for cmd in all_commands:
            if cmd.cog:
                cog_name = cmd.cog.__class__.__name__
                if cog_name not in commands_by_cog:
                    commands_by_cog[cog_name] = []
                commands_by_cog[cog_name].append(cmd)
            else:
                uncategorized.append(cmd)

        # Mapeamento de nomes de cogs para nomes mais amigáveis
        cog_friendly_names = {
            "SetupCog": "⚙️ Configuração",
            "SetCog": "📝 Cadastro",
            "PurgeCog": "🧹 Moderação",
            "WarnCog": "⚠️ Advertências",
            "RegistrationCog": "📋 Registros",
            "ServerManageCog": "🌐 Servidores",
            "HelpCog": "❓ Ajuda",
        }

        # Adiciona comandos agrupados por cog
        for cog_name in sorted(commands_by_cog.keys()):
            cmd_list = commands_by_cog[cog_name]
            field_value = ""
            
            for cmd in sorted(cmd_list, key=lambda c: c.name):
                prefix = ctx.prefix or "!"
                name = f"`{prefix}{cmd.name}`"
                
                # Obtém a descrição do comando (docstring ou description)
                doc = cmd.short_doc or cmd.description or cmd.help or "Sem descrição disponível"
                
                # Se a docstring tiver múltiplas linhas, pega apenas a primeira
                if "\n" in doc:
                    doc = doc.split("\n")[0].strip()
                
                field_value += f"{name} - {doc}\n"
            
            if field_value:
                # Usa nome amigável se disponível, senão remove "Cog" do nome
                friendly_name = cog_friendly_names.get(cog_name, cog_name.replace("Cog", "").strip())
                embed.add_field(
                    name=friendly_name,
                    value=field_value.strip(),
                    inline=False
                )
        
        # Comandos sem cog (se houver)
        if uncategorized:
            field_value = ""
            for cmd in sorted(uncategorized, key=lambda c: c.name):
                prefix = ctx.prefix or "!"
                name = f"`{prefix}{cmd.name}`"
                doc = cmd.short_doc or cmd.description or cmd.help or "Sem descrição disponível"
                if "\n" in doc:
                    doc = doc.split("\n")[0].strip()
                field_value += f"{name} - {doc}\n"
            embed.add_field(
                name="Outros",
                value=field_value.strip(),
                inline=False
            )

        embed.set_footer(text=f"Total: {len(all_commands)} comandos disponíveis")
        
        await ctx.reply(embed=embed)


async def setup(bot):
    """Função de setup para carregamento da extensão."""
    await bot.add_cog(HelpCog(bot))
