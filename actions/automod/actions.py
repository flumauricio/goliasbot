"""
Automod Actions - Gerencia ações de punição do automod.

Features:
- Warn: Envia DM ao usuário
- Timeout: Aplica timeout temporário
- Ban: Bane usuário do servidor
- Logs automáticos em canal configurado
"""

import logging
from datetime import timedelta
from typing import Optional

import discord

LOGGER = logging.getLogger(__name__)


class AutomodActions:
    """Gerencia ações de punição do automod."""
    
    @staticmethod
    async def warn_user(
        member: discord.Member,
        reason: str,
        logs_channel: Optional[discord.TextChannel] = None
    ):
        """
        Envia aviso para o usuário.
        
        Args:
            member: Membro a ser avisado
            reason: Motivo do aviso
            logs_channel: Canal para registrar a ação
        """
        try:
            await member.send(
                f"⚠️ **Aviso de Moderação Automática**\n"
                f"Você foi advertido no servidor **{member.guild.name}**.\n"
                f"Motivo: {reason}\n\n"
                f"Por favor, siga as regras do servidor."
            )
            LOGGER.info(f"Aviso enviado para {member.id} em {member.guild.id}")
        except discord.Forbidden:
            LOGGER.debug(f"Não foi possível enviar DM para {member.id}")
        except Exception as e:
            LOGGER.error(f"Erro ao enviar aviso para {member.id}: {e}")
        
        if logs_channel:
            await AutomodActions._log_action(
                logs_channel, member, "Aviso", reason
            )
    
    @staticmethod
    async def timeout_user(
        member: discord.Member,
        duration_seconds: int,
        reason: str,
        logs_channel: Optional[discord.TextChannel] = None
    ):
        """
        Aplica timeout ao usuário.
        
        Args:
            member: Membro a aplicar timeout
            duration_seconds: Duração do timeout em segundos
            reason: Motivo do timeout
            logs_channel: Canal para registrar a ação
        """
        try:
            duration = timedelta(seconds=duration_seconds)
            await member.timeout(duration, reason=f"Automod: {reason}")
            
            LOGGER.info(
                f"Timeout aplicado em {member.id} ({duration_seconds}s) em {member.guild.id}"
            )
            
            try:
                await member.send(
                    f"🔇 **Timeout Aplicado**\n"
                    f"Você foi silenciado no servidor **{member.guild.name}**.\n"
                    f"Duração: {duration_seconds // 60} minutos\n"
                    f"Motivo: {reason}"
                )
            except discord.Forbidden:
                pass
            
            if logs_channel:
                await AutomodActions._log_action(
                    logs_channel, member, f"Timeout ({duration_seconds//60}min)", reason
                )
        except discord.Forbidden:
            LOGGER.error(f"Sem permissão para aplicar timeout em {member.id}")
        except Exception as e:
            LOGGER.error(f"Erro ao aplicar timeout em {member.id}: {e}")
    
    @staticmethod
    async def ban_user(
        member: discord.Member,
        reason: str,
        logs_channel: Optional[discord.TextChannel] = None
    ):
        """
        Bane o usuário.
        
        Args:
            member: Membro a ser banido
            reason: Motivo do banimento
            logs_channel: Canal para registrar a ação
        """
        try:
            try:
                await member.send(
                    f"🚫 **Banimento**\n"
                    f"Você foi banido do servidor **{member.guild.name}**.\n"
                    f"Motivo: {reason}"
                )
            except discord.Forbidden:
                pass
            
            await member.ban(reason=f"Automod: {reason}", delete_message_days=1)
            
            LOGGER.warning(f"Usuário {member.id} banido em {member.guild.id}")
            
            if logs_channel:
                await AutomodActions._log_action(
                    logs_channel, member, "Banimento", reason
                )
        except discord.Forbidden:
            LOGGER.error(f"Sem permissão para banir {member.id}")
        except Exception as e:
            LOGGER.error(f"Erro ao banir {member.id}: {e}")
    
    @staticmethod
    async def _log_action(
        channel: discord.TextChannel,
        member: discord.Member,
        action: str,
        reason: str
    ):
        """
        Registra ação no canal de logs.
        
        Args:
            channel: Canal de logs
            member: Membro que sofreu a ação
            action: Tipo de ação
            reason: Motivo
        """
        try:
            embed = discord.Embed(
                title=f"🤖 Ação Automática: {action}",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            embed.add_field(
                name="Usuário", 
                value=f"{member.mention} (`{member.id}`)", 
                inline=False
            )
            embed.add_field(name="Motivo", value=reason, inline=False)
            embed.set_footer(text="Sistema Automod")
            
            await channel.send(embed=embed)
        except discord.Forbidden:
            LOGGER.error(f"Sem permissão para enviar logs em {channel.id}")
        except Exception as e:
            LOGGER.error(f"Erro ao enviar log para {channel.id}: {e}")
