"""
Automod Cog - Sistema de Anti-Raid e Automod Inteligente.

Features:
- Event listener on_message com detecção paralela
- Verificação de whitelist (admin/roles/canais)
- Punição graduada: 1ª=warn, 2ª=timeout, 3ª=ban
- Task de cleanup horário (dados detector + violações antigas)
- Fire-and-forget para logs no banco (não bloqueia)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import discord
from discord.ext import commands, tasks

from db import Database
from utils.config_cache import ConfigCacheManager
from .detector import SpamDetector
from .actions import AutomodActions

LOGGER = logging.getLogger(__name__)


class AutomodCog(commands.Cog):
    """Sistema de Anti-Raid e Automod Inteligente."""
    
    def __init__(self, bot: commands.Bot, db: Database):
        self.bot = bot
        self.db = db
        self.config_cache = ConfigCacheManager()
        self.detector = SpamDetector()
        
        # Rastreamento de violações por usuário: {(guild_id, user_id): (count, timestamp)}
        self._violation_counts = {}
        
        # Cleanup task
        self.cleanup_task.start()
    
    def cog_unload(self):
        self.cleanup_task.cancel()
    
    @tasks.loop(hours=24)
    async def cleanup_task(self):
        """Limpa dados antigos do detector e violações antigas do banco."""
        try:
            # Limpa dados do detector
            self.detector.cleanup_old_data()
            
            # Limpa violações antigas (>30 dias)
            deleted = await self.db.cleanup_old_violations(days=30)
            if deleted > 0:
                LOGGER.info(f"Cleanup automod: {deleted} violações antigas removidas")
            
            # Limpa violation counts antigos (>24h)
            cutoff = datetime.utcnow() - timedelta(hours=24)
            keys_to_remove = [
                key for key, (count, timestamp) in self._violation_counts.items()
                if timestamp < cutoff
            ]
            for key in keys_to_remove:
                del self._violation_counts[key]
            
            if keys_to_remove:
                LOGGER.info(f"Cleanup automod: {len(keys_to_remove)} violation counts limpos")
        except Exception as e:
            LOGGER.error(f"Erro no cleanup_task: {e}", exc_info=True)
    
    @cleanup_task.before_loop
    async def before_cleanup(self):
        await self.bot.wait_until_ready()
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Processa mensagens para detecção de spam/raid."""
        # Ignora bots e DMs
        if message.author.bot or not message.guild:
            return
        
        try:
            # Busca config com cache
            config = await self.config_cache.get_automod_config(
                self.db, message.guild.id
            )
            
            if not config or not config.get('enabled'):
                return
            
            # Verifica whitelist
            if await self._is_whitelisted(message):
                return
            
            # Adiciona ao histórico
            self.detector.add_message(
                message.guild.id,
                message.author.id,
                message.content,
                message.id
            )
            
            # Detecções paralelas
            violations = await asyncio.gather(
                self._check_spam(message, config),
                self._check_similarity(message, config),
                self._check_mentions(message, config),
                self._check_links(message, config),
                return_exceptions=True
            )
            
            # Processa violações
            for violation in violations:
                if isinstance(violation, Exception):
                    LOGGER.error(f"Erro na detecção: {violation}")
                elif violation:
                    await self._handle_violation(message, violation, config)
                    break  # Uma violação por vez
        except Exception as e:
            LOGGER.error(f"Erro em on_message automod: {e}", exc_info=True)
    
    async def _is_whitelisted(self, message: discord.Message) -> bool:
        """Verifica se canal ou usuário está na whitelist."""
        # Admin sempre whitelisted
        if message.author.guild_permissions.administrator:
            return True
        
        try:
            # Busca whitelist do banco
            whitelist = await self.db.get_automod_whitelist(message.guild.id)
            
            # Verifica canais
            if str(message.channel.id) in whitelist.get('channels', []):
                return True
            
            # Verifica roles
            user_role_ids = {str(role.id) for role in message.author.roles}
            whitelisted_roles = set(whitelist.get('roles', []))
            
            return bool(user_role_ids & whitelisted_roles)
        except Exception as e:
            LOGGER.error(f"Erro ao verificar whitelist: {e}")
            return False
    
    async def _check_spam(
        self, message: discord.Message, config: dict
    ) -> Optional[str]:
        """Verifica spam de mensagens idênticas."""
        try:
            is_spam, count = self.detector.check_spam(
                message.guild.id,
                message.author.id,
                config.get('spam_threshold', 5),
                config.get('spam_window_seconds', 10)
            )
            
            if is_spam:
                return f"Spam detectado: {count} mensagens idênticas"
            return None
        except Exception as e:
            LOGGER.error(f"Erro em _check_spam: {e}")
            return None
    
    async def _check_similarity(
        self, message: discord.Message, config: dict
    ) -> Optional[str]:
        """Verifica mensagens similares (bypass de spam)."""
        try:
            is_similar, ratio = self.detector.check_similarity(
                message.guild.id,
                message.author.id,
                message.content,
                config.get('similarity_threshold', 0.85)
            )
            
            if is_similar:
                return f"Mensagens similares detectadas ({ratio:.0%})"
            return None
        except Exception as e:
            LOGGER.error(f"Erro em _check_similarity: {e}")
            return None
    
    async def _check_mentions(
        self, message: discord.Message, config: dict
    ) -> Optional[str]:
        """Verifica flood de menções."""
        try:
            mention_limit = config.get('mention_limit', 5)
            total_mentions = len(message.mentions) + len(message.role_mentions)
            
            if total_mentions > mention_limit:
                return f"Flood de menções: {total_mentions} menções"
            return None
        except Exception as e:
            LOGGER.error(f"Erro em _check_mentions: {e}")
            return None
    
    async def _check_links(
        self, message: discord.Message, config: dict
    ) -> Optional[str]:
        """Verifica links suspeitos."""
        try:
            if not config.get('filter_invites'):
                return None
            
            content_lower = message.content.lower()
            
            # Verifica convites de Discord
            if 'discord.gg/' in content_lower or 'discord.com/invite/' in content_lower:
                return "Convite de Discord não autorizado"
            
            return None
        except Exception as e:
            LOGGER.error(f"Erro em _check_links: {e}")
            return None
    
    async def _handle_violation(
        self,
        message: discord.Message,
        violation: str,
        config: dict
    ):
        """Aplica punição graduada baseada nas violações."""
        try:
            # Deleta mensagem
            try:
                await message.delete()
            except discord.Forbidden:
                LOGGER.warning(f"Sem permissão para deletar mensagem em {message.guild.id}")
            except discord.NotFound:
                pass  # Mensagem já deletada
            
            # Conta violações
            key = (message.guild.id, message.author.id)
            if key not in self._violation_counts:
                self._violation_counts[key] = (0, datetime.utcnow())
            
            count, _ = self._violation_counts[key]
            count += 1
            self._violation_counts[key] = (count, datetime.utcnow())
            
            # Busca canal de logs
            logs_channel = None
            logs_channel_id = config.get('logs_channel_id')
            if logs_channel_id:
                logs_channel = message.guild.get_channel(int(logs_channel_id))
            
            # Aplica ação baseada no número de violações
            member = message.author
            
            if count == 1:
                action = config.get('first_action', 'warn')
            elif count == 2:
                action = config.get('second_action', 'timeout')
            else:
                action = config.get('third_action', 'ban')
            
            # Registra no banco de forma não-bloqueante (fire-and-forget)
            asyncio.create_task(
                self.db.add_automod_violation(
                    str(message.guild.id),
                    str(message.author.id),
                    violation,
                    message.content[:200],
                    action
                )
            )
            
            # Executa ação
            if action == 'warn':
                await AutomodActions.warn_user(member, violation, logs_channel)
            elif action == 'timeout':
                duration = config.get('timeout_duration', 600)
                await AutomodActions.timeout_user(member, duration, violation, logs_channel)
            elif action == 'ban':
                await AutomodActions.ban_user(member, violation, logs_channel)
        except Exception as e:
            LOGGER.error(f"Erro em _handle_violation: {e}", exc_info=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutomodCog(bot, bot.db))
