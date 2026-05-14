"""
Sistema de 2FA (TOTP) para o bot.

Como funciona:
- O usuário digita a secret key (base32) no canal configurado
- O bot apaga a mensagem com a key imediatamente
- Retorna o código TOTP atual em caixa de código
- Apaga a resposta após 30 segundos
"""

import asyncio
import base64
import hashlib
import hmac
import logging
import struct
import time

import discord
from discord.ext import commands

from db import Database

LOGGER = logging.getLogger(__name__)


def _generate_totp(secret: str, digits: int = 6, interval: int = 30) -> str:
    """
    Gera um código TOTP a partir da secret key (base32).
    Implementação manual, sem dependências externas.
    """
    # Remove espaços, hífens e converte para maiúsculas (formato padrão base32)
    secret = secret.replace(" ", "").replace("-", "").upper()

    # Adiciona padding '=' para completar múltiplo de 8 (muitos apps omitem o padding)
    remainder = len(secret) % 8
    if remainder:
        secret += "=" * (8 - remainder)

    # Decodifica a chave base32
    try:
        key = base64.b32decode(secret, casefold=True)
    except Exception:
        raise ValueError("Chave inválida. Certifique-se de que é uma chave base32 válida.")

    # Calcula o contador baseado no tempo atual
    counter = int(time.time()) // interval

    # Gera HMAC-SHA1
    counter_bytes = struct.pack(">Q", counter)
    hmac_hash = hmac.new(key, counter_bytes, hashlib.sha1).digest()

    # Dynamic truncation
    offset = hmac_hash[-1] & 0x0F
    code_int = struct.unpack(">I", hmac_hash[offset : offset + 4])[0] & 0x7FFFFFFF

    # Reduz para o número de dígitos desejado
    code = code_int % (10**digits)

    # Retorna com zero-padding (ex: "042891")
    return str(code).zfill(digits)


def _get_seconds_remaining(interval: int = 30) -> int:
    """Retorna quantos segundos faltam para o próximo código."""
    return interval - (int(time.time()) % interval)


class TotpCog(commands.Cog):
    """Cog responsável pelo sistema de 2FA via TOTP."""

    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Escuta mensagens no canal 2FA configurado."""

        # Ignora mensagens do próprio bot
        if message.author.bot:
            return

        # Só funciona em servidores
        if not message.guild:
            return

        # Busca o canal 2FA configurado para este servidor
        settings = await self.db.get_settings(message.guild.id)
        totp_channel_id = settings.get("channel_totp")

        if not totp_channel_id:
            return  # Canal não configurado, ignora

        # Verifica se a mensagem foi enviada no canal 2FA
        if message.channel.id != int(totp_channel_id):
            return

        # Pega o conteúdo da mensagem (a secret key)
        secret_key = message.content.strip()

        # Ignora mensagens vazias ou que parecem ser comandos do bot
        if not secret_key or secret_key.startswith("!"):
            return

        # Apaga a mensagem com a key imediatamente (segurança)
        try:
            await message.delete()
        except discord.Forbidden:
            LOGGER.warning(
                "Sem permissão para apagar mensagem no canal 2FA (guild: %s)",
                message.guild.id,
            )
            await message.channel.send(
                "⚠️ Sem permissão para apagar mensagens. Peça ao administrador para conceder a permissão **Gerenciar Mensagens**.",
                delete_after=15,
            )
            return
        except discord.NotFound:
            pass  # Mensagem já foi apagada

        # Gera o código TOTP
        try:
            code = _generate_totp(secret_key)
            seconds_left = _get_seconds_remaining()
        except ValueError:
            await message.channel.send(
                f"❌ {message.author.mention} — Chave inválida! Certifique-se de usar a **secret key** do seu autenticador (ex: `JBSWY3DPEHPK3PXP`).",
                delete_after=10,
            )
            return

        # Monta o embed com o código
        embed = discord.Embed(
            title="🔐 Código 2FA",
            description=f"Solicitado por {message.author.mention}",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="Código",
            value=f"```{code}```",
            inline=False,
        )
        embed.add_field(
            name="⏱️ Expira em",
            value=f"`{seconds_left}` segundos",
            inline=True,
        )
        embed.set_footer(text="Esta mensagem será apagada em 30 segundos.")

        # Envia o código e apaga após 30 segundos
        try:
            response = await message.channel.send(embed=embed)
            await asyncio.sleep(30)
            await response.delete()
        except discord.NotFound:
            pass  # Mensagem já foi apagada (ex: canal limpo)
        except discord.Forbidden:
            LOGGER.warning(
                "Sem permissão para apagar resposta 2FA (guild: %s)",
                message.guild.id,
            )


async def setup(bot):
    """Função de setup para carregamento da extensão."""
    await bot.add_cog(TotpCog(bot, bot.db))
