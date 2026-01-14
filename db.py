import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import aiosqlite


LOGGER = logging.getLogger(__name__)


class Database:
    """Wrapper assíncrono para SQLite com migração inicial usando aiosqlite."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """Inicializa a conexão e executa migrações. Deve ser chamado antes de usar o banco."""
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self.migrate()

    async def migrate(self) -> None:
        """Executa as migrações do banco de dados."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            await cur.execute(
            """
            CREATE TABLE IF NOT EXISTS registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                user_name TEXT NOT NULL,
                server_id TEXT NOT NULL,
                recruiter_id TEXT NOT NULL,
                status TEXT NOT NULL,
                approval_message_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
            )
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    guild_id TEXT PRIMARY KEY,
                    channel_registration_embed TEXT,
                    channel_welcome TEXT,
                    channel_warnings TEXT,
                    channel_leaves TEXT,
                    channel_approval TEXT,
                    channel_records TEXT,
                    role_set TEXT,
                    role_member TEXT,
                    role_adv1 TEXT,
                    role_adv2 TEXT,
                    message_set_embed TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            # Migrações leves para colunas que podem faltar
            await cur.execute("PRAGMA table_info(settings)")
            rows = await cur.fetchall()
            cols = [row[1] for row in rows]
            if "channel_welcome" not in cols:
                await cur.execute("ALTER TABLE settings ADD COLUMN channel_welcome TEXT")
            if "channel_warnings" not in cols:
                await cur.execute("ALTER TABLE settings ADD COLUMN channel_warnings TEXT")
            if "channel_leaves" not in cols:
                await cur.execute("ALTER TABLE settings ADD COLUMN channel_leaves TEXT")
            if "role_adv1" not in cols:
                await cur.execute("ALTER TABLE settings ADD COLUMN role_adv1 TEXT")
            if "role_adv2" not in cols:
                await cur.execute("ALTER TABLE settings ADD COLUMN role_adv2 TEXT")
            if "channel_naval" not in cols:
                await cur.execute("ALTER TABLE settings ADD COLUMN channel_naval TEXT")
            if "analytics_ignored_channels" not in cols:
                await cur.execute("ALTER TABLE settings ADD COLUMN analytics_ignored_channels TEXT")


            # Permissões de comandos por guild
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS command_permissions (
                    guild_id TEXT NOT NULL,
                    command_name TEXT NOT NULL,
                    role_ids TEXT NOT NULL,
                    PRIMARY KEY (guild_id, command_name)
                )
                """
            )

            # Tabela para mapear server_id -> discord_id (otimização para busca de membros)
            # Tabela para mapear server_id -> discord_id (otimização para busca de membros)
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS member_server_ids (
                    guild_id TEXT NOT NULL,
                    discord_id TEXT NOT NULL,
                    server_id TEXT NOT NULL,
                    PRIMARY KEY (guild_id, discord_id),
                    UNIQUE(guild_id, server_id)
                )
                """
            )
            await cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_member_server_ids_lookup 
                ON member_server_ids(guild_id, server_id)
                """
            )
            
            # Tabelas do sistema de tickets
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ticket_settings (
                    guild_id TEXT PRIMARY KEY,
                    category_id TEXT,
                    log_channel_id TEXT,
                    panel_message_id TEXT,
                    ticket_channel_id TEXT,
                    max_tickets_per_user INTEGER DEFAULT 1,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            
            # Migração: adiciona colunas se não existirem
            await cur.execute("PRAGMA table_info(ticket_settings)")
            rows = await cur.fetchall()
            cols = [row[1] for row in rows]
            if "ticket_channel_id" not in cols:
                await cur.execute("ALTER TABLE ticket_settings ADD COLUMN ticket_channel_id TEXT")
            if "max_tickets_per_user" not in cols:
                await cur.execute("ALTER TABLE ticket_settings ADD COLUMN max_tickets_per_user INTEGER DEFAULT 1")
            if "global_staff_roles" not in cols:
                await cur.execute("ALTER TABLE ticket_settings ADD COLUMN global_staff_roles TEXT")
            
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ticket_topics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    emoji TEXT,
                    button_color TEXT NOT NULL DEFAULT 'primary',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS ticket_topic_roles (
                    topic_id INTEGER NOT NULL,
                    role_id TEXT NOT NULL,
                    PRIMARY KEY (topic_id, role_id),
                    FOREIGN KEY (topic_id) REFERENCES ticket_topics(id) ON DELETE CASCADE
                )
                """
            )
            
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    topic_id INTEGER,
                    claimed_by TEXT,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP,
                    FOREIGN KEY (topic_id) REFERENCES ticket_topics(id) ON DELETE SET NULL
                )
                """
            )
            
            await cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_tickets_guild_channel 
                ON tickets(guild_id, channel_id)
                """
            )
            
            # Tabelas do sistema de ações FiveM
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS action_types (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    min_players INTEGER NOT NULL,
                    max_players INTEGER NOT NULL,
                    total_value REAL NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS active_actions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    type_id INTEGER NOT NULL,
                    creator_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    message_id TEXT,
                    channel_id TEXT,
                    registrations_open INTEGER NOT NULL DEFAULT 0,
                    final_value REAL,
                    result TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    closed_at TIMESTAMP,
                    FOREIGN KEY (type_id) REFERENCES action_types(id) ON DELETE CASCADE
                )
                """
            )
            
            # Migração: adiciona coluna registrations_open se não existir
            try:
                await cur.execute("ALTER TABLE active_actions ADD COLUMN registrations_open INTEGER NOT NULL DEFAULT 0")
            except aiosqlite.OperationalError:
                pass  # Coluna já existe
            
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS action_participants (
                    action_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (action_id, user_id),
                    FOREIGN KEY (action_id) REFERENCES active_actions(id) ON DELETE CASCADE
                )
                """
            )
            
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS action_removed_participants (
                    action_id INTEGER NOT NULL,
                    user_id TEXT NOT NULL,
                    removed_by TEXT NOT NULL,
                    removed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (action_id, user_id),
                    FOREIGN KEY (action_id) REFERENCES active_actions(id) ON DELETE CASCADE
                )
                """
            )
            
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS action_stats (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    participations INTEGER DEFAULT 0,
                    total_earned REAL DEFAULT 0.0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS action_settings (
                    guild_id TEXT PRIMARY KEY,
                    responsible_role_id TEXT,
                    action_channel_id TEXT,
                    ranking_channel_id TEXT,
                    ranking_message_id TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            
            # Tabela para múltiplos cargos responsáveis
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS action_responsible_roles (
                    guild_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, role_id)
                )
                """
            )
            
            # Tabelas do sistema de pontos por voz
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS voice_settings (
                    guild_id TEXT PRIMARY KEY,
                    monitor_all INTEGER NOT NULL DEFAULT 0,
                    afk_channel_id TEXT
                )
                """
            )
            
            # Tabela para gerenciar módulos por servidor
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS guild_modules (
                    guild_id TEXT NOT NULL,
                    module_name TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    PRIMARY KEY (guild_id, module_name)
                )
                """
            )
            
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS voice_allowed_roles (
                    guild_id TEXT NOT NULL,
                    role_id TEXT NOT NULL,
                    PRIMARY KEY (guild_id, role_id)
                )
                """
            )
            
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS voice_monitored_channels (
                    guild_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    PRIMARY KEY (guild_id, channel_id)
                )
                """
            )
            
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS voice_stats (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    total_seconds INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (guild_id, user_id, channel_id)
                )
                """
            )
            
            await cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_voice_stats_user 
                ON voice_stats(guild_id, user_id)
                """
            )
            
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS voice_active_sessions (
                    user_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    join_time TIMESTAMP NOT NULL,
                    PRIMARY KEY (user_id, guild_id)
                )
                """
            )
            
            # Tabelas do sistema de Batalha Naval
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS naval_games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    player1_id TEXT NOT NULL,
                    player2_id TEXT NOT NULL,
                    current_turn TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'setup',
                    channel_id TEXT NOT NULL,
                    message_id TEXT,
                    player1_board TEXT NOT NULL,
                    player2_board TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    finished_at TIMESTAMP,
                    last_move_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            
            await cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_naval_games_guild_status 
                ON naval_games(guild_id, status)
                """
            )
            
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS naval_stats (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    wins INTEGER NOT NULL DEFAULT 0,
                    losses INTEGER NOT NULL DEFAULT 0,
                    points INTEGER NOT NULL DEFAULT 0,
                    total_hits INTEGER NOT NULL DEFAULT 0,
                    total_misses INTEGER NOT NULL DEFAULT 0,
                    current_streak INTEGER NOT NULL DEFAULT 0,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS naval_queue (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            
            # Tabela para logs de membros (comentários, ADVs, moderações, etc.)
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS member_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    author_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    content TEXT,
                    points_delta INTEGER,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            
            await cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_member_logs_lookup 
                ON member_logs(guild_id, target_id, timestamp DESC)
                """
            )
            
            # Tabela para analytics de usuários (estatísticas de engajamento)
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS user_analytics (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    msg_count INTEGER DEFAULT 0,
                    img_count INTEGER DEFAULT 0,
                    mentions_sent INTEGER DEFAULT 0,
                    mentions_received INTEGER DEFAULT 0,
                    reactions_given INTEGER DEFAULT 0,
                    reactions_received INTEGER DEFAULT 0,
                    rank_position INTEGER DEFAULT NULL,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id)
                )
                """
            )
            
            await cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_analytics_ranking 
                ON user_analytics(guild_id, msg_count DESC)
                """
            )
            
            # Tabela para sistema de pontos de membros
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS member_points (
                    user_id TEXT NOT NULL,
                    guild_id TEXT NOT NULL,
                    total_points INTEGER NOT NULL DEFAULT 0,
                    last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, guild_id)
                )
                """
            )
            
            # Tabela para progresso do wizard
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS wizard_progress (
                    guild_id TEXT PRIMARY KEY,
                    current_step TEXT NOT NULL,
                    selected_modules TEXT,
                    config_data TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            
            # Tabela para backups de configuração
            await cur.execute(
                """
                CREATE TABLE IF NOT EXISTS config_backups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id TEXT NOT NULL,
                    backup_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

        await self._conn.commit()

    async def upsert_settings(
        self,
        guild_id: int,
        *,
        channel_registration_embed: Optional[int] = None,
        channel_welcome: Optional[int] = None,
        channel_warnings: Optional[int] = None,
        channel_leaves: Optional[int] = None,
        channel_approval: Optional[int] = None,
        channel_records: Optional[int] = None,
        channel_naval: Optional[int] = None,
        role_set: Optional[int] = None,
        role_member: Optional[int] = None,
        role_adv1: Optional[int] = None,
        role_adv2: Optional[int] = None,
        message_set_embed: Optional[int] = None,
        analytics_ignored_channels: Optional[str] = None,
    ) -> None:
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        data: Dict[str, Any] = {
            "channel_registration_embed": channel_registration_embed,
            "channel_welcome": channel_welcome,
            "channel_warnings": channel_warnings,
            "channel_leaves": channel_leaves,
            "channel_approval": channel_approval,
            "channel_records": channel_records,
            "channel_naval": channel_naval,
            "role_set": role_set,
            "role_member": role_member,
            "role_adv1": role_adv1,
            "role_adv2": role_adv2,
            "message_set_embed": message_set_embed,
            "analytics_ignored_channels": analytics_ignored_channels,
        }
        existing = await self.get_settings(guild_id)
        merged = {**existing, **{k: v for k, v in data.items() if v is not None}}

        async with self._conn.cursor() as cur:
            await cur.execute(
            """
            INSERT INTO settings (
                guild_id,
                channel_registration_embed,
                channel_welcome,
                channel_warnings,
                channel_leaves,
                channel_approval,
                channel_records,
                channel_naval,
                role_set,
                role_member,
                role_adv1,
                role_adv2,
                message_set_embed,
                analytics_ignored_channels
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_registration_embed=excluded.channel_registration_embed,
                channel_welcome=excluded.channel_welcome,
                channel_warnings=excluded.channel_warnings,
                channel_leaves=excluded.channel_leaves,
                channel_approval=excluded.channel_approval,
                channel_records=excluded.channel_records,
                channel_naval=excluded.channel_naval,
                role_set=excluded.role_set,
                role_member=excluded.role_member,
                role_adv1=excluded.role_adv1,
                role_adv2=excluded.role_adv2,
                message_set_embed=excluded.message_set_embed,
                analytics_ignored_channels=excluded.analytics_ignored_channels,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                str(guild_id),
                str(merged.get("channel_registration_embed")) if merged.get("channel_registration_embed") else None,
                str(merged.get("channel_welcome")) if merged.get("channel_welcome") else None,
                str(merged.get("channel_warnings")) if merged.get("channel_warnings") else None,
                str(merged.get("channel_leaves")) if merged.get("channel_leaves") else None,
                str(merged.get("channel_approval")) if merged.get("channel_approval") else None,
                str(merged.get("channel_records")) if merged.get("channel_records") else None,
                str(merged.get("channel_naval")) if merged.get("channel_naval") else None,
                str(merged.get("role_set")) if merged.get("role_set") else None,
                str(merged.get("role_member")) if merged.get("role_member") else None,
                str(merged.get("role_adv1")) if merged.get("role_adv1") else None,
                str(merged.get("role_adv2")) if merged.get("role_adv2") else None,
                str(merged.get("message_set_embed")) if merged.get("message_set_embed") else None,
                merged.get("analytics_ignored_channels"),  # Já é string (JSON)
            ),
        )
        await self._conn.commit()

    async def get_settings(self, guild_id: int) -> Dict[str, Any]:
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            await cur.execute("SELECT * FROM settings WHERE guild_id = ?", (str(guild_id),))
            row = await cur.fetchone()
        if not row:
            return {}
        return dict(row)

    async def create_registration(
        self,
        *,
        guild_id: int,
        user_id: int,
        user_name: str,
        server_id: str,
        recruiter_id: str,
        approval_message_id: Optional[int] = None,
    ) -> int:
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            await cur.execute(
            """
            INSERT INTO registrations (
                guild_id, user_id, user_name, server_id, recruiter_id, status, approval_message_id
            ) VALUES (?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                str(guild_id),
                str(user_id),
                user_name,
                server_id,
                recruiter_id,
                str(approval_message_id) if approval_message_id else None,
            ),
        )
            await self._conn.commit()
        return int(cur.lastrowid)

    async def update_registration_status(
        self,
        registration_id: int,
        status: str,
        *,
        approval_message_id: Optional[int] = None,
    ) -> None:
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            await cur.execute(
            """
            UPDATE registrations
            SET status = ?, approval_message_id = COALESCE(?, approval_message_id), updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, str(approval_message_id) if approval_message_id else None, registration_id),
        )
        await self._conn.commit()

    async def get_registration_by_message(self, approval_message_id: int) -> Optional[Dict[str, Any]]:
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            await cur.execute(
            "SELECT * FROM registrations WHERE approval_message_id = ?", (str(approval_message_id),)
        )
            row = await cur.fetchone()
        return dict(row) if row else None

    async def get_registration(self, registration_id: int) -> Optional[Dict[str, Any]]:
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            await cur.execute("SELECT * FROM registrations WHERE id = ?", (registration_id,))
            row = await cur.fetchone()
        return dict(row) if row else None

    async def get_user_registration(
        self, guild_id: int, user_id: int, status: Optional[str] = "approved"
    ) -> Optional[Dict[str, Any]]:
        """Busca a registration mais recente de um usuário em um servidor.
        
        Args:
            guild_id: ID do servidor
            user_id: ID do usuário no Discord
            status: Status da registration ('approved', 'pending', 'rejected', ou None para qualquer)
        
        Returns:
            Dict com dados da registration ou None se não encontrada
        """
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            if status:
                await cur.execute(
                    "SELECT * FROM registrations WHERE guild_id = ? AND user_id = ? AND status = ? ORDER BY created_at DESC LIMIT 1",
                    (str(guild_id), str(user_id), status),
                )
            else:
                await cur.execute(
                    "SELECT * FROM registrations WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC LIMIT 1",
                    (str(guild_id), str(user_id)),
                )
            row = await cur.fetchone()
        return dict(row) if row else None

    async def list_pending_registrations(self) -> Tuple[Dict[str, Any], ...]:
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            await cur.execute("SELECT * FROM registrations WHERE status = 'pending'")
            rows = await cur.fetchall()
        return tuple(dict(row) for row in rows)

    # ===== Permissões de comandos =====

    async def set_command_permissions(
        self,
        guild_id: int,
        command_name: str,
        role_ids: str,
    ) -> None:
        """Define os cargos autorizados para um comando em uma guild.

        role_ids:
          - '0'  -> apenas administradores
          - ''   -> sem cargos definidos (tratado como apenas admin no check)
          - 'id1,id2,...' -> cargos autorizados
        """
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            await cur.execute(
            """
            INSERT INTO command_permissions (guild_id, command_name, role_ids)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, command_name) DO UPDATE SET
                role_ids = excluded.role_ids
            """,
            (str(guild_id), command_name, role_ids),
        )
        await self._conn.commit()

    async def get_command_permissions(self, guild_id: int, command_name: str) -> Optional[str]:
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            await cur.execute(
            "SELECT role_ids FROM command_permissions WHERE guild_id = ? AND command_name = ?",
            (str(guild_id), command_name),
        )
            row = await cur.fetchone()
        if not row:
            return None
        return row["role_ids"]

    async def list_command_permissions(self, guild_id: int) -> Tuple[Dict[str, Any], ...]:
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            await cur.execute(
            "SELECT command_name, role_ids FROM command_permissions WHERE guild_id = ?",
            (str(guild_id),),
        )
            rows = await cur.fetchall()
        return tuple(dict(row) for row in rows)

    # ===== Mapeamento server_id -> discord_id (otimização) =====

    async def set_member_server_id(self, guild_id: int, discord_id: int, server_id: str) -> None:
        """Armazena o mapeamento server_id -> discord_id para busca otimizada."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO member_server_ids (guild_id, discord_id, server_id)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, discord_id) DO UPDATE SET
                    server_id = excluded.server_id
                """,
                (str(guild_id), str(discord_id), server_id),
            )
        await self._conn.commit()

    async def get_member_by_server_id(self, guild_id: int, server_id: str) -> Optional[int]:
        """Busca o discord_id de um membro pelo server_id (busca otimizada)."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT discord_id FROM member_server_ids WHERE guild_id = ? AND server_id = ?",
                (str(guild_id), server_id.strip()),
            )
            row = await cur.fetchone()
            return int(row["discord_id"]) if row else None

    async def remove_member_server_id(self, guild_id: int, discord_id: int) -> None:
        """Remove o mapeamento quando um membro sai do servidor ou é removido."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM member_server_ids WHERE guild_id = ? AND discord_id = ?",
                (str(guild_id), str(discord_id)),
            )
        await self._conn.commit()

    # ===== Sistema de Tickets =====
    
    async def get_ticket_settings(self, guild_id: int) -> Dict[str, Any]:
        """Busca configurações de tickets de uma guild."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute("SELECT * FROM ticket_settings WHERE guild_id = ?", (str(guild_id),))
            row = await cur.fetchone()
            return dict(row) if row else {}
    
    async def upsert_ticket_settings(
        self,
        guild_id: int,
        *,
        category_id: Optional[int] = None,
        log_channel_id: Optional[int] = None,
        panel_message_id: Optional[int] = None,
        ticket_channel_id: Optional[int] = None,
        max_tickets_per_user: Optional[int] = None,
        global_staff_roles: Optional[str] = None,
    ) -> None:
        """Atualiza ou cria configurações de tickets."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        existing = await self.get_ticket_settings(guild_id)
        merged = {**existing}
        
        if category_id is not None:
            merged["category_id"] = str(category_id)
        if log_channel_id is not None:
            merged["log_channel_id"] = str(log_channel_id)
        if panel_message_id is not None:
            merged["panel_message_id"] = str(panel_message_id)
        if ticket_channel_id is not None:
            merged["ticket_channel_id"] = str(ticket_channel_id)
        if max_tickets_per_user is not None:
            merged["max_tickets_per_user"] = max_tickets_per_user
        if global_staff_roles is not None:
            merged["global_staff_roles"] = global_staff_roles
        
        async with self._conn.cursor() as cur:
            # Verifica se a coluna global_staff_roles existe
            await cur.execute("PRAGMA table_info(ticket_settings)")
            rows = await cur.fetchall()
            cols = [row[1] for row in rows]
            has_global_roles = "global_staff_roles" in cols
            
            if has_global_roles:
                await cur.execute(
                    """
                    INSERT INTO ticket_settings (guild_id, category_id, log_channel_id, panel_message_id, ticket_channel_id, max_tickets_per_user, global_staff_roles)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        category_id=COALESCE(excluded.category_id, category_id),
                        log_channel_id=COALESCE(excluded.log_channel_id, log_channel_id),
                        panel_message_id=COALESCE(excluded.panel_message_id, panel_message_id),
                        ticket_channel_id=COALESCE(excluded.ticket_channel_id, ticket_channel_id),
                        max_tickets_per_user=COALESCE(excluded.max_tickets_per_user, max_tickets_per_user),
                        global_staff_roles=COALESCE(excluded.global_staff_roles, global_staff_roles),
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (
                        str(guild_id),
                        merged.get("category_id"),
                        merged.get("log_channel_id"),
                        merged.get("panel_message_id"),
                        merged.get("ticket_channel_id"),
                        merged.get("max_tickets_per_user", 1),
                        merged.get("global_staff_roles"),
                    ),
                )
                await self._conn.commit()
            else:
                await cur.execute(
                    """
                    INSERT INTO ticket_settings (guild_id, category_id, log_channel_id, panel_message_id, ticket_channel_id, max_tickets_per_user)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        category_id=COALESCE(excluded.category_id, category_id),
                        log_channel_id=COALESCE(excluded.log_channel_id, log_channel_id),
                        panel_message_id=COALESCE(excluded.panel_message_id, panel_message_id),
                        ticket_channel_id=COALESCE(excluded.ticket_channel_id, ticket_channel_id),
                        max_tickets_per_user=COALESCE(excluded.max_tickets_per_user, max_tickets_per_user),
                        updated_at=CURRENT_TIMESTAMP
                    """,
                    (
                        str(guild_id),
                        merged.get("category_id"),
                        merged.get("log_channel_id"),
                        merged.get("panel_message_id"),
                        merged.get("ticket_channel_id"),
                        merged.get("max_tickets_per_user", 1),
                    ),
                )
                await self._conn.commit()
    
    async def create_ticket_topic(
        self,
        guild_id: int,
        name: str,
        description: str,
        emoji: str,
        button_color: str,
    ) -> int:
        """Cria um novo tópico de ticket. Retorna o ID do tópico."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        # Validação robusta: name é obrigatório e não pode ser vazio
        if name is None:
            raise ValueError("O nome do tópico não pode ser None.")
        
        if not isinstance(name, str):
            raise ValueError(f"O nome do tópico deve ser uma string, recebido: {type(name)}")
        
        name = name.strip()
        if not name:
            raise ValueError("O nome do tópico é obrigatório e não pode estar vazio.")
        
        # Sanitização básica
        description = (description.strip() if description and isinstance(description, str) else "") or ""
        emoji = (emoji.strip() if emoji and isinstance(emoji, str) else "") or "🎫"
        button_color = (button_color.strip() if button_color and isinstance(button_color, str) else "") or "primary"
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO ticket_topics (guild_id, name, description, emoji, button_color)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(guild_id), name, description, emoji, button_color),
            )
            await cur.execute("SELECT last_insert_rowid()")
            topic_id = (await cur.fetchone())[0]
        await self._conn.commit()
        return topic_id
    
    async def get_ticket_topics(self, guild_id: int) -> Tuple[Dict[str, Any], ...]:
        """Busca todos os tópicos de tickets de uma guild."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM ticket_topics WHERE guild_id = ? ORDER BY id ASC",
                (str(guild_id),),
            )
            rows = await cur.fetchall()
            return tuple(dict(row) for row in rows)
    
    async def get_ticket_topic(self, topic_id: int) -> Optional[Dict[str, Any]]:
        """Busca um tópico específico por ID."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute("SELECT * FROM ticket_topics WHERE id = ?", (topic_id,))
            row = await cur.fetchone()
            return dict(row) if row else None
    
    async def update_ticket_topic(
        self,
        topic_id: int,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        emoji: Optional[str] = None,
        button_color: Optional[str] = None,
    ) -> None:
        """Atualiza um tópico de ticket existente."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        # Validação: se name for fornecido, não pode ser vazio
        if name is not None and not name.strip():
            raise ValueError("O nome do tópico não pode estar vazio.")
        
        # Constrói a query dinamicamente
        updates = []
        params = []
        
        if name is not None:
            updates.append("name = ?")
            params.append(name.strip())
        if description is not None:
            updates.append("description = ?")
            params.append(description.strip() if description else "")
        if emoji is not None:
            updates.append("emoji = ?")
            params.append(emoji.strip() if emoji else "🎫")
        if button_color is not None:
            updates.append("button_color = ?")
            params.append(button_color.strip() if button_color else "primary")
        
        if not updates:
            return  # Nada para atualizar
        
        params.append(topic_id)
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                f"UPDATE ticket_topics SET {', '.join(updates)} WHERE id = ?",
                params
            )
        await self._conn.commit()
    
    async def delete_ticket_topic(self, topic_id: int) -> None:
        """Deleta um tópico de ticket (cascade remove roles)."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute("DELETE FROM ticket_topics WHERE id = ?", (topic_id,))
        await self._conn.commit()
    
    async def add_topic_role(self, topic_id: int, role_id: int) -> None:
        """Adiciona um cargo a um tópico."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "INSERT OR IGNORE INTO ticket_topic_roles (topic_id, role_id) VALUES (?, ?)",
                (topic_id, str(role_id)),
            )
        await self._conn.commit()
    
    async def get_topic_roles(self, topic_id: int) -> Tuple[str, ...]:
        """Busca todos os cargos de um tópico."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT role_id FROM ticket_topic_roles WHERE topic_id = ?",
                (topic_id,),
            )
            rows = await cur.fetchall()
            return tuple(str(row[0]) for row in rows)
    
    async def remove_topic_role(self, topic_id: int, role_id: int) -> None:
        """Remove um cargo de um tópico."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM ticket_topic_roles WHERE topic_id = ? AND role_id = ?",
                (topic_id, str(role_id)),
            )
        await self._conn.commit()
    
    async def create_ticket(
        self,
        guild_id: int,
        channel_id: int,
        user_id: int,
        topic_id: Optional[int] = None,
    ) -> int:
        """Cria um novo ticket. Retorna o ID do ticket."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO tickets (guild_id, channel_id, user_id, topic_id, status)
                VALUES (?, ?, ?, ?, 'open')
                """,
                (str(guild_id), str(channel_id), str(user_id), topic_id),
            )
            await cur.execute("SELECT last_insert_rowid()")
            ticket_id = (await cur.fetchone())[0]
        await self._conn.commit()
        return ticket_id
    
    async def get_ticket_by_channel(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """Busca um ticket pelo ID do canal."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute("SELECT * FROM tickets WHERE channel_id = ?", (str(channel_id),))
            row = await cur.fetchone()
            return dict(row) if row else None
    
    async def claim_ticket(self, ticket_id: int, user_id: int) -> None:
        """Marca um ticket como assumido por um staff."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "UPDATE tickets SET claimed_by = ? WHERE id = ?",
                (str(user_id), ticket_id),
            )
        await self._conn.commit()

    async def close_ticket(self, ticket_id: int) -> None:
        """Fecha um ticket."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "UPDATE tickets SET status = 'closed', closed_at = CURRENT_TIMESTAMP WHERE id = ?",
                (ticket_id,),
            )
        await self._conn.commit()
    
    async def reopen_ticket(self, ticket_id: int) -> None:
        """Reabre um ticket fechado."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "UPDATE tickets SET status = 'open', closed_at = NULL WHERE id = ?",
                (ticket_id,),
            )
        await self._conn.commit()
    
    async def list_open_tickets(self, guild_id: Optional[int] = None) -> Tuple[Dict[str, Any], ...]:
        """Lista todos os tickets abertos. Se guild_id for fornecido, filtra por guild."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            if guild_id:
                await cur.execute(
                    "SELECT * FROM tickets WHERE guild_id = ? AND status = 'open'",
                    (str(guild_id),),
                )
            else:
                await cur.execute("SELECT * FROM tickets WHERE status = 'open'")
            rows = await cur.fetchall()
        return tuple(dict(row) for row in rows)

    async def count_open_tickets_by_user(self, guild_id: int, user_id: int) -> int:
        """Conta quantos tickets abertos um usuário tem."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND user_id = ? AND status = 'open'",
                (str(guild_id), str(user_id)),
            )
            row = await cur.fetchone()
            return row[0] if row else 0
    
    async def get_ticket_stats(self, guild_id: int) -> Dict[str, Any]:
        """Retorna estatísticas de tickets de uma guild."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            # Total de tickets
            await cur.execute(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ?",
                (str(guild_id),),
            )
            total = (await cur.fetchone())[0]
            
            # Tickets abertos
            await cur.execute(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = 'open'",
                (str(guild_id),),
            )
            open_count = (await cur.fetchone())[0]
            
            # Tickets fechados
            await cur.execute(
                "SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = 'closed'",
                (str(guild_id),),
            )
            closed_count = (await cur.fetchone())[0]
            
            # Tempo médio de resolução (em horas)
            await cur.execute(
                """
                SELECT AVG(
                    (julianday(closed_at) - julianday(created_at)) * 24
                ) as avg_hours
                FROM tickets
                WHERE guild_id = ? AND status = 'closed' AND closed_at IS NOT NULL
                """,
                (str(guild_id),),
            )
            row = await cur.fetchone()
            avg_hours = row[0] if row and row[0] else 0.0
            
            return {
                "total": total,
                "open": open_count,
                "closed": closed_count,
                "avg_resolution_hours": round(avg_hours, 2) if avg_hours else 0.0,
                "resolution_rate": round((closed_count / total * 100) if total > 0 else 0, 2),
            }
    
    async def clear_ticket_settings(self, guild_id: int) -> None:
        """Limpa todas as configurações de tickets de uma guild."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute("DELETE FROM ticket_settings WHERE guild_id = ?", (str(guild_id),))
        await self._conn.commit()
    
    async def clear_ticket_topics(self, guild_id: int) -> None:
        """Limpa todos os tópicos de tickets de uma guild."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute("DELETE FROM ticket_topics WHERE guild_id = ?", (str(guild_id),))
        await self._conn.commit()
    
    async def clear_all_tickets(self, guild_id: int) -> int:
        """Limpa todos os tickets (abertos e fechados) de uma guild. Retorna quantidade deletada."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM tickets WHERE guild_id = ?", (str(guild_id),))
            count = (await cur.fetchone())[0]
            await cur.execute("DELETE FROM tickets WHERE guild_id = ?", (str(guild_id),))
        await self._conn.commit()
        return count
    
    async def clear_closed_tickets(self, guild_id: int) -> int:
        """Limpa apenas tickets fechados de uma guild. Retorna quantidade deletada."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = 'closed'", (str(guild_id),))
            count = (await cur.fetchone())[0]
            await cur.execute("DELETE FROM tickets WHERE guild_id = ? AND status = 'closed'", (str(guild_id),))
        await self._conn.commit()
        return count
    
    async def clear_open_tickets(self, guild_id: int) -> int:
        """Limpa apenas tickets abertos de uma guild. Retorna quantidade deletada."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM tickets WHERE guild_id = ? AND status = 'open'", (str(guild_id),))
            count = (await cur.fetchone())[0]
            await cur.execute("DELETE FROM tickets WHERE guild_id = ? AND status = 'open'", (str(guild_id),))
        await self._conn.commit()
        return count

    # ===== Sistema de Ações FiveM =====
    
    async def add_action_type(
        self,
        guild_id: int,
        name: str,
        min_players: int,
        max_players: int,
        total_value: float,
    ) -> int:
        """Cria um novo tipo de ação."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO action_types (guild_id, name, min_players, max_players, total_value)
                VALUES (?, ?, ?, ?, ?)
                """,
                (str(guild_id), name, min_players, max_players, total_value),
            )
            await cur.execute("SELECT last_insert_rowid()")
            type_id = (await cur.fetchone())[0]
        await self._conn.commit()
        return type_id
    
    async def get_action_types(self, guild_id: int) -> Tuple[Dict[str, Any], ...]:
        """Lista todos os tipos de ação do servidor."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM action_types WHERE guild_id = ? ORDER BY name",
                (str(guild_id),),
            )
            rows = await cur.fetchall()
            return tuple(dict(row) for row in rows)
    
    async def update_action_type(
        self,
        type_id: int,
        name: str,
        min_players: int,
        max_players: int,
        total_value: float,
    ) -> None:
        """Atualiza um tipo de ação existente."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE action_types
                SET name = ?, min_players = ?, max_players = ?, total_value = ?
                WHERE id = ?
                """,
                (name, min_players, max_players, total_value, type_id),
            )
        await self._conn.commit()
    
    async def delete_action_type(self, type_id: int) -> None:
        """Remove um tipo de ação."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute("DELETE FROM action_types WHERE id = ?", (type_id,))
        await self._conn.commit()
    
    async def reset_all_actions(self, guild_id: int) -> None:
        """Deleta todas as ações ativas, zera stats dos usuários, mas mantém os tipos de ação."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            # Primeiro, deleta participantes e removidos das ações que serão deletadas
            await cur.execute(
                """
                DELETE FROM action_participants 
                WHERE action_id IN (
                    SELECT id FROM active_actions WHERE guild_id = ?
                )
                """,
                (str(guild_id),)
            )
            
            await cur.execute(
                """
                DELETE FROM action_removed_participants 
                WHERE action_id IN (
                    SELECT id FROM active_actions WHERE guild_id = ?
                )
                """,
                (str(guild_id),)
            )
            
            # Depois, deleta todas as ações ativas do servidor
            await cur.execute(
                """
                DELETE FROM active_actions 
                WHERE guild_id = ?
                """,
                (str(guild_id),)
            )
            
            # Zera todas as estatísticas dos usuários do servidor
            await cur.execute(
                """
                UPDATE action_stats 
                SET participations = 0, 
                    total_earned = 0.0,
                    updated_at = CURRENT_TIMESTAMP
                WHERE guild_id = ?
                """,
                (str(guild_id),)
            )
            
            # Reseta o autoincrement de active_actions
            await cur.execute("DELETE FROM sqlite_sequence WHERE name = 'active_actions'")
        await self._conn.commit()
    
    async def create_active_action(
        self,
        guild_id: int,
        type_id: int,
        creator_id: int,
        message_id: int,
        channel_id: int,
    ) -> int:
        """Cria uma ação ativa (com inscrições fechadas inicialmente)."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO active_actions (guild_id, type_id, creator_id, message_id, channel_id, registrations_open)
                VALUES (?, ?, ?, ?, ?, 0)
                """,
                (str(guild_id), type_id, str(creator_id), str(message_id), str(channel_id)),
            )
            await cur.execute("SELECT last_insert_rowid()")
            action_id = (await cur.fetchone())[0]
        await self._conn.commit()
        return action_id
    
    async def get_active_action(self, action_id: int) -> Optional[Dict[str, Any]]:
        """Busca uma ação ativa por ID."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT a.*, t.name as type_name, t.min_players, t.max_players, t.total_value
                FROM active_actions a
                JOIN action_types t ON a.type_id = t.id
                WHERE a.id = ?
                """,
                (action_id,),
            )
            row = await cur.fetchone()
            return dict(row) if row else None
    
    async def get_active_action_by_message(self, message_id: int) -> Optional[Dict[str, Any]]:
        """Busca uma ação ativa por message_id."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT a.*, t.name as type_name, t.min_players, t.max_players, t.total_value
                FROM active_actions a
                JOIN action_types t ON a.type_id = t.id
                WHERE a.message_id = ?
                """,
                (str(message_id),),
            )
            row = await cur.fetchone()
            return dict(row) if row else None
    
    async def list_active_actions(self, guild_id: int, status: Optional[str] = None) -> Tuple[Dict[str, Any], ...]:
        """Lista ações ativas do servidor, opcionalmente filtradas por status."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            if status:
                await cur.execute(
                    """
                    SELECT a.*, t.name as type_name, t.min_players, t.max_players, t.total_value
                    FROM active_actions a
                    JOIN action_types t ON a.type_id = t.id
                    WHERE a.guild_id = ? AND a.status = ?
                    ORDER BY a.created_at DESC
                    """,
                    (str(guild_id), status),
                )
            else:
                await cur.execute(
                    """
                    SELECT a.*, t.name as type_name, t.min_players, t.max_players, t.total_value
                    FROM active_actions a
                    JOIN action_types t ON a.type_id = t.id
                    WHERE a.guild_id = ?
                    ORDER BY a.created_at DESC
                    """,
                    (str(guild_id),),
                )
            rows = await cur.fetchall()
            return tuple(dict(row) for row in rows)
    
    async def update_action_status(
        self,
        action_id: int,
        status: str,
        final_value: Optional[float] = None,
        result: Optional[str] = None,
        message_id: Optional[int] = None,
        registrations_open: Optional[bool] = None,
    ) -> None:
        """Atualiza o status e resultado de uma ação."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            updates = ["status = ?"]
            params = [status]
            
            if final_value is not None:
                updates.append("final_value = ?")
                params.append(final_value)
            
            if result:
                updates.append("result = ?")
                updates.append("closed_at = CURRENT_TIMESTAMP")
                params.append(result)
            
            if message_id is not None:
                updates.append("message_id = ?")
                params.append(str(message_id))
            
            if registrations_open is not None:
                updates.append("registrations_open = ?")
                params.append(1 if registrations_open else 0)
            
            params.append(action_id)
            
            await cur.execute(
                f"UPDATE active_actions SET {', '.join(updates)} WHERE id = ?",
                params
            )
        await self._conn.commit()
    
    async def delete_active_action(self, action_id: int) -> None:
        """Deleta uma ação ativa."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute("DELETE FROM active_actions WHERE id = ?", (action_id,))
        await self._conn.commit()
    
    async def add_participant(self, action_id: int, user_id: int) -> None:
        """Adiciona um participante à ação."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "INSERT OR IGNORE INTO action_participants (action_id, user_id) VALUES (?, ?)",
                (action_id, str(user_id)),
            )
        await self._conn.commit()
    
    async def remove_participant(self, action_id: int, user_id: int) -> None:
        """Remove um participante da ação."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM action_participants WHERE action_id = ? AND user_id = ?",
                (action_id, str(user_id)),
            )
        await self._conn.commit()
    
    async def get_participants(self, action_id: int) -> Tuple[Dict[str, Any], ...]:
        """Lista todos os participantes de uma ação."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM action_participants WHERE action_id = ? ORDER BY joined_at",
                (action_id,),
            )
            rows = await cur.fetchall()
            return tuple(dict(row) for row in rows)
    
    async def remove_participant_by_mod(self, action_id: int, user_id: int, removed_by: int) -> None:
        """Remove um participante da ação e adiciona à lista de removidos."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            # Remove da lista de participantes
            await cur.execute(
                "DELETE FROM action_participants WHERE action_id = ? AND user_id = ?",
                (action_id, str(user_id)),
            )
            # Adiciona à lista de removidos
            await cur.execute(
                """
                INSERT INTO action_removed_participants (action_id, user_id, removed_by)
                VALUES (?, ?, ?)
                ON CONFLICT(action_id, user_id) DO UPDATE SET
                    removed_by = ?,
                    removed_at = CURRENT_TIMESTAMP
                """,
                (action_id, str(user_id), str(removed_by), str(removed_by)),
            )
        await self._conn.commit()
    
    async def get_removed_participants(self, action_id: int) -> Tuple[Dict[str, Any], ...]:
        """Lista todos os participantes removidos de uma ação."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM action_removed_participants WHERE action_id = ? ORDER BY removed_at",
                (action_id,),
            )
            rows = await cur.fetchall()
            return tuple(dict(row) for row in rows)
    
    async def restore_participant(self, action_id: int, user_id: int) -> None:
        """Restaura um participante removido."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            # Remove da lista de removidos
            await cur.execute(
                "DELETE FROM action_removed_participants WHERE action_id = ? AND user_id = ?",
                (action_id, str(user_id)),
            )
            # Adiciona de volta à lista de participantes
            await cur.execute(
                """
                INSERT INTO action_participants (action_id, user_id, joined_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(action_id, user_id) DO NOTHING
                """,
                (action_id, str(user_id)),
            )
        await self._conn.commit()
    
    async def count_participants(self, action_id: int) -> int:
        """Conta o número de participantes de uma ação."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM action_participants WHERE action_id = ?",
                (action_id,),
            )
            row = await cur.fetchone()
            return row[0] if row else 0
    
    async def increment_stats(self, guild_id: int, user_id: int, amount: float) -> None:
        """Incrementa participações e total ganho do usuário."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO action_stats (guild_id, user_id, participations, total_earned)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    participations = participations + 1,
                    total_earned = total_earned + ?,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(guild_id), str(user_id), amount, amount),
            )
        await self._conn.commit()
    
    async def increment_participation_only(self, guild_id: int, user_id: int) -> None:
        """Incrementa apenas participações (sem valor ganho)."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO action_stats (guild_id, user_id, participations, total_earned)
                VALUES (?, ?, 1, 0.0)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    participations = participations + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(guild_id), str(user_id)),
            )
        await self._conn.commit()
    
    async def get_user_stats(self, guild_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Busca estatísticas do usuário."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM action_stats WHERE guild_id = ? AND user_id = ?",
                (str(guild_id), str(user_id)),
            )
            row = await cur.fetchone()
            return dict(row) if row else None
    
    async def get_action_ranking(self, guild_id: int, limit: int = 10) -> Tuple[Dict[str, Any], ...]:
        """Retorna ranking por participações, ordenado por participações DESC, total_earned DESC."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM action_stats
                WHERE guild_id = ?
                ORDER BY participations DESC, total_earned DESC
                LIMIT ?
                """,
                (str(guild_id), limit),
            )
            rows = await cur.fetchall()
        return tuple(dict(row) for row in rows)

    async def get_action_settings(self, guild_id: int) -> Dict[str, Any]:
        """Busca configurações de ações do servidor."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM action_settings WHERE guild_id = ?",
                (str(guild_id),),
            )
            row = await cur.fetchone()
            return dict(row) if row else {}
    
    async def upsert_action_settings(
        self,
        guild_id: int,
        responsible_role_id: Optional[int] = None,
        action_channel_id: Optional[int] = None,
        ranking_channel_id: Optional[int] = None,
    ) -> None:
        """Salva ou atualiza configurações de ações."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        existing = await self.get_action_settings(guild_id)
        merged = {**existing}
        
        if responsible_role_id is not None:
            merged["responsible_role_id"] = str(responsible_role_id)
        
        if action_channel_id is not None:
            merged["action_channel_id"] = str(action_channel_id)
        
        if ranking_channel_id is not None:
            merged["ranking_channel_id"] = str(ranking_channel_id)
        
        async with self._conn.cursor() as cur:
            # Verifica colunas existentes na tabela
            await cur.execute("PRAGMA table_info(action_settings)")
            columns = [row[1] for row in await cur.fetchall()]
            
            # Migração para action_channel_id
            if "action_channel_id" not in columns:
                try:
                    await cur.execute("ALTER TABLE action_settings ADD COLUMN action_channel_id TEXT")
                except aiosqlite.OperationalError:
                    pass
            
            # Migração para ranking_channel_id
            if "ranking_channel_id" not in columns:
                try:
                    await cur.execute("ALTER TABLE action_settings ADD COLUMN ranking_channel_id TEXT")
                except aiosqlite.OperationalError:
                    pass
            
            # Migração para ranking_message_id
            if "ranking_message_id" not in columns:
                try:
                    await cur.execute("ALTER TABLE action_settings ADD COLUMN ranking_message_id TEXT")
                except aiosqlite.OperationalError:
                    pass
            
            await cur.execute(
                """
                INSERT INTO action_settings (guild_id, responsible_role_id, action_channel_id, ranking_channel_id)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    responsible_role_id = COALESCE(excluded.responsible_role_id, responsible_role_id),
                    action_channel_id = COALESCE(excluded.action_channel_id, action_channel_id),
                    ranking_channel_id = COALESCE(excluded.ranking_channel_id, ranking_channel_id),
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(guild_id), merged.get("responsible_role_id"), merged.get("action_channel_id"), merged.get("ranking_channel_id")),
            )
        await self._conn.commit()
    
    async def add_responsible_role(self, guild_id: int, role_id: int) -> None:
        """Adiciona um cargo responsável."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT OR IGNORE INTO action_responsible_roles (guild_id, role_id)
                VALUES (?, ?)
                """,
                (str(guild_id), str(role_id)),
            )
        await self._conn.commit()
    
    async def remove_responsible_role(self, guild_id: int, role_id: int) -> None:
        """Remove um cargo responsável."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                DELETE FROM action_responsible_roles
                WHERE guild_id = ? AND role_id = ?
                """,
                (str(guild_id), str(role_id)),
            )
        await self._conn.commit()
    
    async def get_responsible_roles(self, guild_id: int) -> list:
        """Retorna lista de IDs dos cargos responsáveis."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT role_id FROM action_responsible_roles WHERE guild_id = ?",
                (str(guild_id),),
            )
            rows = await cur.fetchall()
            return [int(row[0]) for row in rows if row[0] and str(row[0]).isdigit()]
    
    async def upsert_ranking_message_id(self, guild_id: int, message_id: int) -> None:
        """Salva ou atualiza o ID da mensagem do ranking."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            # Verifica se ranking_message_id existe na tabela
            await cur.execute("PRAGMA table_info(action_settings)")
            columns = [row[1] for row in await cur.fetchall()]
            
            if "ranking_message_id" not in columns:
                try:
                    await cur.execute("ALTER TABLE action_settings ADD COLUMN ranking_message_id TEXT")
                except aiosqlite.OperationalError:
                    pass
            
            await cur.execute(
                """
                INSERT INTO action_settings (guild_id, ranking_message_id)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    ranking_message_id = excluded.ranking_message_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(guild_id), str(message_id)),
            )
        await self._conn.commit()
    
    # ===== Sistema de Pontos por Voz =====
    
    async def get_voice_settings(self, guild_id: int) -> Dict[str, Any]:
        """Busca configurações de voz de uma guild."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute("SELECT * FROM voice_settings WHERE guild_id = ?", (str(guild_id),))
            row = await cur.fetchone()
            return dict(row) if row else {}
    
    async def upsert_voice_settings(
        self,
        guild_id: int,
        monitor_all: Optional[bool] = None,
        afk_channel_id: Optional[int] = None,
    ) -> None:
        """Atualiza ou cria configurações de voz."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        existing = await self.get_voice_settings(guild_id)
        merged = {**existing}
        
        if monitor_all is not None:
            merged["monitor_all"] = 1 if monitor_all else 0
        if afk_channel_id is not None:
            merged["afk_channel_id"] = str(afk_channel_id)
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO voice_settings (guild_id, monitor_all, afk_channel_id)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    monitor_all = COALESCE(excluded.monitor_all, monitor_all),
                    afk_channel_id = COALESCE(excluded.afk_channel_id, afk_channel_id)
                """,
                (
                    str(guild_id),
                    merged.get("monitor_all", 0),
                    merged.get("afk_channel_id"),
                ),
            )
        await self._conn.commit()
    
    async def get_allowed_roles(self, guild_id: int) -> Tuple[int, ...]:
        """Busca todos os cargos permitidos para monitoramento."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT role_id FROM voice_allowed_roles WHERE guild_id = ?",
                (str(guild_id),),
            )
            rows = await cur.fetchall()
            return tuple(int(row[0]) for row in rows if row[0] and str(row[0]).isdigit())
    
    async def add_allowed_role(self, guild_id: int, role_id: int) -> None:
        """Adiciona um cargo à lista de permitidos."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "INSERT OR IGNORE INTO voice_allowed_roles (guild_id, role_id) VALUES (?, ?)",
                (str(guild_id), str(role_id)),
            )
        await self._conn.commit()
    
    async def remove_allowed_role(self, guild_id: int, role_id: int) -> None:
        """Remove um cargo da lista de permitidos."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM voice_allowed_roles WHERE guild_id = ? AND role_id = ?",
                (str(guild_id), str(role_id)),
            )
        await self._conn.commit()
    
    async def get_monitored_channels(self, guild_id: int) -> Tuple[int, ...]:
        """Busca todos os canais monitorados."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT channel_id FROM voice_monitored_channels WHERE guild_id = ?",
                (str(guild_id),),
            )
            rows = await cur.fetchall()
            return tuple(int(row[0]) for row in rows if row[0] and str(row[0]).isdigit())
    
    async def add_monitored_channel(self, guild_id: int, channel_id: int) -> None:
        """Adiciona um canal à lista de monitorados."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "INSERT OR IGNORE INTO voice_monitored_channels (guild_id, channel_id) VALUES (?, ?)",
                (str(guild_id), str(channel_id)),
            )
        await self._conn.commit()
    
    async def remove_monitored_channel(self, guild_id: int, channel_id: int) -> None:
        """Remove um canal da lista de monitorados."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM voice_monitored_channels WHERE guild_id = ? AND channel_id = ?",
                (str(guild_id), str(channel_id)),
            )
        await self._conn.commit()
    
    async def get_voice_stats(self, guild_id: int, user_id: int) -> Tuple[Dict[str, Any], ...]:
        """Busca estatísticas de voz do usuário por canal."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM voice_stats WHERE guild_id = ? AND user_id = ? ORDER BY total_seconds DESC",
                (str(guild_id), str(user_id)),
            )
            rows = await cur.fetchall()
            return tuple(dict(row) for row in rows)
    
    async def get_total_voice_time(self, guild_id: int, user_id: int) -> int:
        """Retorna o tempo total em segundos do usuário (soma de todos os canais)."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT SUM(total_seconds) FROM voice_stats WHERE guild_id = ? AND user_id = ?",
                (str(guild_id), str(user_id)),
            )
            row = await cur.fetchone()
            return int(row[0]) if row and row[0] else 0
    
    async def increment_voice_time(self, guild_id: int, user_id: int, channel_id: int, seconds: int) -> None:
        """Incrementa o tempo de voz do usuário em um canal."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO voice_stats (guild_id, user_id, channel_id, total_seconds)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id, channel_id) DO UPDATE SET
                    total_seconds = total_seconds + excluded.total_seconds
                """,
                (str(guild_id), str(user_id), str(channel_id), seconds),
            )
        await self._conn.commit()
    
    async def adjust_voice_time(self, guild_id: int, user_id: int, seconds_delta: int) -> int:
        """Ajusta o tempo total de voz do usuário (adiciona ou remove segundos).
        
        Distribui o ajuste proporcionalmente entre os canais existentes, ou cria
        uma entrada em um canal padrão se não houver registros.
        
        Args:
            guild_id: ID do servidor
            user_id: ID do usuário
            seconds_delta: Segundos a adicionar (positivo) ou remover (negativo)
            
        Returns:
            Novo tempo total em segundos
        """
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            # Busca estatísticas atuais por canal
            await cur.execute(
                """
                SELECT channel_id, total_seconds FROM voice_stats
                WHERE guild_id = ? AND user_id = ?
                ORDER BY total_seconds DESC
                """,
                (str(guild_id), str(user_id))
            )
            rows = await cur.fetchall()
            
            if not rows:
                # Se não houver registros, cria um em um canal padrão (0 = canal geral)
                if seconds_delta > 0:
                    await cur.execute(
                        """
                        INSERT INTO voice_stats (guild_id, user_id, channel_id, total_seconds)
                        VALUES (?, ?, ?, ?)
                        """,
                        (str(guild_id), str(user_id), "0", seconds_delta)
                    )
                return max(0, seconds_delta)
            
            # Calcula total atual
            total_current = sum(int(row[1]) for row in rows)
            
            # Se for remover e o total for menor que o delta negativo, zera tudo
            if seconds_delta < 0 and abs(seconds_delta) >= total_current:
                # Zera todos os canais
                await cur.execute(
                    """
                    DELETE FROM voice_stats
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (str(guild_id), str(user_id))
                )
                await self._conn.commit()
                return 0
            
            # Distribui proporcionalmente entre os canais
            new_total = total_current + seconds_delta
            if new_total < 0:
                new_total = 0
            
            # Calcula proporção para cada canal
            for row in rows:
                channel_id = row[0]
                current_seconds = int(row[1])
                
                if total_current > 0:
                    # Proporção do canal no total
                    proportion = current_seconds / total_current
                    new_seconds = int(new_total * proportion)
                else:
                    # Se total é 0, distribui igualmente
                    new_seconds = int(new_total / len(rows)) if rows else 0
                
                # Garante que não fique negativo
                new_seconds = max(0, new_seconds)
                
                await cur.execute(
                    """
                    UPDATE voice_stats
                    SET total_seconds = ?
                    WHERE guild_id = ? AND user_id = ? AND channel_id = ?
                    """,
                    (new_seconds, str(guild_id), str(user_id), channel_id)
                )
            
            # Remove canais que ficaram com 0 segundos
            await cur.execute(
                """
                DELETE FROM voice_stats
                WHERE guild_id = ? AND user_id = ? AND total_seconds = 0
                """,
                (str(guild_id), str(user_id))
            )
            
        await self._conn.commit()
        
        # Retorna novo total
        return await self.get_total_voice_time(guild_id, user_id)
    
    async def get_voice_ranking(self, guild_id: int, limit: int = 10) -> Tuple[Dict[str, Any], ...]:
        """Retorna ranking de tempo total por usuário."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT guild_id, user_id, SUM(total_seconds) as total_seconds
                FROM voice_stats
                WHERE guild_id = ?
                GROUP BY guild_id, user_id
                ORDER BY total_seconds DESC
                LIMIT ?
                """,
                (str(guild_id), limit),
            )
            rows = await cur.fetchall()
            return tuple(dict(row) for row in rows)
    
    async def create_voice_session(self, user_id: int, guild_id: int, channel_id: int) -> None:
        """Cria uma sessão ativa de voz."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO voice_active_sessions (user_id, guild_id, channel_id, join_time)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    join_time = CURRENT_TIMESTAMP
                """,
                (str(user_id), str(guild_id), str(channel_id)),
            )
        await self._conn.commit()
    
    async def get_voice_session(self, user_id: int, guild_id: int) -> Optional[Dict[str, Any]]:
        """Busca uma sessão ativa de voz."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM voice_active_sessions WHERE user_id = ? AND guild_id = ?",
                (str(user_id), str(guild_id)),
            )
            row = await cur.fetchone()
            return dict(row) if row else None
    
    async def delete_voice_session(self, user_id: int, guild_id: int) -> None:
        """Remove uma sessão ativa de voz."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM voice_active_sessions WHERE user_id = ? AND guild_id = ?",
                (str(user_id), str(guild_id)),
            )
        await self._conn.commit()
    
    async def cleanup_stale_sessions(self, guild_id: int, active_user_ids: set) -> None:
        """Remove sessões de usuários que não estão mais em call."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            # Busca todas as sessões ativas do servidor
            await cur.execute(
                "SELECT user_id FROM voice_active_sessions WHERE guild_id = ?",
                (str(guild_id),),
            )
            rows = await cur.fetchall()
            session_user_ids = {int(row[0]) for row in rows if row[0] and str(row[0]).isdigit()}
            
            # Remove sessões de usuários que não estão mais em call
            stale_ids = session_user_ids - active_user_ids
            if stale_ids:
                placeholders = ",".join("?" * len(stale_ids))
                await cur.execute(
                    f"DELETE FROM voice_active_sessions WHERE guild_id = ? AND user_id IN ({placeholders})",
                    (str(guild_id),) + tuple(str(uid) for uid in stale_ids),
                )
        await self._conn.commit()

    # Métodos para gerenciar módulos por servidor
    async def get_module_status(self, guild_id: int, module_name: str) -> bool:
        """Retorna se um módulo está ativo para um servidor."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT is_active FROM guild_modules WHERE guild_id = ? AND module_name = ?",
                (str(guild_id), module_name),
            )
            row = await cur.fetchone()
            return bool(row[0]) if row else True  # Padrão: ativo se não existir registro

    async def set_module_status(self, guild_id: int, module_name: str, is_active: bool) -> None:
        """Define o status de um módulo para um servidor."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")

        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT OR REPLACE INTO guild_modules (guild_id, module_name, is_active)
                VALUES (?, ?, ?)
                """,
                (str(guild_id), module_name, 1 if is_active else 0),
            )
        await self._conn.commit()

    async def get_all_modules_status(self, guild_id: int) -> Dict[str, bool]:
        """Retorna um dicionário com o status de todos os módulos para um servidor."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT module_name, is_active FROM guild_modules WHERE guild_id = ?",
                (str(guild_id),),
            )
            rows = await cur.fetchall()
            return {row[0]: bool(row[1]) for row in rows}
    
    # ===== Sistema de Batalha Naval =====
    
    async def create_naval_game(
        self,
        guild_id: int,
        player1_id: int,
        player2_id: int,
        channel_id: int,
        message_id: Optional[int] = None,
    ) -> int:
        """Cria uma nova partida de batalha naval."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        import json
        empty_board = json.dumps({"ships": [], "shots": []})
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO naval_games (guild_id, player1_id, player2_id, current_turn, channel_id, message_id, player1_board, player2_board)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (str(guild_id), str(player1_id), str(player2_id), str(player1_id), str(channel_id), str(message_id) if message_id else None, empty_board, empty_board),
            )
            await cur.execute("SELECT last_insert_rowid()")
            game_id = (await cur.fetchone())[0]
        await self._conn.commit()
        return game_id
    
    async def get_naval_game(self, game_id: int) -> Optional[Dict[str, Any]]:
        """Busca uma partida por ID."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute("SELECT * FROM naval_games WHERE id = ?", (game_id,))
            row = await cur.fetchone()
            return dict(row) if row else None
    
    async def get_naval_game_by_players(self, guild_id: int, player_id: int) -> Optional[Dict[str, Any]]:
        """Busca partida ativa de um jogador."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM naval_games 
                WHERE guild_id = ? AND status IN ('setup', 'active') 
                AND (player1_id = ? OR player2_id = ?)
                LIMIT 1
                """,
                (str(guild_id), str(player_id), str(player_id)),
            )
            row = await cur.fetchone()
            return dict(row) if row else None
    
    async def update_naval_game(
        self,
        game_id: int,
        *,
        current_turn: Optional[str] = None,
        status: Optional[str] = None,
        message_id: Optional[int] = None,
        player1_board: Optional[str] = None,
        player2_board: Optional[str] = None,
        finished_at: Optional[str] = None,
    ) -> None:
        """Atualiza uma partida."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        updates = []
        params = []
        
        if current_turn is not None:
            updates.append("current_turn = ?")
            params.append(str(current_turn))
        if status is not None:
            updates.append("status = ?")
            params.append(status)
        if message_id is not None:
            updates.append("message_id = ?")
            params.append(str(message_id))
        if player1_board is not None:
            updates.append("player1_board = ?")
            params.append(player1_board)
        if player2_board is not None:
            updates.append("player2_board = ?")
            params.append(player2_board)
        if finished_at is not None:
            updates.append("finished_at = ?")
            params.append(finished_at)
        
        if not updates:
            return
        
        params.append(game_id)
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                f"UPDATE naval_games SET {', '.join(updates)} WHERE id = ?",
                params
            )
        await self._conn.commit()
    
    async def update_naval_game_last_move(self, game_id: int) -> None:
        """Atualiza o timestamp do último movimento."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "UPDATE naval_games SET last_move_at = CURRENT_TIMESTAMP WHERE id = ?",
                (game_id,)
            )
        await self._conn.commit()
    
    async def get_stale_games(self, timeout_minutes: int = 5) -> Tuple[Dict[str, Any], ...]:
        """Busca partidas sem movimento há mais de X minutos."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM naval_games 
                WHERE status IN ('setup', 'active')
                AND datetime(last_move_at, '+' || ? || ' minutes') < datetime('now')
                """,
                (timeout_minutes,),
            )
            rows = await cur.fetchall()
            return tuple(dict(row) for row in rows)
    
    async def cleanup_abandoned_games(self, days: int = 1) -> int:
        """Remove partidas antigas (abandonadas há mais de X dias)."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT COUNT(*) FROM naval_games 
                WHERE status = 'finished' 
                AND datetime(finished_at, '+' || ? || ' days') < datetime('now')
                """,
                (days,),
            )
            count = (await cur.fetchone())[0]
            
            await cur.execute(
                """
                DELETE FROM naval_games 
                WHERE status = 'finished' 
                AND datetime(finished_at, '+' || ? || ' days') < datetime('now')
                """,
                (days,),
            )
        await self._conn.commit()
        return count
    
    async def get_naval_stats(self, guild_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Busca estatísticas de um jogador."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM naval_stats WHERE guild_id = ? AND user_id = ?",
                (str(guild_id), str(user_id)),
            )
            row = await cur.fetchone()
            return dict(row) if row else None
    
    async def update_naval_stats(
        self,
        guild_id: int,
        user_id: int,
        *,
        wins: Optional[int] = None,
        losses: Optional[int] = None,
        points: Optional[int] = None,
        total_hits: Optional[int] = None,
        total_misses: Optional[int] = None,
    ) -> None:
        """Atualiza estatísticas de um jogador."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        existing = await self.get_naval_stats(guild_id, user_id)
        if not existing:
            # Cria registro inicial
            async with self._conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO naval_stats (guild_id, user_id, wins, losses, points, total_hits, total_misses)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(guild_id),
                        str(user_id),
                        wins or 0,
                        losses or 0,
                        points or 0,
                        total_hits or 0,
                        total_misses or 0,
                    ),
                )
            await self._conn.commit()
            existing = await self.get_naval_stats(guild_id, user_id)
        
        updates = []
        params = []
        
        if wins is not None:
            updates.append("wins = wins + ?")
            params.append(wins)
        if losses is not None:
            updates.append("losses = losses + ?")
            params.append(losses)
        if points is not None:
            updates.append("points = points + ?")
            params.append(points)
        if total_hits is not None:
            updates.append("total_hits = total_hits + ?")
            params.append(total_hits)
        if total_misses is not None:
            updates.append("total_misses = total_misses + ?")
            params.append(total_misses)
        
        if not updates:
            return
        
        params.extend([str(guild_id), str(user_id)])
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                f"UPDATE naval_stats SET {', '.join(updates)}, updated_at = CURRENT_TIMESTAMP WHERE guild_id = ? AND user_id = ?",
                params
            )
        await self._conn.commit()
    
    async def increment_naval_streak(self, guild_id: int, user_id: int) -> None:
        """Incrementa a sequência de vitórias."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO naval_stats (guild_id, user_id, current_streak)
                VALUES (?, ?, 1)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    current_streak = current_streak + 1,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(guild_id), str(user_id)),
            )
        await self._conn.commit()
    
    async def reset_naval_streak(self, guild_id: int, user_id: int) -> None:
        """Reseta a sequência de vitórias."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE naval_stats 
                SET current_streak = 0, updated_at = CURRENT_TIMESTAMP
                WHERE guild_id = ? AND user_id = ?
                """,
                (str(guild_id), str(user_id)),
            )
        await self._conn.commit()
    
    async def clear_naval_stats(self, guild_id: int) -> None:
        """Zera todas as estatísticas de Batalha Naval de um servidor."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                DELETE FROM naval_stats
                WHERE guild_id = ?
                """,
                (str(guild_id),),
            )
        await self._conn.commit()
    
    async def get_naval_ranking(self, guild_id: int, limit: int = 10) -> Tuple[Dict[str, Any], ...]:
        """Retorna ranking de jogadores por pontos."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM naval_stats
                WHERE guild_id = ?
                ORDER BY points DESC, wins DESC, current_streak DESC
                LIMIT ?
                """,
                (str(guild_id), limit),
            )
            rows = await cur.fetchall()
            return tuple(dict(row) for row in rows)
    
    async def add_to_queue(self, guild_id: int, user_id: int) -> None:
        """Adiciona jogador à fila de matchmaking."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT OR REPLACE INTO naval_queue (guild_id, user_id, joined_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (str(guild_id), str(user_id)),
            )
        await self._conn.commit()
    
    async def remove_from_queue(self, guild_id: int, user_id: int) -> None:
        """Remove jogador da fila."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM naval_queue WHERE guild_id = ? AND user_id = ?",
                (str(guild_id), str(user_id)),
            )
        await self._conn.commit()
    
    async def get_queue(self, guild_id: int) -> Tuple[Dict[str, Any], ...]:
        """Lista jogadores na fila."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "SELECT * FROM naval_queue WHERE guild_id = ? ORDER BY joined_at",
                (str(guild_id),),
            )
            rows = await cur.fetchall()
            return tuple(dict(row) for row in rows)
    
    async def match_players(self, guild_id: int) -> Optional[Tuple[int, int]]:
        """Tenta fazer match entre dois jogadores na fila. Retorna (player1_id, player2_id) ou None."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        queue = await self.get_queue(guild_id)
        if len(queue) < 2:
            return None
        
        # Pega os dois primeiros
        player1_id = int(queue[0]["user_id"])
        player2_id = int(queue[1]["user_id"])
        
        # Remove ambos da fila
        await self.remove_from_queue(guild_id, player1_id)
        await self.remove_from_queue(guild_id, player2_id)
        
        return (player1_id, player2_id)
    
    async def list_active_naval_games(self, guild_id: Optional[int] = None) -> Tuple[Dict[str, Any], ...]:
        """Lista partidas ativas (setup ou active)."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            if guild_id:
                await cur.execute(
                    "SELECT * FROM naval_games WHERE guild_id = ? AND status IN ('setup', 'active')",
                    (str(guild_id),),
                )
            else:
                await cur.execute(
                    "SELECT * FROM naval_games WHERE status IN ('setup', 'active')"
                )
            rows = await cur.fetchall()
            return tuple(dict(row) for row in rows)
    
    # ===== MÉTODOS DE MEMBER LOGS E POINTS =====
    
    async def add_member_log(
        self,
        guild_id: int,
        target_id: int,
        author_id: int,
        log_type: str,
        content: Optional[str] = None,
        points_delta: Optional[int] = None
    ) -> None:
        """Adiciona um log de membro (comentário, ADV, moderação, etc.)."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO member_logs (guild_id, target_id, author_id, type, content, points_delta)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (str(guild_id), str(target_id), str(author_id), log_type, content, points_delta)
            )
        await self._conn.commit()
    
    async def get_member_logs(
        self,
        guild_id: int,
        target_id: int,
        limit: int = 100,
        offset: int = 0,
        log_type: Optional[str] = None
    ) -> Tuple[Dict[str, Any], ...]:
        """Busca logs de um membro com paginação."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            if log_type:
                await cur.execute(
                    """
                    SELECT * FROM member_logs
                    WHERE guild_id = ? AND target_id = ? AND type = ?
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                    """,
                    (str(guild_id), str(target_id), log_type, limit, offset)
                )
            else:
                await cur.execute(
                    """
                    SELECT * FROM member_logs
                    WHERE guild_id = ? AND target_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                    """,
                    (str(guild_id), str(target_id), limit, offset)
                )
            rows = await cur.fetchall()
            return tuple(dict(row) for row in rows)
    
    async def count_member_logs(
        self,
        guild_id: int,
        target_id: int,
        log_type: Optional[str] = None
    ) -> int:
        """Conta total de logs de um membro."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            if log_type:
                await cur.execute(
                    """
                    SELECT COUNT(*) FROM member_logs
                    WHERE guild_id = ? AND target_id = ? AND type = ?
                    """,
                    (str(guild_id), str(target_id), log_type)
                )
            else:
                await cur.execute(
                    """
                    SELECT COUNT(*) FROM member_logs
                    WHERE guild_id = ? AND target_id = ?
                    """,
                    (str(guild_id), str(target_id))
                )
            row = await cur.fetchone()
            return row[0] if row else 0
    
    async def get_member_points(self, guild_id: int, user_id: int) -> int:
        """Retorna pontos atuais de um membro (0 se não existir)."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT total_points FROM member_points
                WHERE guild_id = ? AND user_id = ?
                """,
                (str(guild_id), str(user_id))
            )
            row = await cur.fetchone()
            return row[0] if row else 0
    
    async def update_member_points(self, guild_id: int, user_id: int, delta: int) -> int:
        """Atualiza pontos de um membro (delta pode ser positivo ou negativo). Retorna novo total."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            # Insere ou atualiza
            await cur.execute(
                """
                INSERT INTO member_points (user_id, guild_id, total_points, last_update)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, guild_id) DO UPDATE SET
                    total_points = total_points + ?,
                    last_update = CURRENT_TIMESTAMP
                """,
                (str(user_id), str(guild_id), delta, delta)
            )
            # Busca novo total
            await cur.execute(
                """
                SELECT total_points FROM member_points
                WHERE guild_id = ? AND user_id = ?
                """,
                (str(guild_id), str(user_id))
            )
            row = await cur.fetchone()
        await self._conn.commit()
        return row[0] if row else 0
    
    async def get_member_adv_count(self, guild_id: int, user_id: int) -> int:
        """Conta quantas advertências (ADV1 + ADV2) um membro tem baseado nos cargos.
        
        Nota: Este método não acessa o banco, mas sim verifica os cargos do membro.
        Deve ser chamado com um objeto Member do Discord.
        """
        # Este método será implementado no FichaCog onde temos acesso ao Member
        # Retornamos 0 aqui como placeholder
        return 0

    # ===== MÉTODOS DE USER ANALYTICS =====
    
    async def batch_upsert_user_analytics(self, updates_list: list) -> None:
        """Salva múltiplas atualizações de analytics em lote usando transação.
        
        Args:
            updates_list: Lista de dicts com formato:
                {
                    "guild_id": int,
                    "user_id": int,
                    "msg_count": int (delta),
                    "img_count": int (delta),
                    "mentions_sent": int (delta),
                    "mentions_received": int (delta),
                    "reactions_given": int (delta),
                    "reactions_received": int (delta),
                    "last_active": str (timestamp opcional)
                }
        """
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        if not updates_list:
            return
        
        async with self._conn.cursor() as cur:
            # Inicia transação
            await cur.execute("BEGIN TRANSACTION")
            
            try:
                for update in updates_list:
                    guild_id = str(update["guild_id"])
                    user_id = str(update["user_id"])
                    
                    # Busca dados existentes
                    await cur.execute(
                        """
                        SELECT msg_count, img_count, mentions_sent, mentions_received,
                               reactions_given, reactions_received, last_active
                        FROM user_analytics
                        WHERE guild_id = ? AND user_id = ?
                        """,
                        (guild_id, user_id)
                    )
                    existing = await cur.fetchone()
                    
                    if existing:
                        # Atualiza valores existentes (soma deltas)
                        msg_count = existing[0] + update.get("msg_count", 0)
                        img_count = existing[1] + update.get("img_count", 0)
                        mentions_sent = existing[2] + update.get("mentions_sent", 0)
                        mentions_received = existing[3] + update.get("mentions_received", 0)
                        reactions_given = existing[4] + update.get("reactions_given", 0)
                        reactions_received = existing[5] + update.get("reactions_received", 0)
                        last_active = update.get("last_active") or existing[6]
                        
                        # Garante valores não negativos
                        msg_count = max(0, msg_count)
                        img_count = max(0, img_count)
                        mentions_sent = max(0, mentions_sent)
                        mentions_received = max(0, mentions_received)
                        reactions_given = max(0, reactions_given)
                        reactions_received = max(0, reactions_received)
                        
                        await cur.execute(
                            """
                            UPDATE user_analytics
                            SET msg_count = ?, img_count = ?, mentions_sent = ?,
                                mentions_received = ?, reactions_given = ?,
                                reactions_received = ?, last_active = ?
                            WHERE guild_id = ? AND user_id = ?
                            """,
                            (msg_count, img_count, mentions_sent, mentions_received,
                             reactions_given, reactions_received, last_active,
                             guild_id, user_id)
                        )
                    else:
                        # Insere novo registro
                        msg_count = max(0, update.get("msg_count", 0))
                        img_count = max(0, update.get("img_count", 0))
                        mentions_sent = max(0, update.get("mentions_sent", 0))
                        mentions_received = max(0, update.get("mentions_received", 0))
                        reactions_given = max(0, update.get("reactions_given", 0))
                        reactions_received = max(0, update.get("reactions_received", 0))
                        last_active = update.get("last_active") or "CURRENT_TIMESTAMP"
                        
                        if last_active == "CURRENT_TIMESTAMP":
                            await cur.execute(
                                """
                                INSERT INTO user_analytics (
                                    guild_id, user_id, msg_count, img_count,
                                    mentions_sent, mentions_received,
                                    reactions_given, reactions_received, last_active
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                                """,
                                (guild_id, user_id, msg_count, img_count,
                                 mentions_sent, mentions_received,
                                 reactions_given, reactions_received)
                            )
                        else:
                            await cur.execute(
                                """
                                INSERT INTO user_analytics (
                                    guild_id, user_id, msg_count, img_count,
                                    mentions_sent, mentions_received,
                                    reactions_given, reactions_received, last_active
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (guild_id, user_id, msg_count, img_count,
                                 mentions_sent, mentions_received,
                                 reactions_given, reactions_received, last_active)
                            )
                
                # Commit da transação
                await cur.execute("COMMIT")
            except Exception as e:
                await cur.execute("ROLLBACK")
                raise
    
    async def get_user_analytics(self, guild_id: int, user_id: int) -> Optional[Dict[str, Any]]:
        """Busca dados de analytics de um usuário."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM user_analytics
                WHERE guild_id = ? AND user_id = ?
                """,
                (str(guild_id), str(user_id))
            )
            row = await cur.fetchone()
            return dict(row) if row else None
    
    async def get_top_users_by_messages(
        self, guild_id: int, limit: int = 10, offset: int = 0
    ) -> Tuple[Dict[str, Any], ...]:
        """Retorna top N usuários por mensagens com paginação."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM user_analytics
                WHERE guild_id = ?
                ORDER BY msg_count DESC
                LIMIT ? OFFSET ?
                """,
                (str(guild_id), limit, offset)
            )
            rows = await cur.fetchall()
            return tuple(dict(row) for row in rows)
    
    async def get_server_avg_messages(self, guild_id: int) -> float:
        """Retorna média de mensagens do servidor (para cálculo de temperatura)."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT AVG(msg_count) FROM user_analytics
                WHERE guild_id = ? AND msg_count > 0
                """,
                (str(guild_id),)
            )
            row = await cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
    
    async def update_rankings(self, guild_id: int) -> None:
        """Recalcula e atualiza rank_position para todos os usuários do servidor."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            # Usa ROW_NUMBER() para calcular ranking baseado em msg_count
            await cur.execute(
                """
                UPDATE user_analytics
                SET rank_position = (
                    SELECT rank_pos FROM (
                        SELECT user_id,
                               ROW_NUMBER() OVER (ORDER BY msg_count DESC, last_active DESC) as rank_pos
                        FROM user_analytics
                        WHERE guild_id = ?
                    ) ranked
                    WHERE ranked.user_id = user_analytics.user_id
                )
                WHERE guild_id = ?
                """,
                (str(guild_id), str(guild_id))
            )
        await self._conn.commit()
    
    async def get_user_rank(self, guild_id: int, user_id: int) -> Optional[int]:
        """Retorna posição no ranking (usa rank_position ou calcula se NULL)."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            # Primeiro tenta usar rank_position cacheado
            await cur.execute(
                """
                SELECT rank_position FROM user_analytics
                WHERE guild_id = ? AND user_id = ?
                """,
                (str(guild_id), str(user_id))
            )
            row = await cur.fetchone()
            
            if row and row[0] is not None:
                return int(row[0])
            
            # Se não tiver cacheado, calcula na hora
            await cur.execute(
                """
                SELECT COUNT(*) + 1 FROM user_analytics
                WHERE guild_id = ? AND (
                    msg_count > (SELECT msg_count FROM user_analytics WHERE guild_id = ? AND user_id = ?)
                    OR (msg_count = (SELECT msg_count FROM user_analytics WHERE guild_id = ? AND user_id = ?)
                        AND last_active > (SELECT last_active FROM user_analytics WHERE guild_id = ? AND user_id = ?))
                )
                """,
                (str(guild_id), str(guild_id), str(user_id),
                 str(guild_id), str(user_id), str(guild_id), str(user_id))
            )
            row = await cur.fetchone()
            return int(row[0]) if row else None

    # ===== Wizard Progress =====
    
    async def save_wizard_progress(
        self,
        guild_id: int,
        current_step: str,
        selected_modules: Optional[str] = None,
        config_data: Optional[str] = None,
    ) -> None:
        """Salva o progresso do wizard."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO wizard_progress (guild_id, current_step, selected_modules, config_data)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    current_step = excluded.current_step,
                    selected_modules = excluded.selected_modules,
                    config_data = excluded.config_data,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (str(guild_id), current_step, selected_modules, config_data)
            )
        await self._conn.commit()
    
    async def get_wizard_progress(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Recupera o progresso do wizard."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM wizard_progress
                WHERE guild_id = ?
                """,
                (str(guild_id),)
            )
            row = await cur.fetchone()
            return dict(row) if row else None
    
    async def clear_wizard_progress(self, guild_id: int) -> None:
        """Limpa o progresso do wizard."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM wizard_progress WHERE guild_id = ?",
                (str(guild_id),)
            )
        await self._conn.commit()
    
    # ===== Config Backups =====
    
    async def save_backup(self, guild_id: int, backup_data: Dict[str, Any]) -> int:
        """Salva um backup das configurações."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        import json
        backup_json = json.dumps(backup_data)
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO config_backups (guild_id, backup_data)
                VALUES (?, ?)
                """,
                (str(guild_id), backup_json)
            )
            backup_id = cur.lastrowid
        await self._conn.commit()
        return backup_id
    
    async def get_latest_backup(self, guild_id: int) -> Optional[Dict[str, Any]]:
        """Recupera o backup mais recente."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        import json
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM config_backups
                WHERE guild_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (str(guild_id),)
            )
            row = await cur.fetchone()
            if row:
                result = dict(row)
                result["backup_data"] = json.loads(result["backup_data"])
                return result
            return None
    
    async def list_backups(self, guild_id: int, limit: int = 10) -> Tuple[Dict[str, Any], ...]:
        """Lista backups recentes."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        import json
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM config_backups
                WHERE guild_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (str(guild_id), limit)
            )
            rows = await cur.fetchall()
            results = []
            for row in rows:
                result = dict(row)
                result["backup_data"] = json.loads(result["backup_data"])
                results.append(result)
            return tuple(results)
    
    async def delete_backup(self, backup_id: int) -> None:
        """Deleta um backup."""
        if not self._conn:
            raise RuntimeError("Database não inicializado. Chame initialize() primeiro.")
        
        async with self._conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM config_backups WHERE id = ?",
                (backup_id,)
            )
        await self._conn.commit()

    async def close(self) -> None:
        """Fecha a conexão com o banco de dados."""
        if self._conn:
            await self._conn.close()
            self._conn = None
