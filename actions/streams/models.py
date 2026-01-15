"""
Stream Models - Dataclasses para o sistema de notificações de live.

Features:
- Platform enum (Twitch/YouTube)
- StreamInfo dataclass
- AnnouncementData dataclass
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum


class Platform(Enum):
    """Plataformas de streaming suportadas."""
    TWITCH = "twitch"
    YOUTUBE = "youtube"


@dataclass
class StreamInfo:
    """Informações de uma live."""
    platform: Platform
    channel_name: str
    title: str
    thumbnail_url: str
    viewer_count: int
    started_at: datetime
    stream_url: str


@dataclass
class AnnouncementData:
    """Dados de um anúncio de live."""
    message_id: int
    stream_info: StreamInfo
    announced_at: datetime
    peak_viewers: int = 0
    last_updated: Optional[datetime] = None  # Controle de rate limiting
