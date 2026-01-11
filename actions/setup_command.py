import logging
from typing import Optional, Dict, Callable, Any

import discord
from discord.ext import commands

from config_manager import ConfigManager
from db import Database
from .voice_config import VoiceSetupView
from .action_config import ActionSetupView
from .ticket_command import TicketSetupView
from .registration_config import RegistrationConfigView
from .permissions_config import PermissionsView

LOGGER = logging.getLogger(__name__)


# Configuração modular de módulos
MODULE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "tickets": {
        "name": "🎫 Tickets",
        "view_class": TicketSetupView,
        "check_configured": "tickets",
    },
    "registration": {
        "name": "📝 Cadastro",
        "view_class": RegistrationConfigView,
        "check_configured": "registration",
    },
    "actions": {
        "name": "🎭 Ações",
        "view_class": ActionSetupView,
        "check_configured": "actions",
    },
    "voice_points": {
        "name": "⏱️ Ponto",
        "view_class": VoiceSetupView,
        "check_configured": "voice_points",
    },
    "permissions": {
        "name": "⚙️ Permissões",
        "view_class": PermissionsView,
        "check_configured": "permissions",
    },
}


async def _check_tickets_configured(db: Database, guild_id: int) -> bool:
    """Verifica se o sistema de tickets está configurado."""
    settings = await db.get_ticket_settings(guild_id)
    return bool(settings.get("category_id") or settings.get("ticket_channel_id"))


async def _check_registration_configured(db: Database, guild_id: int) -> bool:
    """Verifica se o sistema de cadastro está configurado."""
    settings = await db.get_settings(guild_id)
    return bool(settings.get("channel_registration_embed") and settings.get("role_member"))


async def _check_actions_configured(db: Database, guild_id: int) -> bool:
    """Verifica se o sistema de ações está configurado."""
    action_types = await db.get_action_types(guild_id)
    return len(action_types) > 0


async def _check_voice_configured(db: Database, guild_id: int) -> bool:
    """Verifica se o sistema de pontos por voz está configurado."""
    allowed_roles = await db.get_allowed_roles(guild_id)
    monitored_channels = await db.get_monitored_channels(guild_id)
    settings = await db.get_voice_settings(guild_id)
    monitor_all = settings.get("monitor_all", 0) == 1
    return bool(allowed_roles and (monitor_all or monitored_channels))


class MainDashboardView(discord.ui.View):
    """View principal do Dashboard Central."""
    
    def __init__(self, bot: commands.Bot, db: Database, config: ConfigManager, guild: discord.Guild):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.config = config
        self.guild = guild
    
    def get_module_status_emoji(self, module_name: str, is_active: bool, is_configured: bool) -> str:
        """Retorna emoji de status do módulo."""
        if not is_active:
            return "⚪"
        return "✅" if is_configured else "❌"
    
    async def build_embed(self) -> discord.Embed:
        """Constrói a embed de resumo do dashboard."""
        embed = discord.Embed(
            title="⚙️ Dashboard Central - Configuração do Bot",
            description="Gerencie todos os módulos do bot a partir deste painel central.",
            color=discord.Color.blue()
        )
        
        # Busca status de todos os módulos
        all_modules_status = await self.db.get_all_modules_status(self.guild.id)
        
        # Constrói campos para cada módulo
        modules_text = []
        for module_name, module_config in MODULE_CONFIGS.items():
            is_active = all_modules_status.get(module_name, True)  # Padrão: ativo
            check_func_name = module_config["check_configured"]
            if check_func_name == "tickets":
                is_configured = await _check_tickets_configured(self.db, self.guild.id)
            elif check_func_name == "registration":
                is_configured = await _check_registration_configured(self.db, self.guild.id)
            elif check_func_name == "actions":
                is_configured = await _check_actions_configured(self.db, self.guild.id)
            elif check_func_name == "voice_points":
                is_configured = await _check_voice_configured(self.db, self.guild.id)
            else:  # permissions
                is_configured = True
            emoji = self.get_module_status_emoji(module_name, is_active, is_configured)
            
            status_text = "Configurado e Ativo" if (is_active and is_configured) else \
                         "Pendente de Configuração" if (is_active and not is_configured) else \
                         "Desativado"
            
            modules_text.append(f"{emoji} {module_config['name']}: {status_text}")
        
        embed.add_field(
            name="📊 Status dos Módulos",
            value="\n".join(modules_text),
            inline=False
        )
        
        embed.set_footer(text="Use os botões abaixo para navegar entre os módulos")
        
        return embed
    
    @discord.ui.button(label="🎫 Tickets", style=discord.ButtonStyle.primary, row=0)
    async def open_tickets(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre configuração de tickets."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Use este comando em um servidor.", ephemeral=True)
            return
        
        view = TicketSetupView(self.bot, self.db, interaction.guild, parent_view=self)
        await view.load_existing_settings()
        embed = await view.update_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="📝 Cadastro", style=discord.ButtonStyle.primary, row=0)
    async def open_registration(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre configuração de cadastro."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Use este comando em um servidor.", ephemeral=True)
            return
        
        view = RegistrationConfigView(self.bot, self.db, self.config, interaction.guild.id, parent_view=self)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="🎭 Ações", style=discord.ButtonStyle.primary, row=0)
    async def open_actions(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre configuração de ações."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Use este comando em um servidor.", ephemeral=True)
            return
        
        view = ActionSetupView(self.bot, self.db, interaction.guild, parent_view=self)
        await view._update_select_options()
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="⏱️ Ponto", style=discord.ButtonStyle.primary, row=1)
    async def open_voice(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre configuração de pontos por voz."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Use este comando em um servidor.", ephemeral=True)
            return
        
        view = VoiceSetupView(self.bot, self.db, interaction.guild.id, parent_view=self)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)
    
    @discord.ui.button(label="⚙️ Permissões", style=discord.ButtonStyle.primary, row=1)
    async def open_permissions(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre configuração de permissões."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Use este comando em um servidor.", ephemeral=True)
            return
        
        view = PermissionsView(self.bot, self.db, interaction.guild, parent_view=self)
        embed = await view.build_embed()
        await interaction.response.edit_message(embed=embed, view=view)


class SetupCog(commands.Cog):
    """Cog para o Dashboard Central de configuração."""
    
    def __init__(self, bot: commands.Bot, db: Database, config: ConfigManager):
        self.bot = bot
        self.db = db
        self.config = config
    
    @commands.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def interactive_setup(self, ctx: commands.Context):
        """Abre o Dashboard Central de configuração do bot."""
        guild = ctx.guild
        if not guild:
            await ctx.reply("❌ Use este comando em um servidor.")
            return
        
        view = MainDashboardView(self.bot, self.db, self.config, guild)
        embed = await view.build_embed()
        
        await ctx.reply(embed=embed, view=view)
        
        # Deleta o comando após execução
        try:
            await ctx.message.delete()
        except:
            pass
