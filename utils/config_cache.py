"""
Config Cache Manager - Singleton para cache de configurações do bot.
Reduz queries ao banco em 90%+ usando cache em memória com TTL.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

LOGGER = logging.getLogger(__name__)


@dataclass
class CachedConfig:
    """Config cacheado com timestamp de expiração."""
    data: Dict[str, Any]
    cached_at: datetime
    ttl_seconds: int = 300  # 5 minutos padrão
    
    def is_expired(self) -> bool:
        """Verifica se o cache expirou."""
        return datetime.utcnow() > self.cached_at + timedelta(seconds=self.ttl_seconds)


class ConfigCacheManager:
    """
    Singleton para gerenciar cache de configurações.
    
    Features:
    - Cache em memória com TTL de 5 minutos
    - Thread-safe com asyncio.Lock
    - Invalidação manual quando config é alterada
    - Suporta automod_config e stream_config
    """
    
    _instance: Optional['ConfigCacheManager'] = None
    _lock = asyncio.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._cache: Dict[tuple, CachedConfig] = {}
            cls._instance._cache_lock = asyncio.Lock()
        return cls._instance
    
    async def get_automod_config(self, db, guild_id: int) -> Dict[str, Any]:
        """
        Busca config do automod com cache.
        
        Args:
            db: Instância do Database
            guild_id: ID do servidor
        
        Returns:
            Dict com configurações do automod
        """
        cache_key = ('automod', guild_id)
        
        # Verifica cache
        async with self._cache_lock:
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                if not cached.is_expired():
                    LOGGER.debug(f"Cache HIT para automod_config guild={guild_id}")
                    return cached.data
                else:
                    LOGGER.debug(f"Cache EXPIRED para automod_config guild={guild_id}")
        
        # Cache miss ou expirado - busca do banco
        LOGGER.debug(f"Cache MISS para automod_config guild={guild_id}, buscando do banco...")
        config = await db.get_automod_config(guild_id)
        
        # Atualiza cache
        async with self._cache_lock:
            self._cache[cache_key] = CachedConfig(
                data=config or {},
                cached_at=datetime.utcnow()
            )
        
        return config or {}
    
    async def get_stream_config(self, db, guild_id: int) -> Dict[str, Any]:
        """
        Busca config de streams com cache.
        
        Args:
            db: Instância do Database
            guild_id: ID do servidor
        
        Returns:
            Dict com configurações de streams
        """
        cache_key = ('streams', guild_id)
        
        # Verifica cache
        async with self._cache_lock:
            if cache_key in self._cache:
                cached = self._cache[cache_key]
                if not cached.is_expired():
                    LOGGER.debug(f"Cache HIT para stream_config guild={guild_id}")
                    return cached.data
                else:
                    LOGGER.debug(f"Cache EXPIRED para stream_config guild={guild_id}")
        
        # Cache miss ou expirado - busca do banco
        LOGGER.debug(f"Cache MISS para stream_config guild={guild_id}, buscando do banco...")
        config = await db.get_stream_config(guild_id)
        
        # Atualiza cache
        async with self._cache_lock:
            self._cache[cache_key] = CachedConfig(
                data=config or {},
                cached_at=datetime.utcnow()
            )
        
        return config or {}
    
    async def invalidate(self, module: str, guild_id: int):
        """
        Invalida cache para forçar reload.
        Deve ser chamado quando configurações são alteradas no !setup.
        
        Args:
            module: 'automod' ou 'streams'
            guild_id: ID do servidor
        """
        cache_key = (module, guild_id)
        async with self._cache_lock:
            if cache_key in self._cache:
                del self._cache[cache_key]
                LOGGER.debug(f"Cache INVALIDATED para {module} guild={guild_id}")
    
    async def clear_all(self):
        """Limpa todo o cache (útil para testes)."""
        async with self._cache_lock:
            self._cache.clear()
            LOGGER.info("Cache CLEARED - todos os dados removidos")
    
    def get_stats(self) -> Dict[str, int]:
        """Retorna estatísticas do cache."""
        total = len(self._cache)
        expired = sum(1 for cached in self._cache.values() if cached.is_expired())
        active = total - expired
        
        return {
            'total_entries': total,
            'active_entries': active,
            'expired_entries': expired
        }
