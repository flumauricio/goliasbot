import logging
from datetime import datetime

import discord
from discord.ext import commands

from db import Database

LOGGER = logging.getLogger(__name__)


class VoiceMonitorCog(commands.Cog):
    """Cog para monitoramento de tempo em call."""
    
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
    
    def _has_allowed_role(self, member: discord.Member, allowed_roles: tuple) -> bool:
        """Verifica se o membro tem algum cargo permitido."""
        if not allowed_roles:
            return False
        member_role_ids = {role.id for role in member.roles}
        return bool(member_role_ids & set(allowed_roles))
    
    def _is_channel_monitored(
        self,
        channel_id: int,
        guild_id: int,
        monitor_all: bool,
        monitored_channels: tuple
    ) -> bool:
        """Verifica se um canal é monitorado."""
        if monitor_all:
            return True
        return channel_id in monitored_channels
    
    async def _end_session(self, user_id: int, guild_id: int) -> None:
        """Encerra uma sessão ativa e salva o tempo."""
        session = await self.db.get_voice_session(user_id, guild_id)
        if not session:
            return
        
        # Calcula o tempo decorrido
        join_time_str = session.get("join_time")
        if not join_time_str:
            await self.db.delete_voice_session(user_id, guild_id)
            return
        
        try:
            # Parse do timestamp (formato SQLite: YYYY-MM-DD HH:MM:SS)
            join_time = datetime.fromisoformat(join_time_str.replace(" ", "T"))
            now = datetime.utcnow()
            delta = now - join_time
            seconds = int(delta.total_seconds())
            
            if seconds > 0:
                channel_id = int(session.get("channel_id", 0))
                await self.db.increment_voice_time(guild_id, user_id, channel_id, seconds)
                LOGGER.debug(
                    "Sessão encerrada: user_id=%s, guild_id=%s, channel_id=%s, seconds=%d",
                    user_id, guild_id, channel_id, seconds
                )
        except Exception as exc:
            LOGGER.error("Erro ao calcular tempo da sessão: %s", exc)
        
        # Remove a sessão
        await self.db.delete_voice_session(user_id, guild_id)
    
    async def _start_session(
        self,
        user_id: int,
        guild_id: int,
        channel_id: int
    ) -> None:
        """Inicia uma nova sessão de voz."""
        await self.db.create_voice_session(user_id, guild_id, channel_id)
        LOGGER.debug(
            "Sessão iniciada: user_id=%s, guild_id=%s, channel_id=%s",
            user_id, guild_id, channel_id
        )
    
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ):
        """Monitora mudanças no estado de voz dos membros."""
        if not member.guild:
            return
        
        guild_id = member.guild.id
        user_id = member.id
        
        # Busca configurações
        settings = await self.db.get_voice_settings(guild_id)
        monitor_all = settings.get("monitor_all", 0) == 1
        afk_channel_id = settings.get("afk_channel_id")
        afk_channel_id_int = int(afk_channel_id) if afk_channel_id and str(afk_channel_id).isdigit() else None
        
        allowed_roles = await self.db.get_allowed_roles(guild_id)
        monitored_channels = await self.db.get_monitored_channels(guild_id)
        
        # Verifica se o usuário tem cargo permitido
        if not self._has_allowed_role(member, allowed_roles):
            # Se não tem cargo, encerra sessão se existir
            session = await self.db.get_voice_session(user_id, guild_id)
            if session:
                await self._end_session(user_id, guild_id)
            return
        
        before_channel_id = before.channel.id if before.channel and isinstance(before.channel, discord.VoiceChannel) else None
        after_channel_id = after.channel.id if after.channel and isinstance(after.channel, discord.VoiceChannel) else None
        
        # Caso 1: Usuário entrou em um canal
        if not before.channel and after.channel:
            # Verifica se é canal AFK
            if after_channel_id == afk_channel_id_int:
                # Não inicia sessão para AFK
                return
            
            # Verifica se o canal é monitorado
            if self._is_channel_monitored(after_channel_id, guild_id, monitor_all, monitored_channels):
                await self._start_session(user_id, guild_id, after_channel_id)
        
        # Caso 2: Usuário saiu de um canal
        elif before.channel and not after.channel:
            # Encerra a sessão atual
            await self._end_session(user_id, guild_id)
        
        # Caso 3: Usuário mudou de canal
        elif before.channel and after.channel and before_channel_id != after_channel_id:
            # Verifica se entrou no AFK
            if after_channel_id == afk_channel_id_int:
                # Encerra sessão anterior (não acumula tempo no AFK)
                await self._end_session(user_id, guild_id)
                return
            
            # Verifica se saiu do AFK
            if before_channel_id == afk_channel_id_int:
                # Se o canal destino é monitorado, inicia nova sessão
                if self._is_channel_monitored(after_channel_id, guild_id, monitor_all, monitored_channels):
                    await self._start_session(user_id, guild_id, after_channel_id)
                return
            
            # Mudança entre canais normais
            before_monitored = self._is_channel_monitored(before_channel_id, guild_id, monitor_all, monitored_channels)
            after_monitored = self._is_channel_monitored(after_channel_id, guild_id, monitor_all, monitored_channels)
            
            if before_monitored and not after_monitored:
                # Saiu de monitorado para não monitorado: encerra sessão
                await self._end_session(user_id, guild_id)
            elif before_monitored and after_monitored:
                # Saiu de monitorado para monitorado: encerra anterior, inicia nova
                await self._end_session(user_id, guild_id)
                await self._start_session(user_id, guild_id, after_channel_id)
            elif not before_monitored and after_monitored:
                # Saiu de não monitorado para monitorado: inicia nova
                await self._start_session(user_id, guild_id, after_channel_id)
