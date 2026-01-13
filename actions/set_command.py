import logging
import discord
from discord.ext import commands

from config_manager import ConfigManager
from db import Database
from permissions import command_guard
from .registration import RegistrationView

LOGGER = logging.getLogger(__name__)

class SetCog(commands.Cog):
    def __init__(self, bot: commands.Bot, db: Database, config: ConfigManager):
        self.bot = bot
        self.db = db
        self.config = config

    @commands.command(name="set")
    @command_guard("set")
    async def set_registration_embed(self, ctx: commands.Context):
        """Publica ou atualiza o embed de cadastro no canal configurado (apenas Staff/Admin).

Uso: !set

Exemplos:
- !set
"""
        guild = ctx.guild
        if not guild:
            await ctx.reply("Apenas em servidores.")
            return

        # Busca configurações no Banco de Dados (fonte única de verdade)
        settings = await self.db.get_settings(guild.id)
        channel_id = settings.get("channel_registration_embed")

        if not channel_id:
            await ctx.reply("Canal de cadastro não configurado. Rode !setup primeiro.")
            return

        target_channel = guild.get_channel(int(channel_id))
        if not target_channel:
            await ctx.reply("Não encontrei o canal configurado.")
            return

        embed = discord.Embed(
            title="🎯 Cadastro de Membro",
            description=(
                "Clique no botão abaixo para iniciar seu cadastro.\n\n"
                "✅ Siga as regras do servidor antes de enviar.\n"
                "🛟 Precisa de ajuda? Fale com a staff."
            ),
            color=discord.Color.purple(),
        )
        
        embed.add_field(
            name="Regras rápidas",
            value="• Respeite a comunidade\n• Sem SPAM\n• Use IDs corretos\n• Aguarde aprovação",
            inline=False,
        )

        # --- CORREÇÃO DEFINITIVA DO ERRO ---
        # Verificamos se o bot tem avatar, se não tiver, usamos None
        bot_avatar_url = None
        if guild.me.display_avatar:
            bot_avatar_url = guild.me.display_avatar.url

        embed.set_footer(
            text="Golias Bot • Cadastro",
            icon_url=bot_avatar_url
        )
        # -----------------------------------

        view = RegistrationView(self.db, self.config)

        # Verifica se já existe uma mensagem enviada anteriormente para editar
        existing_message_id = settings.get("message_set_embed")

        message = None
        if existing_message_id:
            try:
                message = await target_channel.fetch_message(int(existing_message_id))
                await message.edit(embed=embed, view=view)
            except Exception:
                LOGGER.warning("Não consegui atualizar mensagem existente, criando nova.")

        if not message:
            message = await target_channel.send(embed=embed, view=view)

        # Salva as configurações atualizadas no Banco (fonte única de verdade)
        await self.db.upsert_settings(
            guild.id,
            channel_registration_embed=int(channel_id),
            message_set_embed=message.id,
        )
        
        await ctx.reply(f"✅ Painel de cadastro configurado com sucesso em {target_channel.mention}!")


async def setup(bot):
    """Função de setup para carregamento da extensão."""
    from config_manager import ConfigManager
    from db import Database
    
    await bot.add_cog(SetCog(bot, bot.db, bot.config_manager))