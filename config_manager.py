import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional


LOGGER = logging.getLogger(__name__)


class ConfigManager:
    """Gerencia leitura e escrita do config.json."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: Dict[str, Any] = {}
        self.reload()

    @property
    def token(self) -> Optional[str]:
        return self._data.get("token")

    def get_guild(self, guild_id: int) -> Dict[str, Any]:
        guilds = self._data.setdefault("guilds", {})
        return guilds.setdefault(str(guild_id), {"channels": {}, "roles": {}, "messages": {}})

    def set_guild_value(self, guild_id: int, section: str, key: str, value: str) -> None:
        guild = self.get_guild(guild_id)
        bucket = guild.setdefault(section, {})
        bucket[key] = value
        self.save()

    def set_token(self, token: str) -> None:
        self._data["token"] = token
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fp:
            json.dump(self._data, fp, indent=2)
        LOGGER.info("Config salvo em %s", self.path)

    def reload(self) -> None:
        if not self.path.exists():
            self._data = {"token": "", "guilds": {}}
            self.save()
            return
        with self.path.open("r", encoding="utf-8") as fp:
            self._data = json.load(fp)

    def guild_channels(self, guild_id: int) -> Dict[str, str]:
        return self.get_guild(guild_id).setdefault("channels", {})

    def guild_roles(self, guild_id: int) -> Dict[str, str]:
        return self.get_guild(guild_id).setdefault("roles", {})

    def guild_messages(self, guild_id: int) -> Dict[str, str]:
        return self.get_guild(guild_id).setdefault("messages", {})

