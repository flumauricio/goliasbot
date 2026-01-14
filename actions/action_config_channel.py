import logging

import discord
from discord.ext import commands

from db import Database
from .ui_commons import CreateChannelModal as BaseCreateChannelModal

LOGGER = logging.getLogger(__name__)


class CreateChannelModal(BaseCreateChannelModal):
    """Modal para criar um novo canal de ações (wrapper para compatibilidade)."""
    
    def __init__(self, db: Database, guild_id: int, setup_view, guild: discord.Guild):
        async def on_success(interaction: discord.Interaction, channel: discord.TextChannel):
            await db.upsert_action_settings(guild_id, action_channel_id=channel.id)
            await setup_view.update_embed()
        
        super().__init__(
            guild=guild,
            title="Criar Novo Canal de Ações",
            channel_name_label="Nome do Canal",
            channel_type=discord.ChannelType.text,
            on_success=on_success
        )


class ChannelSelectView(discord.ui.View):
    """View para selecionar ou criar canal de ações."""
    
    def __init__(self, db: Database, guild_id: int, setup_view, guild: discord.Guild):
        super().__init__(timeout=60)
        self.db = db
        self.guild_id = guild_id
        self.setup_view = setup_view
        self.guild = guild
    
    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Selecione um canal existente...",
        channel_types=[discord.ChannelType.text],
        min_values=0,
        max_values=1,
        row=0
    )
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        """Seleciona o canal de ações."""
        if select.values:
            channel = select.values[0]
            await self.db.upsert_action_settings(self.guild_id, action_channel_id=channel.id)
            await interaction.response.send_message(
                f"✅ Canal de ações configurado: {channel.mention}",
                ephemeral=True
            )
            await self.setup_view.update_embed()
        else:
            # Remove canal
            await self.db.upsert_action_settings(self.guild_id, action_channel_id=None)
            await interaction.response.send_message(
                "✅ Canal de ações removido.",
                ephemeral=True
            )
            await self.setup_view.update_embed()
    
    @discord.ui.button(
        label="➕ Criar Novo Canal",
        style=discord.ButtonStyle.success,
        row=1,
        emoji="➕"
    )
    async def create_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre modal para criar novo canal."""
        modal = CreateChannelModal(self.db, self.guild_id, self.setup_view, self.guild)
        await interaction.response.send_modal(modal)


class CreateRankingChannelModal(discord.ui.Modal, title="Criar Novo Canal de Ranking"):
    """Modal para criar um novo canal de ranking."""
    
    def __init__(self, db: Database, guild_id: int, setup_view, guild: discord.Guild):
        super().__init__()
        self.db = db
        self.guild_id = guild_id
        self.setup_view = setup_view
        self.guild = guild
    
    channel_name_input = discord.ui.TextInput(
        label="Nome do Canal",
        placeholder="Ex: ranking-ações",
        required=True,
        max_length=100
    )
    
    category_name_input = discord.ui.TextInput(
        label="Nome da Categoria (opcional)",
        placeholder="Deixe vazio para usar categoria existente",
        required=False,
        max_length=100
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        """Cria o canal e configura."""
        try:
            channel_name = self.channel_name_input.value.strip()
            if not channel_name:
                await interaction.response.send_message(
                    "❌ O nome do canal não pode estar vazio.",
                    ephemeral=True
                )
                return
            
            category = None
            category_name = self.category_name_input.value.strip()
            
            # Se forneceu nome de categoria, tenta criar ou buscar
            if category_name:
                # Tenta buscar categoria existente
                existing_category = None
                for cat in self.guild.categories:
                    if cat.name == category_name:
                        existing_category = cat
                        break
                if existing_category:
                    category = existing_category
                else:
                    # Cria nova categoria
                    try:
                        category = await self.guild.create_category(
                            category_name,
                            reason=f"Categoria criada via !acao_setup por {interaction.user}"
                        )
                    except discord.Forbidden:
                        await interaction.response.send_message(
                            "❌ Não tenho permissão para criar categorias. Verifique as permissões do bot.",
                            ephemeral=True
                        )
                        return
            
            try:
                channel = await self.guild.create_text_channel(
                    name=channel_name,
                    category=category,
                    reason=f"Canal de ranking criado via !acao_setup por {interaction.user}"
                )
                
                await self.db.upsert_action_settings(self.guild_id, ranking_channel_id=channel.id)
                
                await interaction.response.send_message(
                    f"✅ Canal de ranking **{channel.name}** criado e configurado! {channel.mention}",
                    ephemeral=True
                )
                
                await self.setup_view.update_embed()
                
            except discord.Forbidden:
                await interaction.response.send_message(
                    "❌ Não tenho permissão para criar canais. Verifique as permissões do bot.",
                    ephemeral=True
                )
            except Exception as exc:
                LOGGER.error("Erro ao criar canal de ranking: %s", exc, exc_info=True)
                await interaction.response.send_message(
                    "❌ Erro ao criar canal. Tente novamente.",
                    ephemeral=True
                )
                
        except Exception as exc:
            LOGGER.error("Erro no modal de criar canal de ranking: %s", exc, exc_info=True)
            await interaction.response.send_message(
                "❌ Erro ao processar. Tente novamente.",
                ephemeral=True
            )


class RankingChannelSelectView(discord.ui.View):
    """View para selecionar ou criar canal de ranking."""
    
    def __init__(self, db: Database, guild_id: int, setup_view, guild: discord.Guild):
        super().__init__(timeout=60)
        self.db = db
        self.guild_id = guild_id
        self.setup_view = setup_view
        self.guild = guild
    
    @discord.ui.select(
        cls=discord.ui.ChannelSelect,
        placeholder="Selecione um canal existente...",
        channel_types=[discord.ChannelType.text],
        min_values=0,
        max_values=1,
        row=0
    )
    async def select_channel(self, interaction: discord.Interaction, select: discord.ui.ChannelSelect):
        """Seleciona o canal de ranking."""
        if select.values:
            channel = select.values[0]
            await self.db.upsert_action_settings(self.guild_id, ranking_channel_id=channel.id)
            await interaction.response.send_message(
                f"✅ Canal de ranking configurado: {channel.mention}",
                ephemeral=True
            )
            await self.setup_view.update_embed()
        else:
            # Remove canal
            await self.db.upsert_action_settings(self.guild_id, ranking_channel_id=None)
            await interaction.response.send_message(
                "✅ Canal de ranking removido.",
                ephemeral=True
            )
            await self.setup_view.update_embed()
    
    @discord.ui.button(
        label="➕ Criar Novo Canal",
        style=discord.ButtonStyle.success,
        row=1,
        emoji="➕"
    )
    async def create_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Abre modal para criar novo canal."""
        modal = CreateRankingChannelModal(self.db, self.guild_id, self.setup_view, self.guild)
        await interaction.response.send_modal(modal)
