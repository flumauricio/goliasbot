"""Modelos de dados para o sistema de hierarquia usando dataclasses."""

from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class HierarchyConfig:
    """Modelo de configuração de cargo na hierarquia."""
    guild_id: int
    role_id: int
    role_name: str
    level_order: int
    role_color: Optional[str] = None
    max_vacancies: int = 0
    is_admin_rank: bool = False
    auto_promote: bool = True
    requires_approval: bool = False
    expiry_days: int = 0
    req_messages: int = 0
    req_call_time: int = 0
    req_reactions: int = 0
    req_min_days: int = 0
    min_days_in_role: int = 0
    req_min_any: int = 1
    auto_demote_on_lose_req: bool = False
    auto_demote_inactive_days: int = 0
    vacancy_priority: str = 'first_qualify'
    check_frequency_hours: int = 24
    req_other_roles: List[int] = field(default_factory=list)
    channel_access: List[int] = field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> 'HierarchyConfig':
        """Cria instância a partir de dicionário do banco."""
        # Converte strings para int onde necessário
        config = cls(
            guild_id=int(data['guild_id']),
            role_id=int(data['role_id']),
            role_name=data['role_name'],
            level_order=int(data['level_order']),
            role_color=data.get('role_color'),
            max_vacancies=int(data.get('max_vacancies', 0)),
            is_admin_rank=bool(data.get('is_admin_rank', 0)),
            auto_promote=bool(data.get('auto_promote', 1)),
            requires_approval=bool(data.get('requires_approval', 0)),
            expiry_days=int(data.get('expiry_days', 0)),
            req_messages=int(data.get('req_messages', 0)),
            req_call_time=int(data.get('req_call_time', 0)),
            req_reactions=int(data.get('req_reactions', 0)),
            req_min_days=int(data.get('req_min_days', 0)),
            min_days_in_role=int(data.get('min_days_in_role', 0)),
            req_min_any=int(data.get('req_min_any', 1)),
            auto_demote_on_lose_req=bool(data.get('auto_demote_on_lose_req', 0)),
            auto_demote_inactive_days=int(data.get('auto_demote_inactive_days', 0)),
            vacancy_priority=data.get('vacancy_priority', 'first_qualify'),
            check_frequency_hours=int(data.get('check_frequency_hours', 24)),
            req_other_roles=[],  # Será preenchido separadamente
            channel_access=[]  # Será preenchido separadamente
        )
        return config
    
    def to_dict(self) -> dict:
        """Converte para dicionário para salvar no banco."""
        return {
            'guild_id': str(self.guild_id),
            'role_id': str(self.role_id),
            'role_name': self.role_name,
            'level_order': self.level_order,
            'role_color': self.role_color,
            'max_vacancies': self.max_vacancies,
            'is_admin_rank': int(self.is_admin_rank),
            'auto_promote': int(self.auto_promote),
            'requires_approval': int(self.requires_approval),
            'expiry_days': self.expiry_days,
            'req_messages': self.req_messages,
            'req_call_time': self.req_call_time,
            'req_reactions': self.req_reactions,
            'req_min_days': self.req_min_days,
            'min_days_in_role': self.min_days_in_role,
            'req_min_any': self.req_min_any,
            'auto_demote_on_lose_req': int(self.auto_demote_on_lose_req),
            'auto_demote_inactive_days': self.auto_demote_inactive_days,
            'vacancy_priority': self.vacancy_priority,
            'check_frequency_hours': self.check_frequency_hours
        }


@dataclass
class PromotionRequest:
    """Modelo de pedido de promoção."""
    id: Optional[int] = None
    guild_id: int = 0
    user_id: int = 0
    current_role_id: Optional[int] = None
    target_role_id: int = 0
    request_type: str = 'auto'
    requested_by: Optional[int] = None
    reason: Optional[str] = None
    status: str = 'pending'
    message_id: Optional[int] = None
    created_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[int] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> 'PromotionRequest':
        """Cria instância a partir de dicionário do banco."""
        return cls(
            id=int(data['id']) if data.get('id') else None,
            guild_id=int(data['guild_id']),
            user_id=int(data['user_id']),
            current_role_id=int(data['current_role_id']) if data.get('current_role_id') else None,
            target_role_id=int(data['target_role_id']),
            request_type=data.get('request_type', 'auto'),
            requested_by=int(data['requested_by']) if data.get('requested_by') else None,
            reason=data.get('reason'),
            status=data.get('status', 'pending'),
            message_id=int(data['message_id']) if data.get('message_id') else None,
            created_at=data.get('created_at'),
            resolved_at=data.get('resolved_at'),
            resolved_by=int(data['resolved_by']) if data.get('resolved_by') else None
        )


@dataclass
class HierarchyUserStatus:
    """Modelo de status do usuário na hierarquia."""
    guild_id: int
    user_id: int
    current_role_id: Optional[int] = None
    promoted_at: Optional[datetime] = None
    last_promotion_check: Optional[datetime] = None
    ignore_auto_promote_until: Optional[datetime] = None
    ignore_auto_demote_until: Optional[datetime] = None
    promotion_cooldown_until: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    
    @classmethod
    def from_dict(cls, data: dict) -> 'HierarchyUserStatus':
        """Cria instância a partir de dicionário do banco."""
        # Proteção contra None ou valores inválidos (evita int(None))
        guild_id = data.get('guild_id')
        user_id = data.get('user_id')
        
        if not guild_id or not user_id:
            raise ValueError(f"guild_id e user_id são obrigatórios. Recebido: guild_id={guild_id}, user_id={user_id}")
        
        # Função auxiliar para converter string para datetime
        def parse_datetime(value):
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                try:
                    # Formato: "YYYY-MM-DD HH:MM:SS"
                    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    try:
                        # Tenta formato ISO se o formato acima falhar
                        return datetime.fromisoformat(value.replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        return None
            return None
        
        return cls(
            guild_id=int(guild_id) if isinstance(guild_id, (int, str)) else 0,
            user_id=int(user_id) if isinstance(user_id, (int, str)) else 0,
            current_role_id=int(data['current_role_id']) if data.get('current_role_id') and str(data.get('current_role_id')).isdigit() else None,
            promoted_at=parse_datetime(data.get('promoted_at')),
            last_promotion_check=parse_datetime(data.get('last_promotion_check')),
            ignore_auto_promote_until=parse_datetime(data.get('ignore_auto_promote_until')),
            ignore_auto_demote_until=parse_datetime(data.get('ignore_auto_demote_until')),
            promotion_cooldown_until=parse_datetime(data.get('promotion_cooldown_until')),
            expiry_date=parse_datetime(data.get('expiry_date'))
        )
