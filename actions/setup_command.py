import asyncio
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

# Usa o set global do bot para prevenir execução duplicada


class BackButton(discord.ui.Button):
    """Botão para voltar ao dashboard principal."""
    
    def __init__(self, parent_view):
        super().__init__(label="⬅️ Voltar", style=discord.ButtonStyle.secondary, row=4)
        self.parent_view = parent_view
    
    async def callback(self, interaction: discord.Interaction):
        embed = await self.parent_view.build_embed()
        await interaction.response.edit_message(embed=embed, view=self.parent_view)


class NavalSetupView(discord.ui.View):
    """View para configurar o sistema de Batalha Naval."""
    
    def __init__(self, bot: commands.Bot, db: Database, guild: discord.Guild, parent_view=None):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild = guild
        self.parent_view = parent_view
        
        # Adiciona botão voltar se parent_view existir
        if self.parent_view:
            self.add_item(BackButton(self.parent_view))
        
        # ChannelSelect para Canal de Batalha Naval
        self.naval_channel_select = discord.ui.ChannelSelect(
            placeholder="Selecione o canal para partidas de Batalha Naval...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=0
        )
        self.naval_channel_select.callback = self.on_naval_channel_select
        self.add_item(self.naval_channel_select)
    
    async def build_embed(self) -> discord.Embed:
        """Constrói a embed com as configurações atuais."""
        settings = await self.db.get_settings(self.guild.id)
        
        embed = discord.Embed(
            title="⚓ Configuração do Sistema de Batalha Naval",
            description="Configure o canal onde as partidas de Batalha Naval serão criadas.",
            color=discord.Color.blue()
        )
        
        # Canal de Batalha Naval
        channel_naval_id = settings.get("channel_naval")
        if channel_naval_id:
            channel = self.guild.get_channel(int(channel_naval_id))
            if channel:
                channel_text = f"{channel.mention} (`{channel.id}`)"
            else:
                channel_text = f"`{channel_naval_id}` (canal não encontrado)"
        else:
            channel_text = "❌ Não configurado"
        
        embed.add_field(
            name="📢 Canal de Batalha Naval",
            value=channel_text,
            inline=False
        )
        
        embed.set_footer(text="Selecione um canal abaixo para configurar")
        
        return embed
    
    async def on_naval_channel_select(self, interaction: discord.Interaction):
        """Callback quando um canal é selecionado."""
        await interaction.response.defer(ephemeral=True)
        
        selected_channels = interaction.data.get("values", [])
        if not selected_channels:
            await interaction.followup.send("❌ Nenhum canal selecionado.", ephemeral=True)
            return
        
        channel_id = int(selected_channels[0])
        channel = self.guild.get_channel(channel_id)
        
        if not channel:
            await interaction.followup.send("❌ Canal não encontrado.", ephemeral=True)
            return
        
        # Salva a configuração
        await self.db.upsert_settings(self.guild.id, channel_naval=channel.id)
        
        # Atualiza a embed
        embed = await self.build_embed()
        await interaction.followup.send(
            f"✅ Canal de Batalha Naval configurado: {channel.mention}",
            ephemeral=True
        )
        
        # Atualiza a mensagem principal
        try:
            await interaction.message.edit(embed=embed, view=self)
        except discord.NotFound:
            pass


# Configuração modular de módulos
MODULE_CONFIGS: Dict[str, Dict[str, Any]] = {
    "tickets": {
        "name": "🎫 Tickets",
        "view_class": TicketSetupView,
        "check_configured": "tickets",
    },
    "registration": {
        "name": "📝 Geral",
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
    "naval": {
        "name": "⚓ Batalha Naval",
        "view_class": NavalSetupView,
        "check_configured": "naval",
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


async def _check_naval_configured(db: Database, guild_id: int) -> bool:
    """Verifica se o sistema de Batalha Naval está configurado."""
    settings = await db.get_settings(guild_id)
    return bool(settings.get("channel_naval"))


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
            elif check_func_name == "naval":
                is_configured = await _check_naval_configured(self.db, self.guild.id)
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
    
    @discord.ui.button(label="📝 Geral", style=discord.ButtonStyle.primary, row=0)
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
    
    @discord.ui.button(label="⚓ Naval", style=discord.ButtonStyle.primary, row=1)
    async def open_naval(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre configuração de Batalha Naval."""
        if not interaction.guild:
            await interaction.response.send_message("❌ Use este comando em um servidor.", ephemeral=True)
            return
        
        view = NavalSetupView(self.bot, self.db, interaction.guild, parent_view=self)
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
        # Verifica se já está sendo processado (prevenção de duplicação) - thread-safe
        msg_id = ctx.message.id
        with self.bot._processing_lock:
            if msg_id in self.bot._processing_messages:
                return
            
            # Marca como em processamento IMEDIATAMENTE (antes de qualquer await)
            self.bot._processing_messages.add(msg_id)
        
        try:
            LOGGER.info("[TRACE] !setup RECEBIDO - Usuario: %s, Guild: %s, Msg_ID: %s, Channel: %s", 
                        ctx.author.id, ctx.guild.id, ctx.message.id, ctx.channel.id)
        
            guild = ctx.guild
            if not guild:
                await ctx.send("❌ Use este comando em um servidor.")
                return
            
            LOGGER.info("[EXEC] !setup INICIADO - Usuario: %s (ID: %s), Guild: %s (ID: %s)", 
                        ctx.author.name, ctx.author.id, guild.name, guild.id)
            
            view = MainDashboardView(self.bot, self.db, self.config, guild)
            embed = await view.build_embed()
            
            # Deleta o comando após execução
            try:
                await ctx.message.delete()
            except discord.errors.HTTPException as e:
                LOGGER.warning("Erro HTTP ao deletar mensagem: %s", e)
            except Exception as e:
                LOGGER.warning("Erro ao deletar mensagem do comando: %s", e)
            
            # Usa ctx.send ao invés de ctx.reply para evitar erro quando mensagem foi deletada
            reply_msg = await ctx.send(embed=embed, view=view)
            
            LOGGER.info("[SUCCESS] Dashboard enviado (msg_id: %s) para %s", reply_msg.id, guild.name)
            LOGGER.info("[FINALIZED] !setup concluído para %s", ctx.author.name)
        finally:
            # Remove do set de processamento após 2 segundos
            await asyncio.sleep(2)
            with self.bot._processing_lock:
                self.bot._processing_messages.discard(msg_id)


async def setup(bot):
    """Função de setup para carregamento da extensão."""
    from config_manager import ConfigManager
    from db import Database
    
    await bot.add_cog(SetupCog(bot, bot.db, bot.config_manager))
