"""Cache inteligente em memória com TTL para o sistema de hierarquia."""

import logging
from typing import Dict, Optional, Tuple, Any
from datetime import datetime, timedelta

from .models import HierarchyConfig, HierarchyUserStatus

LOGGER = logging.getLogger(__name__)


class HierarchyCache:
    """Cache em memória com TTL e invalidação automática."""
    
    def __init__(self, default_ttl_minutes: int = 5):
        """
        Inicializa o cache.
        
        Args:
            default_ttl_minutes: TTL padrão em minutos (padrão: 5)
        """
        self._config_cache: Dict[Tuple[int, int], Tuple[HierarchyConfig, datetime]] = {}
        self._user_status_cache: Dict[Tuple[int, int], Tuple[HierarchyUserStatus, datetime]] = {}
        self._ttl = timedelta(minutes=default_ttl_minutes)
        self._hits = 0
        self._misses = 0
    
    def get_config(self, guild_id: int, role_id: int) -> Optional[HierarchyConfig]:
        """
        Busca configuração de cargo no cache.
        
        Args:
            guild_id: ID do servidor
            role_id: ID do cargo
            
        Returns:
            HierarchyConfig se encontrado e válido, None caso contrário
        """
        key = (guild_id, role_id)
        if key in self._config_cache:
            config, expiry = self._config_cache[key]
            if datetime.utcnow() < expiry:
                self._hits += 1
                return config
            else:
                # Expirou, remove do cache
                del self._config_cache[key]
        
        self._misses += 1
        return None
    
    def set_config(self, guild_id: int, role_id: int, config: HierarchyConfig) -> None:
        """
        Armazena configuração de cargo no cache.
        
        Args:
            guild_id: ID do servidor
            role_id: ID do cargo
            config: Configuração a ser armazenada
        """
        key = (guild_id, role_id)
        expiry = datetime.utcnow() + self._ttl
        self._config_cache[key] = (config, expiry)
    
    def invalidate_config(self, guild_id: int, role_id: Optional[int] = None) -> None:
        """
        Invalida cache de configuração.
        
        Args:
            guild_id: ID do servidor
            role_id: ID do cargo (None para invalidar todos do servidor)
        """
        if role_id:
            self._config_cache.pop((guild_id, role_id), None)
        else:
            # Invalidar todos os cargos do servidor
            keys_to_remove = [k for k in self._config_cache.keys() if k[0] == guild_id]
            for key in keys_to_remove:
                del self._config_cache[key]
    
    def get_user_status(self, guild_id: int, user_id: int) -> Optional[HierarchyUserStatus]:
        """
        Busca status do usuário no cache.
        
        Args:
            guild_id: ID do servidor
            user_id: ID do usuário
            
        Returns:
            HierarchyUserStatus se encontrado e válido, None caso contrário
        """
        key = (guild_id, user_id)
        if key in self._user_status_cache:
            status, expiry = self._user_status_cache[key]
            if datetime.utcnow() < expiry:
                self._hits += 1
                return status
            else:
                # Expirou, remove do cache
                del self._user_status_cache[key]
        
        self._misses += 1
        return None
    
    def set_user_status(self, guild_id: int, user_id: int, status: HierarchyUserStatus) -> None:
        """
        Armazena status do usuário no cache.
        
        Args:
            guild_id: ID do servidor
            user_id: ID do usuário
            status: Status a ser armazenado
        """
        key = (guild_id, user_id)
        expiry = datetime.utcnow() + self._ttl
        self._user_status_cache[key] = (status, expiry)
    
    def invalidate_user_status(self, guild_id: int, user_id: Optional[int] = None) -> None:
        """
        Invalida cache de status do usuário.
        
        Args:
            guild_id: ID do servidor
            user_id: ID do usuário (None para invalidar todos do servidor)
        """
        if user_id:
            self._user_status_cache.pop((guild_id, user_id), None)
        else:
            # Invalidar todos os usuários do servidor
            keys_to_remove = [k for k in self._user_status_cache.keys() if k[0] == guild_id]
            for key in keys_to_remove:
                del self._user_status_cache[key]
    
    def clear(self) -> None:
        """Limpa todo o cache."""
        self._config_cache.clear()
        self._user_status_cache.clear()
        self._hits = 0
        self._misses = 0
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Retorna estatísticas do cache.
        
        Returns:
            Dicionário com estatísticas (hits, misses, hit_rate, size)
        """
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0.0
        
        return {
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': round(hit_rate, 2),
            'config_cache_size': len(self._config_cache),
            'user_status_cache_size': len(self._user_status_cache)
        }
    
    def cleanup_expired(self) -> int:
        """
        Remove entradas expiradas do cache.
        
        Returns:
            Número de entradas removidas
        """
        now = datetime.utcnow()
        removed = 0
        
        # Limpa config_cache
        keys_to_remove = [
            k for k, (_, expiry) in self._config_cache.items()
            if now >= expiry
        ]
        for key in keys_to_remove:
            del self._config_cache[key]
            removed += 1
        
        # Limpa user_status_cache
        keys_to_remove = [
            k for k, (_, expiry) in self._user_status_cache.items()
            if now >= expiry
        ]
        for key in keys_to_remove:
            del self._user_status_cache[key]
            removed += 1
        
        return removed
