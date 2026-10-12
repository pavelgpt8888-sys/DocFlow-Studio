"""Поиск шаблонов и файлов данных только в разрешённых папках."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Iterator

from .data_loader import SUPPORTED_EXTENSIONS
from .models import DataFileInfo

SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", "node_modules", "output",
    ".pytest_cache", ".mypy_cache", ".idea", ".vscode", "build", "dist", "assets",
}
MAX_DEPTH = 6
MAX_FILES = 2000


def _walk(root: Path, extensions: set[str]) -> Iterator[Path]:
    if not root.is_dir():
        return
    root_depth = len(root.parts)
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        if len(current.parts) - root_depth >= MAX_DEPTH:
            dirnames[:] = []
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            if name.startswith(".") or Path(name).suffix.lower() not in extensions:
                continue
            seen += 1
            if seen > MAX_FILES:
                return
            yield current / name


def _unique_roots(roots: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    for root in roots:
        root = Path(root).expanduser().resolve()
        if root not in result:
            result.append(root)
    return result


def find_templates(roots: Iterable[Path]) -> list[Path]:
    found: list[Path] = []
    for root in _unique_roots(roots):
        for path in _walk(root, {".html", ".htm"}):
            if path not in found:
                found.append(path)
    return found


def find_data_files(roots: Iterable[Path]) -> list[DataFileInfo]:
    found: list[DataFileInfo] = []
    seen: set[Path] = set()
    for root in _unique_roots(roots):
        for path in _walk(root, set(SUPPORTED_EXTENSIONS)):
            if path in seen:
                continue
            seen.add(path)
            try:
                size = path.stat().st_size
            except OSError:
                continue
            found.append(DataFileInfo(path, SUPPORTED_EXTENSIONS[path.suffix.lower()], size, root))
    return found
