import json
import logging
from pathlib import Path
from typing import Optional


LOGGER = logging.getLogger(__name__)


class ConfigManager:
    """Gerencia leitura e escrita do config.json. Usado apenas para o token do bot."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._data: dict = {}
        self.reload()

    @property
    def token(self) -> Optional[str]:
        """Retorna o token do bot."""
        return self._data.get("token")

    def set_token(self, token: str) -> None:
        """Define o token do bot."""
        self._data["token"] = token
        self.save()

    def save(self) -> None:
        """Salva o config.json."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fp:
            json.dump(self._data, fp, indent=2)
        LOGGER.info("Config salvo em %s", self.path)

    def reload(self) -> None:
        """Recarrega o config.json do disco."""
        if not self.path.exists():
            self._data = {"token": ""}
            self.save()
            return
        with self.path.open("r", encoding="utf-8") as fp:
            self._data = json.load(fp)

