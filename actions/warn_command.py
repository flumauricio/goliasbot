import logging
from typing import Optional

import discord
from discord.ext import commands

from config_manager import ConfigManager
from db import Database
from permissions import command_guard
from .registration import _get_settings


LOGGER = logging.getLogger(__name__)


class WarnCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database, config: ConfigManager):
        self.bot = bot
        self.db = db
        self.config = config

    def _find_member_by_server_id(self, guild: discord.Guild, server_id: str) -> Optional[discord.Member]:
        server_id = server_id.strip()
        for member in guild.members:
            name = member.nick or member.name
            if "|" not in name:
                continue
            left, right = name.split("|", 1)
            if right.strip() == server_id:
                return member
        return None

    @commands.command(name="adv")
    @command_guard("adv")
    async def add_warning(self, ctx: commands.Context, server_id: str, *, motivo: str):
        """Aplica advertência progressiva baseada no ID após o | do apelido.

        Uso: !adv 1234 motivo da advertência
        """
        guild = ctx.guild
        if not guild:
            await ctx.reply("Use este comando em um servidor.")
            return

        member = self._find_member_by_server_id(guild, server_id)
        if not member:
            await ctx.reply(f"Não encontrei membro com ID '{server_id}' no apelido.")
            return

        channels, roles, _ = _get_settings(self.db, self.config, guild.id)
        warn_channel_id = channels.get("warnings") or channels.get("channel_warnings")
        role_adv1_id = roles.get("adv1") or roles.get("role_adv1")
        role_adv2_id = roles.get("adv2") or roles.get("role_adv2")

        if not (role_adv1_id and role_adv2_id and warn_channel_id):
            await ctx.reply("Canais/cargos de advertência não configurados. Rode !setup.")
            return

        role_adv1 = guild.get_role(int(role_adv1_id))
        role_adv2 = guild.get_role(int(role_adv2_id))
        warn_channel = guild.get_channel(int(warn_channel_id))

        if not (role_adv1 and role_adv2 and isinstance(warn_channel, discord.TextChannel)):
            await ctx.reply("Não consegui localizar cargos/canal de advertência. Verifique IDs no !setup.")
            return

        has_adv1 = role_adv1 in member.roles
        has_adv2 = role_adv2 in member.roles

        action = ""

        if not has_adv1:
            await member.add_roles(role_adv1, reason=f"Advertência 1 aplicada por {ctx.author}: {motivo}")
            action = "ADV 1 aplicada"
            dm_text = (
                "Você recebeu sua **primeira advertência (ADV 1)** no servidor.\n"
                f"Motivo: {motivo}"
            )
        elif not has_adv2:
            await member.add_roles(role_adv2, reason=f"Advertência 2 aplicada por {ctx.author}: {motivo}")
            action = "ADV 2 aplicada"
            dm_text = (
                "Você recebeu sua **segunda advertência (ADV 2)** no servidor.\n"
                f"Motivo: {motivo}"
            )
        else:
            # Terceira vez: banimento
            action = "Banimento após ADV 2"
            dm_text = (
                "Você já possuía duas advertências (ADV 2) e foi banido do servidor.\n"
                f"Motivo: {motivo}"
            )
            try:
                await member.send(dm_text)
            except discord.Forbidden:
                LOGGER.warning("Não consegui enviar DM de banimento para %s", member.id)
            await guild.ban(member, reason=f"Banido após ADV 2 por {ctx.author}: {motivo}")

            # Log no canal e resposta e encerrar
            embed = discord.Embed(
                title="🚫 Usuário banido por advertências",
                color=discord.Color.dark_red(),
            )
            embed.add_field(name="Usuário", value=f"{member.mention} ({member.id})", inline=False)
            embed.add_field(name="Ação", value=action, inline=False)
            embed.add_field(name="Motivo", value=motivo, inline=False)
            embed.add_field(name="Executor", value=ctx.author.mention, inline=False)
            await warn_channel.send(embed=embed)
            await ctx.reply(f"{member.mention} foi banido após ADV 2.")
            return

        # Log para ADV 1/2
        embed = discord.Embed(
            title="⚠️ Advertência aplicada",
            color=discord.Color.orange(),
        )
        embed.add_field(name="Usuário", value=f"{member.mention} ({member.id})", inline=False)
        embed.add_field(name="ID no servidor", value=server_id, inline=True)
        embed.add_field(name="Ação", value=action, inline=True)
        embed.add_field(name="Motivo", value=motivo, inline=False)
        embed.add_field(name="Executor", value=ctx.author.mention, inline=False)
        embed.set_thumbnail(url=member.display_avatar.url)

        await warn_channel.send(embed=embed)
        try:
            await member.send(dm_text)
        except discord.Forbidden:
            LOGGER.warning("Não consegui enviar DM de advertência para %s", member.id)

        await ctx.reply(f"{action} para {member.mention}.")


