import logging

import discord
from discord.ext import commands

LOGGER = logging.getLogger(__name__)


class HelpCog(commands.Cog):
    """Cog para comandos de ajuda e informações do bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
    
    def _parse_command_doc(self, docstring: str) -> dict:
        """Extrai descrição, uso e exemplos de uma docstring.
        
        Args:
            docstring: String com a docstring do comando
            
        Returns:
            Dict com keys: "description", "usage", "examples"
        """
        if not docstring:
            return {"description": "Sem descrição disponível", "usage": None, "examples": None}
        
        lines = docstring.strip().split("\n")
        description = lines[0].strip() if lines else "Sem descrição disponível"
        
        usage = None
        examples = []
        in_usage_section = False
        in_examples_section = False
        
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            
            # Detecta seção "Uso:" ou "Sintaxe:"
            if line.lower().startswith("uso:") or line.lower().startswith("sintaxe:"):
                in_usage_section = True
                in_examples_section = False
                # Extrai o uso da mesma linha ou próxima
                usage_text = line.split(":", 1)[1].strip() if ":" in line else ""
                if usage_text:
                    usage = usage_text
                continue
            
            # Detecta seção "Exemplos:"
            if line.lower().startswith("exemplos:"):
                in_examples_section = True
                in_usage_section = False
                continue
            
            # Se está na seção de uso, continua coletando
            if in_usage_section and not usage:
                usage = line
                continue
            
            # Se está na seção de exemplos, coleta exemplos
            if in_examples_section:
                # Remove marcadores de lista (-, *, etc)
                example = line.lstrip("- *•").strip()
                if example:
                    examples.append(example)
        
        return {
            "description": description,
            "usage": usage,
            "examples": examples if examples else None
        }

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
            "FichaCog": "📋 Fichas",
            "AnalyticsCog": "📊 Analytics",
            "NavalCog": "⚓ Batalha Naval",
            "VoiceCommandsCog": "🎤 Voz",
            "VoiceConfigCog": "⚙️ Configuração de Voz",
            "TicketCog": "🎫 Tickets",
            "ActionCog": "🎯 Ações",
            "ActionConfigCog": "⚙️ Configuração de Ações",
            "InviteCog": "🔗 Convites",
        }

        # Adiciona comandos agrupados por cog
        for cog_name in sorted(commands_by_cog.keys()):
            cmd_list = commands_by_cog[cog_name]
            field_value = ""
            
            for cmd in sorted(cmd_list, key=lambda c: c.name):
                prefix = ctx.prefix or "!"
                name = f"`{prefix}{cmd.name}`"
                
                # Obtém a docstring completa
                full_doc = cmd.help or cmd.description or ""
                if not full_doc and cmd.callback.__doc__:
                    full_doc = cmd.callback.__doc__
                
                # Parse da docstring
                parsed = self._parse_command_doc(full_doc)
                
                # Monta a linha do comando
                cmd_line = f"{name} - {parsed['description']}\n"
                
                # Adiciona uso se disponível
                if parsed['usage']:
                    cmd_line += f"   📝 Uso: {parsed['usage']}\n"
                
                # Adiciona exemplo se disponível (apenas o primeiro)
                if parsed['examples']:
                    first_example = parsed['examples'][0]
                    cmd_line += f"   💡 Exemplo: {first_example}\n"
                
                field_value += cmd_line
            
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
                
                # Obtém a docstring completa
                full_doc = cmd.help or cmd.description or ""
                if not full_doc and cmd.callback.__doc__:
                    full_doc = cmd.callback.__doc__
                
                # Parse da docstring
                parsed = self._parse_command_doc(full_doc)
                
                # Monta a linha do comando
                cmd_line = f"{name} - {parsed['description']}\n"
                
                # Adiciona uso se disponível
                if parsed['usage']:
                    cmd_line += f"   📝 Uso: {parsed['usage']}\n"
                
                # Adiciona exemplo se disponível (apenas o primeiro)
                if parsed['examples']:
                    first_example = parsed['examples'][0]
                    cmd_line += f"   💡 Exemplo: {first_example}\n"
                
                field_value += cmd_line
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
