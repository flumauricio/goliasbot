import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


LOGGER = logging.getLogger(__name__)


class Database:
    """Wrapper simples para SQLite com migração inicial."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self.migrate()

    def migrate(self) -> None:
        cur = self._conn.cursor()
        cur.execute(
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
        cur.execute(
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
        cur.execute("PRAGMA table_info(settings)")
        cols = [row[1] for row in cur.fetchall()]
        if "channel_welcome" not in cols:
            cur.execute("ALTER TABLE settings ADD COLUMN channel_welcome TEXT")
        if "channel_warnings" not in cols:
            cur.execute("ALTER TABLE settings ADD COLUMN channel_warnings TEXT")
        if "channel_leaves" not in cols:
            cur.execute("ALTER TABLE settings ADD COLUMN channel_leaves TEXT")
        if "role_adv1" not in cols:
            cur.execute("ALTER TABLE settings ADD COLUMN role_adv1 TEXT")
        if "role_adv2" not in cols:
            cur.execute("ALTER TABLE settings ADD COLUMN role_adv2 TEXT")

        # Permissões de comandos por guild
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS command_permissions (
                guild_id TEXT NOT NULL,
                command_name TEXT NOT NULL,
                role_ids TEXT NOT NULL,
                PRIMARY KEY (guild_id, command_name)
            )
            """
        )

        self._conn.commit()
        LOGGER.info("Migrações aplicadas em %s", self.path)

    def upsert_settings(
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
        existing = self.get_settings(guild_id)
        merged = {**existing, **{k: v for k, v in data.items() if v is not None}}
        cur = self._conn.cursor()
        # updated_at usa o DEFAULT na inserção; é atualizado apenas no UPDATE
        cur.execute(
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
        self._conn.commit()

    def get_settings(self, guild_id: int) -> Dict[str, Any]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM settings WHERE guild_id = ?", (str(guild_id),))
        row = cur.fetchone()
        if not row:
            return {}
        return dict(row)

    def create_registration(
        self,
        *,
        guild_id: int,
        user_id: int,
        user_name: str,
        server_id: str,
        recruiter_id: str,
        approval_message_id: Optional[int] = None,
    ) -> int:
        cur = self._conn.cursor()
        cur.execute(
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
        self._conn.commit()
        return int(cur.lastrowid)

    def update_registration_status(
        self,
        registration_id: int,
        status: str,
        *,
        approval_message_id: Optional[int] = None,
    ) -> None:
        cur = self._conn.cursor()
        cur.execute(
            """
            UPDATE registrations
            SET status = ?, approval_message_id = COALESCE(?, approval_message_id), updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, str(approval_message_id) if approval_message_id else None, registration_id),
        )
        self._conn.commit()

    def get_registration_by_message(self, approval_message_id: int) -> Optional[Dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM registrations WHERE approval_message_id = ?", (str(approval_message_id),)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def get_registration(self, registration_id: int) -> Optional[Dict[str, Any]]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM registrations WHERE id = ?", (registration_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def list_pending_registrations(self) -> Tuple[Dict[str, Any], ...]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM registrations WHERE status = 'pending'")
        rows = cur.fetchall()
        return tuple(dict(row) for row in rows)

    # ===== Permissões de comandos =====

    def set_command_permissions(
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
        cur = self._conn.cursor()
        cur.execute(
            """
            INSERT INTO command_permissions (guild_id, command_name, role_ids)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, command_name) DO UPDATE SET
                role_ids = excluded.role_ids
            """,
            (str(guild_id), command_name, role_ids),
        )
        self._conn.commit()

    def get_command_permissions(self, guild_id: int, command_name: str) -> Optional[str]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT role_ids FROM command_permissions WHERE guild_id = ? AND command_name = ?",
            (str(guild_id), command_name),
        )
        row = cur.fetchone()
        if not row:
            return None
        return row["role_ids"]

    def list_command_permissions(self, guild_id: int) -> Tuple[Dict[str, Any], ...]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT command_name, role_ids FROM command_permissions WHERE guild_id = ?",
            (str(guild_id),),
        )
        rows = cur.fetchall()
        return tuple(dict(row) for row in rows)

    def close(self) -> None:
        self._conn.close()

