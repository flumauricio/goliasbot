"""
View de configuração do canal Discord Accounts para o !setup.
Arquivo: actions/discord_accounts_config.py
"""

import logging
import discord
from discord.ext import commands
from db import Database
from .ui_commons import BackButton, CreateChannelModal, build_standard_config_embed

LOGGER = logging.getLogger(__name__)


class DiscordAccountsSetupView(discord.ui.View):
    """View para configurar o canal do sistema de gerenciamento de contas Discord."""

    def __init__(self, bot: commands.Bot, db: Database, guild: discord.Guild, parent_view=None):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild = guild
        self.parent_view = parent_view

        if self.parent_view:
            self.add_item(BackButton(self.parent_view))

        self.channel_select = discord.ui.ChannelSelect(
            placeholder="Selecione o canal de gerenciamento de contas Discord...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=0,
        )
        self.channel_select.callback = self.on_channel_select
        self.add_item(self.channel_select)

        self.create_btn = discord.ui.Button(
            label="➕ Criar Novo Canal",
            style=discord.ButtonStyle.success,
            row=3,
        )
        self.create_btn.callback = self.create_channel
        self.add_item(self.create_btn)

        self.remove_btn = discord.ui.Button(
            label="🗑️ Remover Canal",
            style=discord.ButtonStyle.danger,
            row=3,
        )
        self.remove_btn.callback = self.remove_channel
        self.add_item(self.remove_btn)

    async def build_embed(self) -> discord.Embed:
        settings = await self.db.get_settings(self.guild.id)
        channel_id = settings.get("channel_discord_accounts")

        if channel_id:
            channel = self.guild.get_channel(int(channel_id))
            channel_text = f"{channel.mention} (`{channel.id}`)" if channel else f"`{channel_id}` (canal não encontrado)"
        else:
            channel_text = None

        embed = await build_standard_config_embed(
            title="🎧 Configuração do Gerenciador de Contas Discord",
            description=(
                "Configure o canal onde os usuários poderão gerenciar suas contas Discord, Email e Steam.\n\n"
                "**Como funciona:**\n"
                "• Use o comando `!discord_accounts` para abrir o painel\n"
                "• Gerencie múltiplas contas por usuário\n"
                "• Vincule contas Rockstar com contas Discord\n"
                "• Todos os dados são privados e seguros"
            ),
            current_config={"Canal Discord Accounts": channel_text},
            guild=self.guild,
            footer_text="Selecione um canal abaixo ou crie um novo",
        )
        return embed

    async def on_channel_select(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        selected = interaction.data.get("values", [])
        if not selected:
            await interaction.followup.send("❌ Nenhum canal selecionado.", ephemeral=True)
            return
        channel = self.guild.get_channel(int(selected[0]))
        if not channel:
            await interaction.followup.send("❌ Canal não encontrado.", ephemeral=True)
            return
        await self.db.upsert_settings(self.guild.id, channel_discord_accounts=channel.id)
        embed = await self.build_embed()
        try:
            await interaction.message.edit(embed=embed, view=self)
        except discord.NotFound:
            pass
        await interaction.followup.send(f"✅ Canal Discord Accounts configurado: {channel.mention}", ephemeral=True)

    async def create_channel(self, interaction: discord.Interaction):
        async def on_success(inter: discord.Interaction, channel: discord.TextChannel):
            await self.db.upsert_settings(self.guild.id, channel_discord_accounts=channel.id)
            embed = await self.build_embed()
            try:
                await inter.message.edit(embed=embed, view=self)
            except Exception:
                pass
        modal = CreateChannelModal(
            guild=self.guild,
            title="Criar Canal Discord Accounts",
            channel_name_label="Nome do Canal",
            on_success=on_success,
        )
        await interaction.response.send_modal(modal)

    async def remove_channel(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            async with self.db._conn.cursor() as cur:
                await cur.execute(
                    "UPDATE settings SET channel_discord_accounts = NULL WHERE guild_id = ?",
                    (self.guild.id,),
                )
                await self.db._conn.commit()
        except Exception as e:
            LOGGER.error("Erro ao remover canal Discord Accounts: %s", e)
            await interaction.followup.send("❌ Erro ao remover configuração.", ephemeral=True)
            return
        embed = await self.build_embed()
        try:
            await interaction.message.edit(embed=embed, view=self)
        except discord.NotFound:
            pass
        await interaction.followup.send("✅ Canal Discord Accounts removido.", ephemeral=True)
