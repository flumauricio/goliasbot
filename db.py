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
        LOGGER.info("Database inicializado: %s", self.path)

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

        await self._conn.commit()
        LOGGER.info("Migrações aplicadas em %s", self.path)

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
        role_set: Optional[int] = None,
        role_member: Optional[int] = None,
        role_adv1: Optional[int] = None,
        role_adv2: Optional[int] = None,
        message_set_embed: Optional[int] = None,
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
            "role_set": role_set,
            "role_member": role_member,
            "role_adv1": role_adv1,
            "role_adv2": role_adv2,
            "message_set_embed": message_set_embed,
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
                    role_set,
                    role_member,
                    role_adv1,
                    role_adv2,
                    message_set_embed
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_registration_embed=excluded.channel_registration_embed,
                    channel_welcome=excluded.channel_welcome,
                    channel_warnings=excluded.channel_warnings,
                    channel_approval=excluded.channel_approval,
                    channel_records=excluded.channel_records,
                    role_set=excluded.role_set,
                    role_member=excluded.role_member,
                    role_adv1=excluded.role_adv1,
                    role_adv2=excluded.role_adv2,
                    message_set_embed=excluded.message_set_embed,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (
                    str(guild_id),
                    merged.get("channel_registration_embed"),
                    merged.get("channel_welcome"),
                    merged.get("channel_warnings"),
                    merged.get("channel_leaves"),
                    merged.get("channel_approval"),
                    merged.get("channel_records"),
                    merged.get("role_set"),
                    merged.get("role_member"),
                    merged.get("role_adv1"),
                    merged.get("role_adv2"),
                    merged.get("message_set_embed"),
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
        
        async with self._conn.cursor() as cur:
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
    
    async def close(self) -> None:
        """Fecha a conexão com o banco de dados."""
        if self._conn:
            await self._conn.close()
            self._conn = None
