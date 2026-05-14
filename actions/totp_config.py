"""
View de configuração do canal 2FA para o !setup.
Este arquivo deve ser colocado em: actions/totp_config.py
"""

import logging

import discord
from discord.ext import commands

from db import Database
from .ui_commons import BackButton, CreateChannelModal, build_standard_config_embed

LOGGER = logging.getLogger(__name__)


class TotpSetupView(discord.ui.View):
    """View para configurar o canal do sistema 2FA."""

    def __init__(self, bot: commands.Bot, db: Database, guild: discord.Guild, parent_view=None):
        super().__init__(timeout=300)
        self.bot = bot
        self.db = db
        self.guild = guild
        self.parent_view = parent_view

        # Botão voltar (aparece se vier de outra view)
        if self.parent_view:
            self.add_item(BackButton(self.parent_view))

        # Seletor de canal
        self.channel_select = discord.ui.ChannelSelect(
            placeholder="Selecione o canal exclusivo para 2FA...",
            channel_types=[discord.ChannelType.text],
            min_values=0,
            max_values=1,
            row=0,
        )
        self.channel_select.callback = self.on_channel_select
        self.add_item(self.channel_select)

        # Botão criar novo canal
        self.create_btn = discord.ui.Button(
            label="➕ Criar Novo Canal",
            style=discord.ButtonStyle.success,
            row=3,
        )
        self.create_btn.callback = self.create_totp_channel
        self.add_item(self.create_btn)

        # Botão remover configuração
        self.remove_btn = discord.ui.Button(
            label="🗑️ Remover Canal",
            style=discord.ButtonStyle.danger,
            row=3,
        )
        self.remove_btn.callback = self.remove_totp_channel
        self.add_item(self.remove_btn)

    async def build_embed(self) -> discord.Embed:
        """Constrói o embed de configuração com o estado atual."""
        settings = await self.db.get_settings(self.guild.id)
        channel_id = settings.get("channel_totp")

        if channel_id:
            channel = self.guild.get_channel(int(channel_id))
            channel_text = f"{channel.mention} (`{channel.id}`)" if channel else f"`{channel_id}` (canal não encontrado)"
        else:
            channel_text = None

        current_config = {"Canal 2FA": channel_text}

        embed = await build_standard_config_embed(
            title="🔐 Configuração do Sistema 2FA",
            description=(
                "Configure o canal onde os usuários poderão digitar suas **secret keys** para obter o código 2FA.\n\n"
                "**Como funciona:**\n"
                "• O usuário digita a secret key (base32) no canal configurado\n"
                "• O bot apaga a key imediatamente por segurança\n"
                "• O código 2FA é exibido por **30 segundos** e depois apagado\n"
                "• Funciona **apenas** neste canal dedicado"
            ),
            current_config=current_config,
            guild=self.guild,
            footer_text="Selecione um canal abaixo ou crie um novo",
        )
        return embed

    async def on_channel_select(self, interaction: discord.Interaction):
        """Salva o canal selecionado."""
        await interaction.response.defer(ephemeral=True)

        selected = interaction.data.get("values", [])
        if not selected:
            await interaction.followup.send("❌ Nenhum canal selecionado.", ephemeral=True)
            return

        channel = self.guild.get_channel(int(selected[0]))
        if not channel:
            await interaction.followup.send("❌ Canal não encontrado.", ephemeral=True)
            return

        await self.db.upsert_settings(self.guild.id, channel_totp=channel.id)

        embed = await self.build_embed()
        try:
            await interaction.message.edit(embed=embed, view=self)
        except discord.NotFound:
            pass

        await interaction.followup.send(
            f"✅ Canal 2FA configurado: {channel.mention}",
            ephemeral=True,
        )

    async def create_totp_channel(self, interaction: discord.Interaction):
        """Cria um novo canal dedicado ao 2FA."""

        async def on_success(inter: discord.Interaction, channel: discord.TextChannel):
            # Aplica permissões restritivas: apenas quem precisa pode ver/enviar
            try:
                await channel.set_permissions(
                    self.guild.default_role,
                    send_messages=True,
                    read_messages=False,  # invisível para @everyone por padrão
                )
            except discord.Forbidden:
                pass  # Sem permissão para alterar permissões do canal

            await self.db.upsert_settings(self.guild.id, channel_totp=channel.id)
            LOGGER.info("Canal 2FA '%s' criado e configurado no guild %s", channel.name, self.guild.id)

            embed = await self.build_embed()
            try:
                await inter.message.edit(embed=embed, view=self)
            except Exception:
                pass

        modal = CreateChannelModal(
            guild=self.guild,
            title="Criar Canal 2FA",
            channel_name_label="Nome do Canal 2FA",
            on_success=on_success,
        )
        await interaction.response.send_modal(modal)

    async def remove_totp_channel(self, interaction: discord.Interaction):
        """Remove a configuração do canal 2FA."""
        await interaction.response.defer(ephemeral=True)

        # Usa upsert com valor None não é suportado diretamente, então usamos SQL direto via db
        # Como o db.upsert_settings ignora None, precisamos de uma abordagem diferente
        # O jeito mais simples é salvar 0 ou usar o método genérico se disponível
        # Aqui salvamos uma string vazia que será tratada como "não configurado"
        try:
            async with self.db._conn.cursor() as cur:
                await cur.execute(
                    "UPDATE settings SET channel_totp = NULL WHERE guild_id = ?",
                    (self.guild.id,),
                )
                await self.db._conn.commit()
        except Exception as e:
            LOGGER.error("Erro ao remover canal 2FA: %s", e)
            await interaction.followup.send("❌ Erro ao remover configuração.", ephemeral=True)
            return

        embed = await self.build_embed()
        try:
            await interaction.message.edit(embed=embed, view=self)
        except discord.NotFound:
            pass

        await interaction.followup.send("✅ Canal 2FA removido.", ephemeral=True)
