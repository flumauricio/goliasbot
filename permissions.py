import logging
from typing import Callable, Optional

import discord
from discord.ext import commands

from db import Database


LOGGER = logging.getLogger(__name__)


async def check_command_permission(ctx: commands.Context, command_name: str) -> bool:
    """Verifica se o autor do comando pode executá-lo nesta guild.

    Regras:
    - Se não for em guild, bloqueia.
    - Admin do servidor sempre pode (para comandos protegidos por cargos).
    - Se não houver configuração no DB -> apenas admin.
    - role_ids == '0' -> apenas admin.
    - role_ids com IDs -> precisa ter pelo menos um desses cargos (ou ser admin).
    """
    guild = ctx.guild
    if guild is None:
        return False

    author: discord.Member = ctx.author  # type: ignore[assignment]

    # Admin sempre possui permissão lógica (checks de permissão do Discord ainda se aplicam)
    if author.guild_permissions.administrator:
        return True

    db: Database = ctx.bot.db  # type: ignore[attr-defined]
    role_ids = db.get_command_permissions(guild.id, command_name)

    # Sem configuração explícita -> apenas admins (já checado acima)
    if role_ids is None:
        return False

    role_ids = role_ids.strip()
    if not role_ids or role_ids == "0":
        # Configuração explícita de "apenas admin" ou vazio
        return False

    try:
        allowed_ids = {int(rid) for rid in role_ids.split(",") if rid.strip()}
    except ValueError:
        LOGGER.warning("role_ids inválidos para %s/%s: %s", guild.id, command_name, role_ids)
        return False

    author_role_ids = {role.id for role in author.roles}
    return bool(allowed_ids & author_role_ids)


def command_guard(command_name: str) -> Callable:
    """Decorator de proteção por cargos, baseado em DB."""

    async def predicate(ctx: commands.Context) -> bool:
        allowed = await check_command_permission(ctx, command_name)
        if not allowed:
            await ctx.send("Você não tem permissão para usar este comando.", delete_after=5)
        return allowed

    return commands.check(predicate)


