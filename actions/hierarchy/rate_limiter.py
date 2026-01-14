"""Rate Limiter Inteligente para gerenciar limites do Discord (250 cargos/48h)."""

import logging
from typing import Tuple, Optional
from datetime import datetime, timedelta

from db import Database

LOGGER = logging.getLogger(__name__)


class HierarchyRateLimiter:
    """Gerencia rate limits do Discord para operações de hierarquia."""
    
    # Limites do Discord
    MAX_ROLE_CREATES_48H = 250
    MAX_ROLE_EDITS_48H = 250
    MAX_PERMISSION_EDITS_48H = 250
    
    def __init__(self, db: Database):
        """
        Inicializa o rate limiter.
        
        Args:
            db: Instância do Database
        """
        self.db = db
    
    async def can_create_role(self, guild_id: int) -> Tuple[bool, int, int]:
        """
        Verifica se pode criar cargo.
        
        Args:
            guild_id: ID do servidor
            
        Returns:
            Tupla (pode_criar, ações_48h, limite_restante)
        """
        count_48h = await self.db.get_rate_limit_count(guild_id, 'role_create', hours=48)
        can_create = count_48h < self.MAX_ROLE_CREATES_48H
        remaining = max(0, self.MAX_ROLE_CREATES_48H - count_48h)
        return can_create, count_48h, remaining
    
    async def can_edit_role(self, guild_id: int) -> Tuple[bool, int, int]:
        """
        Verifica se pode editar cargo.
        
        Args:
            guild_id: ID do servidor
            
        Returns:
            Tupla (pode_editar, ações_48h, limite_restante)
        """
        count_48h = await self.db.get_rate_limit_count(guild_id, 'role_edit', hours=48)
        can_edit = count_48h < self.MAX_ROLE_EDITS_48H
        remaining = max(0, self.MAX_ROLE_EDITS_48H - count_48h)
        return can_edit, count_48h, remaining
    
    async def can_edit_permission(self, guild_id: int) -> Tuple[bool, int, int]:
        """
        Verifica se pode editar permissão de canal.
        
        Args:
            guild_id: ID do servidor
            
        Returns:
            Tupla (pode_editar, ações_48h, limite_restante)
        """
        count_48h = await self.db.get_rate_limit_count(guild_id, 'permission_edit', hours=48)
        can_edit = count_48h < self.MAX_PERMISSION_EDITS_48H
        remaining = max(0, self.MAX_PERMISSION_EDITS_48H - count_48h)
        return can_edit, count_48h, remaining
    
    async def get_adaptive_delay(self, guild_id: int, action_type: str) -> float:
        """
        Retorna delay adaptativo baseado em ações recentes.
        
        Args:
            guild_id: ID do servidor
            action_type: Tipo de ação ('role_create', 'role_edit', 'permission_edit')
            
        Returns:
            Delay em segundos
        """
        count_48h = await self.db.get_rate_limit_count(guild_id, action_type, hours=48)
        
        if count_48h < 50:
            return 1.5
        elif count_48h < 150:
            return 2.5
        elif count_48h < 200:
            return 5.0
        else:
            return 10.0
    
    async def track_action(self, guild_id: int, action_type: str) -> None:
        """
        Registra ação para tracking.
        
        Args:
            guild_id: ID do servidor
            action_type: Tipo de ação
        """
        await self.db.track_rate_limit_action(guild_id, action_type)
    
    async def get_status_message(self, guild_id: int, action_type: str) -> str:
        """
        Retorna mensagem de status do rate limit.
        
        Args:
            guild_id: ID do servidor
            action_type: Tipo de ação
            
        Returns:
            Mensagem formatada
        """
        count_48h = await self.db.get_rate_limit_count(guild_id, action_type, hours=48)
        
        if action_type == 'role_create':
            limit = self.MAX_ROLE_CREATES_48H
        elif action_type == 'role_edit':
            limit = self.MAX_ROLE_EDITS_48H
        else:  # permission_edit
            limit = self.MAX_PERMISSION_EDITS_48H
        
        percentage = (count_48h / limit) * 100
        
        if percentage < 50:
            status_emoji = "🟢"
        elif percentage < 80:
            status_emoji = "🟡"
        else:
            status_emoji = "🔴"
        
        return f"{status_emoji} {count_48h}/{limit} ações nas últimas 48h ({percentage:.1f}%)"
