"""
Streams Cog - Sistema de notificações de live (Twitch/YouTube).

Features:
- Task check_streams_task (a cada 2 minutos)
- Task update_live_embeds_task (a cada 5 minutos)
- Exponential Backoff para retry de APIs externas
- Cooldown de 10 minutos para anúncios
- Detecção de stream offline → edita para "Live Encerrada"
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

import discord
from discord.ext import commands, tasks

from db import Database
from utils.config_cache import ConfigCacheManager
from .models import StreamInfo, Platform, AnnouncementData
from .embed_manager import StreamEmbedManager

LOGGER = logging.getLogger(__name__)


class StreamsCog(commands.Cog):
    """Sistema de notificações de live (Twitch/YouTube)."""
    
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
        self.config_cache = ConfigCacheManager()
        self.embed_manager = StreamEmbedManager()
        
        # Cooldown tracking: {(guild_id, channel_name): last_announcement_time}
        self._announcement_cooldowns: Dict[tuple, datetime] = {}
        
        # Active announcements: {(guild_id, stream_id): AnnouncementData}
        self._active_announcements: Dict[tuple, AnnouncementData] = {}
        
        # Tasks
        self.check_streams_task.start()
        self.update_live_embeds_task.start()
    
    def cog_unload(self):
        self.check_streams_task.cancel()
        self.update_live_embeds_task.cancel()
    
    @tasks.loop(minutes=2)
    async def check_streams_task(self):
        """Verifica status de streams configurados."""
        try:
            # Busca todos os servidores com stream config ativa
            guilds_with_streams = await self.db.get_guilds_with_stream_config()
            
            for guild_data in guilds_with_streams:
                guild_id = guild_data['guild_id']
                guild = self.bot.get_guild(int(guild_id))
                
                if not guild:
                    continue
                
                # Processa streams do servidor
                await self._check_guild_streams(guild)
        except Exception as e:
            LOGGER.error(f"Erro em check_streams_task: {e}", exc_info=True)
    
    @check_streams_task.before_loop
    async def before_check_streams(self):
        await self.bot.wait_until_ready()
    
    @tasks.loop(minutes=5)
    async def update_live_embeds_task(self):
        """
        Atualiza embeds de lives ativas.
        
        RATE LIMITING: Respeita intervalo mínimo de 5 minutos entre atualizações
        para evitar rate limits do Discord (exceto se stream ficar offline).
        """
        try:
            for key, announcement in list(self._active_announcements.items()):
                guild_id, stream_id = key
                guild = self.bot.get_guild(guild_id)
                
                if not guild:
                    continue
                
                # RATE LIMITING: Verifica se já atualizou recentemente
                if announcement.last_updated:
                    elapsed = datetime.utcnow() - announcement.last_updated
                    if elapsed < timedelta(minutes=5):
                        continue  # Ainda em cooldown
                
                # Busca info atualizada do stream
                stream_info = await self._fetch_stream_info_with_retry(
                    announcement.stream_info.platform,
                    announcement.stream_info.channel_name
                )
                
                if not stream_info:
                    # Stream offline - marca como encerrado (BYPASS do rate limit)
                    await self._end_stream_announcement(guild_id, stream_id, announcement)
                    continue
                
                # Atualiza peak viewers
                if stream_info.viewer_count > announcement.peak_viewers:
                    announcement.peak_viewers = stream_info.viewer_count
                
                # Atualiza embed
                config = await self.config_cache.get_stream_config(self.db, guild_id)
                channel_id = config.get('announcement_channel_id')
                
                if channel_id:
                    channel = guild.get_channel(int(channel_id))
                    if channel:
                        try:
                            message = await channel.fetch_message(announcement.message_id)
                            success = await self.embed_manager.update_live_embed(
                                message,
                                stream_info.viewer_count,
                                announcement.peak_viewers
                            )
                            if success:
                                # Marca timestamp da última atualização
                                announcement.last_updated = datetime.utcnow()
                        except discord.NotFound:
                            del self._active_announcements[key]
                        except discord.HTTPException as e:
                            # Rate limited - aguarda mais tempo
                            LOGGER.warning(f"Rate limited ao atualizar embed: {e}")
                            continue
        except Exception as e:
            LOGGER.error(f"Erro em update_live_embeds_task: {e}", exc_info=True)
    
    @update_live_embeds_task.before_loop
    async def before_update_embeds(self):
        await self.bot.wait_until_ready()
    
    async def _check_guild_streams(self, guild: discord.Guild):
        """Verifica streams de um servidor."""
        try:
            config = await self.config_cache.get_stream_config(self.db, guild.id)
            
            if not config or not config.get('enabled'):
                return
            
            # Busca canais monitorados
            stream_channels = await self.db.get_stream_channels(guild.id)
            
            for channel_data in stream_channels:
                if not channel_data.get('is_active'):
                    continue
                
                platform = Platform(channel_data['platform'])
                channel_name = channel_data['channel_name']
                
                # Busca info do stream com retry
                stream_info = await self._fetch_stream_info_with_retry(platform, channel_name)
                
                if stream_info:
                    # Stream está online
                    await self._handle_stream_online(
                        guild, channel_data['id'], stream_info, config
                    )
        except Exception as e:
            LOGGER.error(f"Erro em _check_guild_streams para {guild.id}: {e}")
    
    async def _fetch_stream_info_with_retry(
        self, 
        platform: Platform, 
        channel_name: str,
        max_retries: int = 3
    ) -> Optional[StreamInfo]:
        """
        Busca stream info com exponential backoff.
        
        RESILIÊNCIA: Retry com exponential backoff (2s, 4s, 8s) para tratar
        falhas temporárias de rede ou rate limits da API.
        
        Args:
            platform: Plataforma (Twitch/YouTube)
            channel_name: Nome do canal
            max_retries: Número máximo de tentativas
        
        Returns:
            StreamInfo se online, None se offline ou erro
        """
        for attempt in range(max_retries):
            try:
                result = await self._fetch_stream_info(platform, channel_name)
                return result
            except Exception as e:
                if attempt == max_retries - 1:
                    LOGGER.error(
                        f"Falha após {max_retries} tentativas para {channel_name}: {e}"
                    )
                    return None
                
                # Exponential backoff: 2^attempt segundos (2s, 4s, 8s)
                delay = 2 ** attempt
                LOGGER.warning(
                    f"Erro ao buscar stream {channel_name} (tentativa {attempt+1}): {e}. "
                    f"Retry em {delay}s"
                )
                await asyncio.sleep(delay)
        
        return None
    
    async def _fetch_stream_info(
        self, platform: Platform, channel_name: str
    ) -> Optional[StreamInfo]:
        """
        Busca informações de um stream.
        
        NOTA: Implementação real requer integração com APIs externas:
        - Twitch: Helix API
        - YouTube: Data API v3
        
        Por ora, retorna None (stub para implementação futura).
        """
        # TODO: Implementar integração com APIs externas
        # Esta é uma função placeholder que deve ser implementada com:
        # - Twitch Helix API para Twitch
        # - YouTube Data API v3 para YouTube
        # - Autenticação apropriada (OAuth2)
        # - Rate limiting
        
        return None
    
    async def _handle_stream_online(
        self,
        guild: discord.Guild,
        stream_id: int,
        stream_info: StreamInfo,
        config: dict
    ):
        """Processa stream online - envia anúncio se necessário."""
        try:
            # Verifica cooldown
            cooldown_key = (guild.id, stream_info.channel_name)
            if cooldown_key in self._announcement_cooldowns:
                last_announcement = self._announcement_cooldowns[cooldown_key]
                cooldown_minutes = config.get('cooldown_minutes', 10)
                
                if datetime.utcnow() < last_announcement + timedelta(minutes=cooldown_minutes):
                    return  # Ainda em cooldown
            
            # Verifica se já tem anúncio ativo
            active_key = (guild.id, stream_id)
            if active_key in self._active_announcements:
                return  # Já anunciado
            
            # Envia anúncio
            channel_id = config.get('announcement_channel_id')
            if not channel_id:
                return
            
            channel = guild.get_channel(int(channel_id))
            if not channel or not isinstance(channel, discord.TextChannel):
                return
            
            # Cria embed
            ping_role_id = config.get('ping_role_id')
            ping_text = f"<@&{ping_role_id}>" if ping_role_id else "@everyone"
            
            embed = self.embed_manager.create_live_embed(stream_info, ping_text)
            
            message = await channel.send(content=ping_text, embed=embed)
            
            # Registra anúncio
            self._announcement_cooldowns[cooldown_key] = datetime.utcnow()
            self._active_announcements[active_key] = AnnouncementData(
                message_id=message.id,
                stream_info=stream_info,
                announced_at=datetime.utcnow()
            )
            
            # Salva no banco
            await self.db.add_stream_announcement(
                guild.id,
                stream_id,
                message.id,
                stream_info.title,
                stream_info.thumbnail_url
            )
            
            LOGGER.info(
                f"Anúncio de live enviado: {stream_info.channel_name} em {guild.name}"
            )
        except discord.Forbidden:
            LOGGER.error(f"Sem permissão para enviar anúncio em {guild.id}")
        except Exception as e:
            LOGGER.error(f"Erro em _handle_stream_online: {e}")
    
    async def _end_stream_announcement(
        self,
        guild_id: int,
        stream_id: int,
        announcement: AnnouncementData
    ):
        """Finaliza anúncio de live (edita embed ou deixa como está)."""
        try:
            guild = self.bot.get_guild(guild_id)
            if not guild:
                return
            
            config = await self.config_cache.get_stream_config(self.db, guild_id)
            
            # Verifica se deve editar ao encerrar
            if not config.get('edit_on_end', True):
                del self._active_announcements[(guild_id, stream_id)]
                return
            
            # Calcula duração
            duration = datetime.utcnow() - announcement.announced_at
            duration_minutes = int(duration.total_seconds() / 60)
            
            # Busca mensagem e edita
            channel_id = config.get('announcement_channel_id')
            if channel_id:
                channel = guild.get_channel(int(channel_id))
                if channel:
                    try:
                        message = await channel.fetch_message(announcement.message_id)
                        ended_embed = self.embed_manager.create_ended_embed(
                            announcement.stream_info,
                            duration_minutes,
                            announcement.peak_viewers
                        )
                        await message.edit(embed=ended_embed)
                    except discord.NotFound:
                        pass
            
            # Atualiza no banco
            await self.db.update_stream_announcement_ended(
                guild_id,
                stream_id,
                announcement.peak_viewers,
                duration_minutes
            )
            
            # Remove do tracking
            del self._active_announcements[(guild_id, stream_id)]
            
            LOGGER.info(
                f"Live encerrada: {announcement.stream_info.channel_name} em guild={guild_id}"
            )
        except Exception as e:
            LOGGER.error(f"Erro em _end_stream_announcement: {e}")


async def setup(bot: commands.Bot):
    await bot.add_cog(StreamsCog(bot, bot.db))
