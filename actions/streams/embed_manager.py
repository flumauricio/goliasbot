"""
Stream Embed Manager - Gerencia criação e atualização de embeds de live.

Features:
- Cria embed de anúncio de live
- Atualiza embed com novos dados de espectadores
- Cria embed de live encerrada
- Rate limit protection: mínimo 5 minutos entre updates
"""

import logging
from datetime import datetime
from typing import Optional

import discord

from .models import StreamInfo, Platform

LOGGER = logging.getLogger(__name__)


class StreamEmbedManager:
    """Gerencia criação e atualização de embeds de live."""
    
    @staticmethod
    def create_live_embed(stream: StreamInfo, ping_role: str = "@everyone") -> discord.Embed:
        """
        Cria embed de anúncio de live.
        
        Args:
            stream: Informações da live
            ping_role: Cargo para notificar
        
        Returns:
            discord.Embed configurado
        """
        platform_emoji = "🎮" if stream.platform == Platform.TWITCH else "📺"
        color = discord.Color.purple() if stream.platform == Platform.TWITCH else discord.Color.red()
        
        embed = discord.Embed(
            title=f"{platform_emoji} {stream.channel_name} está AO VIVO!",
            description=stream.title or "Sem título",
            url=stream.stream_url,
            color=color,
            timestamp=datetime.utcnow()
        )
        
        embed.add_field(
            name="👥 Espectadores",
            value=f"{stream.viewer_count:,}",
            inline=True
        )
        
        embed.add_field(
            name="📺 Plataforma",
            value=stream.platform.value.capitalize(),
            inline=True
        )
        
        if stream.thumbnail_url:
            embed.set_image(url=stream.thumbnail_url)
        
        embed.set_footer(text=f"🔴 Live iniciada")
        
        return embed
    
    @staticmethod
    def create_ended_embed(
        stream: StreamInfo,
        duration_minutes: int,
        peak_viewers: int
    ) -> discord.Embed:
        """
        Cria embed de live encerrada.
        
        Args:
            stream: Informações da live
            duration_minutes: Duração em minutos
            peak_viewers: Pico de espectadores
        
        Returns:
            discord.Embed configurado
        """
        platform_emoji = "🎮" if stream.platform == Platform.TWITCH else "📺"
        
        embed = discord.Embed(
            title=f"{platform_emoji} Live Encerrada - {stream.channel_name}",
            description=stream.title or "Sem título",
            color=discord.Color.dark_gray(),
            timestamp=datetime.utcnow()
        )
        
        hours = duration_minutes // 60
        minutes = duration_minutes % 60
        duration_str = f"{hours}h {minutes}min" if hours > 0 else f"{minutes}min"
        
        embed.add_field(
            name="⏱️ Duração",
            value=duration_str,
            inline=True
        )
        
        embed.add_field(
            name="📊 Pico de Espectadores",
            value=f"{peak_viewers:,}",
            inline=True
        )
        
        embed.set_footer(text="⚫ Live encerrada")
        
        return embed
    
    @staticmethod
    async def update_live_embed(
        message: discord.Message,
        current_viewers: int,
        peak_viewers: int
    ) -> bool:
        """
        Atualiza embed com novos dados de espectadores.
        
        PROTEÇÃO DE RATE LIMIT: Método não controla rate limit internamente.
        O rate limit é gerenciado pelo Cog (mínimo 5 minutos entre updates).
        
        Args:
            message: Mensagem do anúncio
            current_viewers: Espectadores atuais
            peak_viewers: Pico de espectadores
        
        Returns:
            True se atualizou com sucesso, False caso contrário
        """
        if not message.embeds:
            LOGGER.warning(f"Mensagem {message.id} não possui embeds")
            return False
        
        try:
            embed = message.embeds[0]
            
            # Atualiza campo de espectadores
            for i, field in enumerate(embed.fields):
                if "Espectadores" in field.name:
                    embed.set_field_at(
                        i,
                        name="👥 Espectadores",
                        value=f"{current_viewers:,} (pico: {peak_viewers:,})",
                        inline=True
                    )
                    break
            
            await message.edit(embed=embed)
            LOGGER.debug(f"Embed {message.id} atualizado: viewers={current_viewers}")
            return True
        except discord.Forbidden:
            LOGGER.error(f"Sem permissão para editar mensagem {message.id}")
            return False
        except discord.NotFound:
            LOGGER.warning(f"Mensagem {message.id} não encontrada")
            return False
        except discord.HTTPException as e:
            LOGGER.error(f"Erro HTTP ao atualizar embed {message.id}: {e}")
            return False
        except Exception as e:
            LOGGER.error(f"Erro ao atualizar embed {message.id}: {e}")
            return False
