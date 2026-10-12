"""Настройки приложения в JSON-файле в папке пользователя."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "DocFlow Studio"
MAX_RECENT = 10
_SAVE_LOCK = threading.Lock()


def app_home() -> Path:
    """Папка для настроек и истории. Переопределяется переменной DOCFLOW_HOME."""
    override = os.environ.get("DOCFLOW_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / "Library" / "Application Support" / APP_NAME


@dataclass
class Settings:
    theme: str = "system"  # system | light | dark
    output_dir: str = ""  # пусто — папка output/ проекта
    auto_open_single: bool = True
    extra_folders: list[str] = field(default_factory=list)
    recent_files: list[str] = field(default_factory=list)
    field_mappings: dict[str, dict[str, str]] = field(default_factory=dict)
    last_template: str = ""
    preview_zoom: float = 1.0

    path: Path | None = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        path = path or app_home() / "settings.json"
        settings = cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                for key, value in data.items():
                    if key in cls.__dataclass_fields__ and key != "path":
                        default = getattr(settings, key)
                        if isinstance(value, type(default)) or (
                            isinstance(default, float) and isinstance(value, int)
                        ):
                            setattr(settings, key, value)
        except (OSError, ValueError):
            pass  # первый запуск или повреждённый файл — работаем со значениями по умолчанию
        settings.path = path
        return settings

    def save(self) -> None:
        if self.path is None:
            return
        # Сохранять могут и интерфейс, и фоновые задачи — пишем по очереди,
        # каждый раз через свой временный файл и атомарную замену.
        with _SAVE_LOCK:
            data = asdict(self)
            data.pop("path", None)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(prefix="settings-", suffix=".tmp", dir=self.path.parent)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)

    def add_recent(self, file_path: Path) -> None:
        value = str(Path(file_path).resolve())
        self.recent_files = [value] + [p for p in self.recent_files if p != value]
        self.recent_files = self.recent_files[:MAX_RECENT]

    def add_folder(self, folder: Path) -> bool:
        value = str(Path(folder).expanduser().resolve())
        if value in self.extra_folders:
            return False
        self.extra_folders.append(value)
        return True

    def remove_folder(self, folder: str) -> None:
        self.extra_folders = [f for f in self.extra_folders if f != folder]

    @staticmethod
    def mapping_key(template_id: str, data_path: Path) -> str:
        return f"{template_id}::{Path(data_path).name}"
