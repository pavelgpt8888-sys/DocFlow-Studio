from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from docflow.core import DocFlowEngine  # noqa: E402
from docflow.core.history import History  # noqa: E402
from docflow.core.settings import Settings  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Настройки и история каждого теста живут во временной папке."""
    monkeypatch.setenv("DOCFLOW_HOME", str(tmp_path / "home"))
    return tmp_path / "home"


@pytest.fixture
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture
def engine(tmp_path) -> DocFlowEngine:
    settings = Settings.load(tmp_path / "home" / "settings.json")
    settings.output_dir = str(tmp_path / "output")
    history = History(tmp_path / "home" / "history.sqlite3")
    return DocFlowEngine(PROJECT_ROOT, settings, history)


def write(path: Path, content: str | bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8")
    return path
