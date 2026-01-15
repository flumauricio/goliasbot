"""
Streams Config View - Interface de configuração do sistema de notificações de live.

Features:
- Toggle ativar/desativar
- ChannelSelect para canal de anúncios
- RoleSelect para cargo de ping
- Botão para gerenciar streamers
- NOVO: Botão "👁️ Testar Visualização" (gera embed efêmero de exemplo)
- BackButton para voltar ao dashboard
"""

import discord
import logging
from datetime import datetime

from db import Database
from ..ui_commons import BackButton, build_standard_config_embed
from utils.config_cache import ConfigCacheManager
from .models import StreamInfo, Platform
from .embed_manager import StreamEmbedManager

LOGGER = logging.getLogger(__name__)


class StreamsConfigView(discord.ui.View):
    """View para configurar o sistema de notificações de live."""
    
    def __init__(
        self, 
        bot, 
        db: Database, 
        guild: discord.Guild, 
        parent_view=None
    ):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild = guild
        self.parent_view = parent_view
        self.config_cache = ConfigCacheManager()
        
        # Adiciona botão voltar se parent_view existir
        if self.parent_view:
            self.add_item(BackButton(self.parent_view))
    
    async def build_embed(self) -> discord.Embed:
        """Constrói a embed com as configurações atuais."""
        config = await self.db.get_stream_config(self.guild.id)
        
        # Status
        enabled = config.get('enabled', 0)
        status_text = "✅ Ativo" if enabled else "❌ Desativado"
        
        # Canal de anúncios
        announcement_channel_id = config.get('announcement_channel_id')
        if announcement_channel_id:
            channel = self.guild.get_channel(int(announcement_channel_id))
            channel_text = f"{channel.mention}" if channel else "`Canal não encontrado`"
        else:
            channel_text = "Não configurado"
        
        # Cargo para ping
        ping_role_id = config.get('ping_role_id')
        if ping_role_id:
            role = self.guild.get_role(int(ping_role_id))
            role_text = f"{role.mention}" if role else "`Cargo não encontrado`"
        else:
            role_text = "@everyone"
        
        # Configurações
        edit_on_end = config.get('edit_on_end', 1)
        cooldown_minutes = config.get('cooldown_minutes', 10)
        
        # Conta canais monitorados
        stream_channels = await self.db.get_stream_channels(self.guild.id)
        active_channels = [c for c in stream_channels if c.get('is_active')]
        
        current_config = {
            "Status": status_text,
            "Canal de Anúncios": channel_text,
            "Cargo para Notificar": role_text,
            "Canais Monitorados": f"{len(active_channels)} ativos",
            "Editar ao Encerrar": "Sim" if edit_on_end else "Não",
            "Cooldown": f"{cooldown_minutes} minutos"
        }
        
        embed = await build_standard_config_embed(
            title="📺 Configuração de Notificações de Live",
            description=(
                "Configure o sistema de anúncios de lives do Twitch/YouTube.\n\n"
                "**Recursos:**\n"
                "• Anúncios automáticos quando streamer entra ao vivo\n"
                "• Atualização em tempo real de espectadores\n"
                "• Embed editável ao encerrar live\n"
                "• Suporte para Twitch e YouTube"
            ),
            current_config=current_config,
            guild=self.guild,
            footer_text="Use os botões abaixo para configurar"
        )
        
        return embed
    
    @discord.ui.button(
        label="⚡ Ativar/Desativar",
        style=discord.ButtonStyle.primary,
        row=0
    )
    async def toggle_enabled(
        self, 
        interaction: discord.Interaction, 
        button: discord.ui.Button
    ):
        """Toggle do sistema de streams."""
        await interaction.response.defer(ephemeral=True)
        
        config = await self.db.get_stream_config(self.guild.id)
        current_enabled = config.get('enabled', 0)
        new_enabled = 1 if not current_enabled else 0
        
        await self.db.set_stream_config(self.guild.id, enabled=new_enabled)
        
        # Invalida cache
        await self.config_cache.invalidate('streams', self.guild.id)
        
        status = "ativado" if new_enabled else "desativado"
        await interaction.followup.send(
            f"✅ Sistema de Notificações de Live **{status}** com sucesso!",
            ephemeral=True
        )
        
        # Atualiza embed
        embed = await self.build_embed()
        await interaction.message.edit(embed=embed, view=self)
    
    @discord.ui.select(
        placeholder="Selecione o canal para anúncios...",
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        min_values=0,
        max_values=1,
        row=1
    )
    async def select_announcement_channel(
        self,
        interaction: discord.Interaction,
        select: discord.ui.ChannelSelect
    ):
        """Seleciona canal de anúncios."""
        await interaction.response.defer(ephemeral=True)
        
        if not select.values:
            await interaction.followup.send("❌ Nenhum canal selecionado.", ephemeral=True)
            return
        
        channel = select.values[0]
        
        await self.db.set_stream_config(
            self.guild.id,
            announcement_channel_id=channel.id
        )
        
        # Invalida cache
        await self.config_cache.invalidate('streams', self.guild.id)
        
        await interaction.followup.send(
            f"✅ Canal de anúncios definido para {channel.mention}",
            ephemeral=True
        )
        
        # Atualiza embed
        embed = await self.build_embed()
        await interaction.message.edit(embed=embed, view=self)
    
    @discord.ui.select(
        placeholder="Selecione o cargo para notificar...",
        cls=discord.ui.RoleSelect,
        min_values=0,
        max_values=1,
        row=2
    )
    async def select_ping_role(
        self,
        interaction: discord.Interaction,
        select: discord.ui.RoleSelect
    ):
        """Seleciona cargo para ping."""
        await interaction.response.defer(ephemeral=True)
        
        if not select.values:
            # Remove ping role (usa @everyone)
            await self.db.set_stream_config(
                self.guild.id,
                ping_role_id=None
            )
            await self.config_cache.invalidate('streams', self.guild.id)
            await interaction.followup.send(
                "✅ Cargo de notificação removido. Usará @everyone",
                ephemeral=True
            )
        else:
            role = select.values[0]
            
            await self.db.set_stream_config(
                self.guild.id,
                ping_role_id=role.id
            )
            await self.config_cache.invalidate('streams', self.guild.id)
            await interaction.followup.send(
                f"✅ Cargo de notificação definido para {role.mention}",
                ephemeral=True
            )
        
        # Atualiza embed
        embed = await self.build_embed()
        await interaction.message.edit(embed=embed, view=self)
    
    @discord.ui.button(
        label="📋 Gerenciar Streamers",
        style=discord.ButtonStyle.secondary,
        row=3
    )
    async def manage_streamers(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        """Abre modal para gerenciar streamers."""
        modal = AddStreamerModal(self.db, self.guild, self)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="👁️ Testar Visualização",
        style=discord.ButtonStyle.secondary,
        row=3
    )
    async def preview_embed(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        """Gera embed de exemplo (efêmero) para preview."""
        # Dados de exemplo
        sample_stream = StreamInfo(
            platform=Platform.TWITCH,
            channel_name="ExemploStreamer",
            title="Testando o Bot - Live de Exemplo 🎮",
            thumbnail_url="https://static-cdn.jtvnw.net/ttv-boxart/21779-285x380.jpg",
            viewer_count=1234,
            started_at=datetime.utcnow(),
            stream_url="https://twitch.tv/exemplo"
        )
        
        embed_manager = StreamEmbedManager()
        config = await self.db.get_stream_config(self.guild.id)
        
        ping_role_id = config.get('ping_role_id')
        ping_text = f"<@&{ping_role_id}>" if ping_role_id else "@everyone"
        
        embed = embed_manager.create_live_embed(sample_stream, ping_text)
        
        await interaction.response.send_message(
            "📺 **Preview do Anúncio de Live:**\n\n"
            "Este é um exemplo de como ficará o anúncio quando um streamer entrar ao vivo.",
            embed=embed,
            ephemeral=True
        )


class AddStreamerModal(discord.ui.Modal):
    """Modal para adicionar streamer à lista de monitoramento."""
    
    def __init__(
        self,
        db: Database,
        guild: discord.Guild,
        parent_view: StreamsConfigView
    ):
        super().__init__(title="Adicionar Streamer")
        self.db = db
        self.guild = guild
        self.parent_view = parent_view
        self.config_cache = ConfigCacheManager()
        
        # Campo de plataforma
        self.add_item(
            discord.ui.TextInput(
                label="Plataforma (twitch ou youtube)",
                placeholder="twitch",
                min_length=5,
                max_length=10
            )
        )
        
        # Campo de nome do canal
        self.add_item(
            discord.ui.TextInput(
                label="Nome do Canal/Usuário",
                placeholder="exemplo_streamer",
                min_length=1,
                max_length=100
            )
        )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Salva streamer na lista de monitoramento."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            platform_input = self.children[0].value.lower().strip()
            channel_name = self.children[1].value.strip()
            
            # Valida plataforma
            if platform_input not in ('twitch', 'youtube'):
                raise ValueError("Plataforma deve ser 'twitch' ou 'youtube'")
            
            # Adiciona ao banco
            stream_id = await self.db.add_stream_channel(
                self.guild.id,
                platform_input,
                channel_name
            )
            
            await interaction.followup.send(
                f"✅ Streamer **{channel_name}** ({platform_input}) adicionado com sucesso!",
                ephemeral=True
            )
            
            # Atualiza embed
            embed = await self.parent_view.build_embed()
            await interaction.message.edit(embed=embed, view=self.parent_view)
        except ValueError as e:
            await interaction.followup.send(
                f"❌ Erro de validação: {str(e)}",
                ephemeral=True
            )
        except Exception as e:
            LOGGER.error(f"Erro ao adicionar streamer: {e}")
            await interaction.followup.send(
                "❌ Erro ao adicionar streamer. Verifique os logs.",
                ephemeral=True
            )
