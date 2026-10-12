"""Взаимодействие с macOS: открыть файл или папку штатными средствами."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def open_path(path: Path) -> bool:
    """Открывает файл в приложении по умолчанию (для PDF — Просмотр). Не печатает."""
    path = Path(path)
    if not path.exists():
        return False
    if sys.platform == "darwin":
        cmd = ["open", str(path)]
    elif sys.platform.startswith("win"):  # pragma: no cover
        import os
        os.startfile(str(path))  # type: ignore[attr-defined]
        return True
    else:  # pragma: no cover
        cmd = ["xdg-open", str(path)]
    try:
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def reveal_in_finder(path: Path) -> bool:
    path = Path(path)
    if sys.platform == "darwin" and path.is_file():
        try:
            subprocess.Popen(["open", "-R", str(path)], stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
            return True
        except OSError:
            return False
    return open_path(path if path.is_dir() else path.parent)
