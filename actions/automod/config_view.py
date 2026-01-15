"""
Automod Config View - Interface de configuração do sistema automod no !setup.

Features:
- Toggle ativar/desabilitar
- Select de sensibilidade (threshold)
- Select de canal de logs
- Botão para gerenciar whitelist
- BackButton para voltar ao dashboard
"""

import discord
import logging
from typing import Optional

from db import Database
from ..ui_commons import BackButton, build_standard_config_embed
from utils.config_cache import ConfigCacheManager

LOGGER = logging.getLogger(__name__)


class AutomodConfigView(discord.ui.View):
    """View para configurar o sistema de Automod."""
    
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
        config = await self.db.get_automod_config(self.guild.id)
        
        # Status
        enabled = config.get('enabled', 0)
        status_text = "✅ Ativo" if enabled else "❌ Desativado"
        
        # Canal de logs
        logs_channel_id = config.get('logs_channel_id')
        if logs_channel_id:
            channel = self.guild.get_channel(int(logs_channel_id))
            logs_text = f"{channel.mention}" if channel else "`Canal não encontrado`"
        else:
            logs_text = "Não configurado"
        
        # Configurações de detecção
        spam_threshold = config.get('spam_threshold', 5)
        spam_window = config.get('spam_window_seconds', 10)
        similarity = config.get('similarity_threshold', 0.85)
        mention_limit = config.get('mention_limit', 5)
        
        # Configurações de punição
        first_action = config.get('first_action', 'warn')
        second_action = config.get('second_action', 'timeout')
        third_action = config.get('third_action', 'ban')
        timeout_duration = config.get('timeout_duration', 600)
        
        current_config = {
            "Status": status_text,
            "Canal de Logs": logs_text,
            "Detecção de Spam": f"{spam_threshold} mensagens em {spam_window}s",
            "Similaridade": f"{similarity:.0%}",
            "Limite de Menções": f"{mention_limit}",
            "Punições": f"1ª {first_action} → 2ª {second_action} → 3ª {third_action}",
            "Duração Timeout": f"{timeout_duration // 60} minutos"
        }
        
        embed = await build_standard_config_embed(
            title="🤖 Configuração do Sistema Automod",
            description=(
                "Configure o sistema de anti-raid e moderação automática.\n\n"
                "**Recursos:**\n"
                "• Detecção de spam (mensagens idênticas)\n"
                "• Detecção de similaridade (bypass de spam)\n"
                "• Proteção contra flood de menções\n"
                "• Filtro de convites do Discord\n"
                "• Punições graduadas automáticas"
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
        """Toggle do sistema automod."""
        await interaction.response.defer(ephemeral=True)
        
        config = await self.db.get_automod_config(self.guild.id)
        current_enabled = config.get('enabled', 0)
        new_enabled = 1 if not current_enabled else 0
        
        await self.db.set_automod_config(self.guild.id, enabled=new_enabled)
        
        # Invalida cache
        await self.config_cache.invalidate('automod', self.guild.id)
        
        status = "ativado" if new_enabled else "desativado"
        await interaction.followup.send(
            f"✅ Sistema Automod **{status}** com sucesso!",
            ephemeral=True
        )
        
        # Atualiza embed
        embed = await self.build_embed()
        await interaction.message.edit(embed=embed, view=self)
    
    @discord.ui.select(
        placeholder="Selecione o canal de logs...",
        cls=discord.ui.ChannelSelect,
        channel_types=[discord.ChannelType.text],
        min_values=0,
        max_values=1,
        row=1
    )
    async def select_logs_channel(
        self,
        interaction: discord.Interaction,
        select: discord.ui.ChannelSelect
    ):
        """Seleciona canal de logs."""
        await interaction.response.defer(ephemeral=True)
        
        if not select.values:
            await interaction.followup.send("❌ Nenhum canal selecionado.", ephemeral=True)
            return
        
        channel = select.values[0]
        
        await self.db.set_automod_config(
            self.guild.id,
            logs_channel_id=channel.id
        )
        
        # Invalida cache
        await self.config_cache.invalidate('automod', self.guild.id)
        
        await interaction.followup.send(
            f"✅ Canal de logs definido para {channel.mention}",
            ephemeral=True
        )
        
        # Atualiza embed
        embed = await self.build_embed()
        await interaction.message.edit(embed=embed, view=self)
    
    @discord.ui.button(
        label="⚙️ Configurações Avançadas",
        style=discord.ButtonStyle.secondary,
        row=2
    )
    async def open_advanced_settings(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        """Abre modal de configurações avançadas."""
        config = await self.db.get_automod_config(self.guild.id)
        
        modal = AdvancedSettingsModal(
            self.db,
            self.guild,
            config,
            self
        )
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(
        label="🛡️ Gerenciar Whitelist",
        style=discord.ButtonStyle.secondary,
        row=2
    )
    async def manage_whitelist(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        """Abre interface de gerenciamento da whitelist."""
        await interaction.response.send_message(
            "🛡️ **Gerenciamento de Whitelist**\n\n"
            "Use os comandos abaixo para gerenciar a whitelist:\n"
            "• `/automod whitelist add role <cargo>` - Adiciona cargo à whitelist\n"
            "• `/automod whitelist add channel <canal>` - Adiciona canal à whitelist\n"
            "• `/automod whitelist remove role <cargo>` - Remove cargo\n"
            "• `/automod whitelist remove channel <canal>` - Remove canal\n"
            "• `/automod whitelist list` - Lista itens na whitelist\n\n"
            "**Nota:** Administradores sempre ignoram o automod.",
            ephemeral=True
        )


class AdvancedSettingsModal(discord.ui.Modal):
    """Modal para configurações avançadas do automod."""
    
    def __init__(
        self,
        db: Database,
        guild: discord.Guild,
        config: dict,
        parent_view: AutomodConfigView
    ):
        super().__init__(title="Configurações Avançadas - Automod")
        self.db = db
        self.guild = guild
        self.parent_view = parent_view
        self.config_cache = ConfigCacheManager()
        
        # Campos do modal
        self.add_item(
            discord.ui.TextInput(
                label="Threshold de Spam (mensagens)",
                placeholder="5",
                default=str(config.get('spam_threshold', 5)),
                min_length=1,
                max_length=2
            )
        )
        
        self.add_item(
            discord.ui.TextInput(
                label="Janela de Tempo (segundos)",
                placeholder="10",
                default=str(config.get('spam_window_seconds', 10)),
                min_length=1,
                max_length=3
            )
        )
        
        self.add_item(
            discord.ui.TextInput(
                label="Limite de Menções",
                placeholder="5",
                default=str(config.get('mention_limit', 5)),
                min_length=1,
                max_length=2
            )
        )
        
        self.add_item(
            discord.ui.TextInput(
                label="Duração do Timeout (minutos)",
                placeholder="10",
                default=str(config.get('timeout_duration', 600) // 60),
                min_length=1,
                max_length=4
            )
        )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Salva configurações avançadas."""
        await interaction.response.defer(ephemeral=True)
        
        try:
            spam_threshold = int(self.children[0].value)
            spam_window = int(self.children[1].value)
            mention_limit = int(self.children[2].value)
            timeout_minutes = int(self.children[3].value)
            
            # Validações
            if spam_threshold < 1 or spam_threshold > 20:
                raise ValueError("Threshold de spam deve estar entre 1 e 20")
            if spam_window < 1 or spam_window > 300:
                raise ValueError("Janela de tempo deve estar entre 1 e 300 segundos")
            if mention_limit < 1 or mention_limit > 50:
                raise ValueError("Limite de menções deve estar entre 1 e 50")
            if timeout_minutes < 1 or timeout_minutes > 1440:
                raise ValueError("Duração do timeout deve estar entre 1 e 1440 minutos")
            
            await self.db.set_automod_config(
                self.guild.id,
                spam_threshold=spam_threshold,
                spam_window_seconds=spam_window,
                mention_limit=mention_limit,
                timeout_duration=timeout_minutes * 60
            )
            
            # Invalida cache
            await self.config_cache.invalidate('automod', self.guild.id)
            
            await interaction.followup.send(
                "✅ Configurações avançadas salvas com sucesso!",
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
            LOGGER.error(f"Erro ao salvar configurações avançadas: {e}")
            await interaction.followup.send(
                "❌ Erro ao salvar configurações. Verifique os logs.",
                ephemeral=True
            )
