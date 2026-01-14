"""Repository Pattern para abstrair acesso ao banco de dados de hierarquia."""

import logging
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime

from db import Database
from .models import HierarchyConfig, PromotionRequest, HierarchyUserStatus
from .cache import HierarchyCache

LOGGER = logging.getLogger(__name__)


class HierarchyRepository:
    """Repository que abstrai acesso ao banco de dados de hierarquia."""
    
    def __init__(self, db: Database, cache: Optional[HierarchyCache] = None):
        """
        Inicializa o repository.
        
        Args:
            db: Instância do Database
            cache: Instância do HierarchyCache (opcional)
        """
        self.db = db
        self.cache = cache or HierarchyCache()
    
    # ===== MÉTODOS DE CONFIGURAÇÃO =====
    
    async def get_config(
        self, guild_id: int, role_id: int
    ) -> Optional[HierarchyConfig]:
        """
        Busca configuração de cargo (com cache).
        
        Args:
            guild_id: ID do servidor
            role_id: ID do cargo
            
        Returns:
            HierarchyConfig se encontrado, None caso contrário
        """
        # Verifica cache primeiro
        cached = self.cache.get_config(guild_id, role_id)
        if cached:
            return cached
        
        # Busca do banco
        data = await self.db.get_hierarchy_config(guild_id, role_id)
        if not data:
            return None
        
        # Converte para model
        config = HierarchyConfig.from_dict(data)
        
        # Busca requisitos e canais relacionados
        req_roles = await self.db.get_hierarchy_role_requirements(guild_id, role_id)
        config.req_other_roles = list(req_roles)
        
        channels = await self.db.get_hierarchy_channel_access(guild_id, role_id)
        config.channel_access = list(channels)
        
        # Armazena no cache
        self.cache.set_config(guild_id, role_id, config)
        
        return config
    
    async def get_all_configs(
        self, guild_id: int, order_by: str = 'level_order'
    ) -> List[HierarchyConfig]:
        """
        Lista todas as configurações de hierarquia do servidor.
        
        Args:
            guild_id: ID do servidor
            order_by: Campo para ordenação (padrão: 'level_order')
            
        Returns:
            Lista de HierarchyConfig
        """
        rows = await self.db.get_all_hierarchy_roles(guild_id, order_by)
        configs = []
        
        for row in rows:
            config = HierarchyConfig.from_dict(row)
            # Busca requisitos e canais
            req_roles = await self.db.get_hierarchy_role_requirements(
                guild_id, config.role_id
            )
            config.req_other_roles = list(req_roles)
            
            channels = await self.db.get_hierarchy_channel_access(
                guild_id, config.role_id
            )
            config.channel_access = list(channels)
            
            configs.append(config)
        
        return configs
    
    async def upsert_config(self, config: HierarchyConfig) -> None:
        """
        Cria ou atualiza configuração (transação atômica).
        
        Args:
            config: Configuração a ser salva
        """
        # Salva configuração principal
        await self.db.upsert_hierarchy_config(
            config.guild_id,
            config.role_id,
            config.role_name,
            config.level_order,
            config.role_color,
            config.max_vacancies,
            config.is_admin_rank,
            config.auto_promote,
            config.requires_approval,
            config.expiry_days,
            config.req_messages,
            config.req_call_time,
            config.req_reactions,
            config.req_min_days,
            config.min_days_in_role,
            config.req_min_any,
            config.auto_demote_on_lose_req,
            config.auto_demote_inactive_days,
            config.vacancy_priority,
            config.check_frequency_hours
        )
        
        # Remove requisitos antigos e adiciona novos
        existing_req = await self.db.get_hierarchy_role_requirements(
            config.guild_id, config.role_id
        )
        for req_role_id in existing_req:
            if req_role_id not in config.req_other_roles:
                await self.db.remove_hierarchy_role_requirement(
                    config.guild_id, config.role_id, req_role_id
                )
        
        for req_role_id in config.req_other_roles:
            if req_role_id not in existing_req:
                await self.db.add_hierarchy_role_requirement(
                    config.guild_id, config.role_id, req_role_id
                )
        
        # Remove canais antigos e adiciona novos
        existing_channels = await self.db.get_hierarchy_channel_access(
            config.guild_id, config.role_id
        )
        for channel_id in existing_channels:
            if channel_id not in config.channel_access:
                await self.db.remove_hierarchy_channel_access(
                    config.guild_id, config.role_id, channel_id
                )
        
        for channel_id in config.channel_access:
            if channel_id not in existing_channels:
                await self.db.add_hierarchy_channel_access(
                    config.guild_id, config.role_id, channel_id
                )
        
        # Invalida cache
        self.cache.invalidate_config(config.guild_id, config.role_id)
    
    async def delete_config(self, guild_id: int, role_id: int) -> None:
        """
        Remove configuração (CASCADE nas tabelas relacionadas).
        
        Args:
            guild_id: ID do servidor
            role_id: ID do cargo
        """
        await self.db.delete_hierarchy_config(guild_id, role_id)
        # Invalida cache
        self.cache.invalidate_config(guild_id, role_id)
    
    async def get_config_by_level(
        self, guild_id: int, level_order: int
    ) -> Optional[HierarchyConfig]:
        """
        Busca configuração por nível hierárquico.
        
        Args:
            guild_id: ID do servidor
            level_order: Nível hierárquico
            
        Returns:
            HierarchyConfig se encontrado, None caso contrário
        """
        data = await self.db.get_hierarchy_role_by_level(guild_id, level_order)
        if not data:
            return None
        
        config = HierarchyConfig.from_dict(data)
        # Busca requisitos e canais
        req_roles = await self.db.get_hierarchy_role_requirements(
            guild_id, config.role_id
        )
        config.req_other_roles = list(req_roles)
        
        channels = await self.db.get_hierarchy_channel_access(
            guild_id, config.role_id
        )
        config.channel_access = list(channels)
        
        return config
    
    # ===== MÉTODOS DE PROMOÇÕES =====
    
    async def create_promotion_request(
        self,
        guild_id: int,
        user_id: int,
        target_role_id: int,
        request_type: str = 'auto',
        current_role_id: Optional[int] = None,
        requested_by: Optional[int] = None,
        reason: Optional[str] = None,
        message_id: Optional[int] = None
    ) -> int:
        """
        Cria pedido de promoção.
        
        Args:
            guild_id: ID do servidor
            user_id: ID do usuário
            target_role_id: ID do cargo alvo
            request_type: Tipo de pedido ('auto' ou 'manual')
            current_role_id: ID do cargo atual (opcional)
            requested_by: ID de quem solicitou (opcional)
            reason: Motivo (opcional)
            message_id: ID da mensagem de aprovação (opcional)
            
        Returns:
            ID do pedido criado
        """
        return await self.db.create_promotion_request(
            guild_id, user_id, target_role_id, request_type,
            current_role_id, requested_by, reason, message_id
        )
    
    async def get_pending_requests(
        self, guild_id: int, user_id: Optional[int] = None
    ) -> List[PromotionRequest]:
        """
        Busca pedidos pendentes.
        
        Args:
            guild_id: ID do servidor
            user_id: ID do usuário (opcional, para filtrar)
            
        Returns:
            Lista de PromotionRequest
        """
        rows = await self.db.get_pending_promotion_requests(guild_id, user_id)
        return [PromotionRequest.from_dict(row) for row in rows]
    
    async def resolve_request(
        self, request_id: int, status: str, resolved_by: int
    ) -> None:
        """
        Resolve pedido de promoção.
        
        Args:
            request_id: ID do pedido
            status: Status final ('approved' ou 'rejected')
            resolved_by: ID de quem resolveu
        """
        await self.db.resolve_promotion_request(request_id, status, resolved_by)
    
    # ===== MÉTODOS DE STATUS DE USUÁRIO =====
    
    async def get_user_status(
        self, guild_id: int, user_id: int
    ) -> Optional[HierarchyUserStatus]:
        """
        Busca status do usuário (com cache).
        
        Args:
            guild_id: ID do servidor
            user_id: ID do usuário
            
        Returns:
            HierarchyUserStatus se encontrado, None caso contrário
        """
        # Verifica cache primeiro
        cached = self.cache.get_user_status(guild_id, user_id)
        if cached:
            return cached
        
        # Busca do banco
        data = await self.db.get_user_hierarchy_status(guild_id, user_id)
        if not data:
            return None
        
        status = HierarchyUserStatus.from_dict(data)
        # Armazena no cache
        self.cache.set_user_status(guild_id, user_id, status)
        
        return status
    
    async def update_user_status(
        self,
        guild_id: int,
        user_id: int,
        current_role_id: Optional[int] = None,
        promoted_at: Optional[str] = None,
        last_promotion_check: Optional[str] = None,
        ignore_auto_promote_until: Optional[str] = None,
        ignore_auto_demote_until: Optional[str] = None,
        promotion_cooldown_until: Optional[str] = None,
        expiry_date: Optional[str] = None
    ) -> None:
        """
        Atualiza status do usuário (transação atômica).
        
        Args:
            guild_id: ID do servidor
            user_id: ID do usuário
            current_role_id: ID do cargo atual (opcional)
            promoted_at: Data da promoção (opcional)
            last_promotion_check: Data da última verificação (opcional)
            ignore_auto_promote_until: Ignorar promoção até (opcional)
            ignore_auto_demote_until: Ignorar rebaixamento até (opcional)
            promotion_cooldown_until: Cooldown de promoção até (opcional)
            expiry_date: Data de expiração (opcional)
        """
        await self.db.update_user_hierarchy_status(
            guild_id, user_id, current_role_id, promoted_at,
            last_promotion_check, ignore_auto_promote_until,
            ignore_auto_demote_until, promotion_cooldown_until, expiry_date
        )
        # Invalida cache
        self.cache.invalidate_user_status(guild_id, user_id)
    
    # ===== MÉTODOS DE HISTÓRICO =====
    
    async def add_history(
        self,
        guild_id: int,
        user_id: int,
        action_type: str,
        to_role_id: int,
        from_role_id: Optional[int] = None,
        reason: Optional[str] = None,
        performed_by: Optional[int] = None,
        detailed_reason: Optional[str] = None
    ) -> int:
        """
        Adiciona entrada ao histórico.
        
        Args:
            guild_id: ID do servidor
            user_id: ID do usuário
            action_type: Tipo de ação ('promotion', 'demotion', etc.)
            to_role_id: ID do cargo alvo
            from_role_id: ID do cargo anterior (opcional)
            reason: Motivo (opcional)
            performed_by: ID de quem executou (opcional)
            detailed_reason: Razão detalhada (opcional)
            
        Returns:
            ID da entrada criada
        """
        return await self.db.add_hierarchy_history(
            guild_id, user_id, action_type, to_role_id,
            from_role_id, reason, performed_by, detailed_reason
        )
    
    async def get_user_history(
        self, guild_id: int, user_id: int, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Busca histórico do usuário.
        
        Args:
            guild_id: ID do servidor
            user_id: ID do usuário
            limit: Limite de resultados (padrão: 50)
            
        Returns:
            Lista de entradas de histórico
        """
        return list(await self.db.get_user_hierarchy_history(guild_id, user_id, limit))
    
    # ===== MÉTODOS DE RATE LIMITING =====
    
    async def track_rate_limit(self, guild_id: int, action_type: str) -> None:
        """
        Registra ação para rate limiting.
        
        Args:
            guild_id: ID do servidor
            action_type: Tipo de ação ('role_create', 'role_edit', etc.)
        """
        await self.db.track_rate_limit_action(guild_id, action_type)
    
    async def get_rate_limit_count(
        self, guild_id: int, action_type: str, hours: int = 48
    ) -> int:
        """
        Conta ações nas últimas N horas.
        
        Args:
            guild_id: ID do servidor
            action_type: Tipo de ação
            hours: Horas para contar (padrão: 48)
            
        Returns:
            Número de ações
        """
        return await self.db.get_rate_limit_count(guild_id, action_type, hours)
    
    # ===== MÉTODOS DE VERIFICAÇÃO =====
    
    async def get_eligible_users(
        self, guild_id: int, role_id: int
    ) -> List[Dict[str, Any]]:
        """
        Lista usuários elegíveis para promoção (otimizado).
        
        Args:
            guild_id: ID do servidor
            role_id: ID do cargo alvo
            
        Returns:
            Lista de usuários elegíveis
        """
        return list(await self.db.get_users_eligible_for_promotion(guild_id, role_id))
