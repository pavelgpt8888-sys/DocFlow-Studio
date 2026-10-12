"""Линейные иконки в едином стиле (контуры в духе Lucide, лицензия ISC).

Иконки описаны как SVG и перекрашиваются под текущую тему.
"""

from __future__ import annotations

import tempfile
import weakref
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QAbstractButton, QLabel

_FILE = '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/>'

PATHS: dict[str, str] = {
    "documents": _FILE + '<path d="M16 13H8"/><path d="M16 17H8"/><path d="M10 9H8"/>',
    "file": _FILE,
    "templates": '<rect width="18" height="7" x="3" y="3" rx="1.5"/><rect width="9" height="7" x="3" y="14" rx="1.5"/><rect width="5" height="7" x="16" y="14" rx="1.5"/>',
    "database": '<ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M3 5V19A9 3 0 0 0 21 19V5"/><path d="M3 12A9 3 0 0 0 21 12"/>',
    "history": '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/><path d="M12 7v5l4 2"/>',
    "settings": '<path d="M21 4h-7"/><path d="M10 4H3"/><path d="M21 12h-9"/><path d="M8 12H3"/><path d="M21 20h-5"/><path d="M12 20H3"/><path d="M14 2v4"/><path d="M8 10v4"/><path d="M16 18v4"/>',
    "receipt": '<path d="M4 2v20l2-1 2 1 2-1 2 1 2-1 2 1 2-1 2 1V2l-2 1-2-1-2 1-2-1-2 1-2-1-2 1Z"/><path d="M8 8h8"/><path d="M8 12h8"/><path d="M8 16h5"/>',
    "invoice": _FILE + '<path d="M8 13h2"/><path d="M14 13h2"/><path d="M8 17h2"/><path d="M14 17h2"/>',
    "certificate": '<circle cx="12" cy="8" r="6"/><path d="M15.48 12.89 17 22l-5-3-5 3 1.52-9.11"/>',
    "search": '<circle cx="11" cy="11" r="7.5"/><path d="m21 21-4.3-4.3"/>',
    "plus": '<path d="M5 12h14"/><path d="M12 5v14"/>',
    "folder": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
    "folder-plus": '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/><path d="M12 10v6"/><path d="M9 13h6"/>',
    "file-up": _FILE + '<path d="M12 18v-6"/><path d="m9 15 3-3 3 3"/>',
    "zoom-in": '<circle cx="11" cy="11" r="7.5"/><path d="m21 21-4.3-4.3"/><path d="M11 8v6"/><path d="M8 11h6"/>',
    "zoom-out": '<circle cx="11" cy="11" r="7.5"/><path d="m21 21-4.3-4.3"/><path d="M8 11h6"/>',
    "fit": '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>',
    "check": '<path d="M20 6 9 17l-5-5"/>',
    "check-circle": '<circle cx="12" cy="12" r="10"/><path d="m9 12 2 2 4-4"/>',
    "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    "alert-circle": '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    "moon": '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    "monitor": '<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/>',
    "refresh": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    "external": '<path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>',
    "mapping": '<path d="M8 3 4 7l4 4"/><path d="M4 7h16"/><path d="m16 21 4-4-4-4"/><path d="M20 17H4"/>',
    "trash": '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/>',
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    "download": '<path d="M12 15V3"/><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10 5 5 5-5"/>',
    "eye": '<path d="M2.06 12.35a1 1 0 0 1 0-.7 10.75 10.75 0 0 1 19.88 0 1 1 0 0 1 0 .7 10.75 10.75 0 0 1-19.88 0"/><circle cx="12" cy="12" r="3"/>',
    "table": '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/><path d="M3 15h18"/><path d="M12 3v18"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "chevron-right": '<path d="m9 18 6-6-6-6"/>',
    "dash": '<path d="M6 12h12"/>',
    "sparkle": '<path d="M12 3v4"/><path d="M12 17v4"/><path d="M3 12h4"/><path d="M17 12h4"/><path d="m5.6 5.6 2.8 2.8"/><path d="m15.6 15.6 2.8 2.8"/><path d="m5.6 18.4 2.8-2.8"/><path d="m15.6 8.4 2.8-2.8"/>',
    "lock": '<rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
}


def svg(name: str, color: str, stroke: float = 1.75) -> bytes:
    body = PATHS.get(name, PATHS["file"])
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="{stroke}" stroke-linecap="round" '
        f'stroke-linejoin="round">{body}</svg>'
    ).encode()


def pixmap(name: str, color: str, size: int = 18, stroke: float = 1.75, ratio: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg(name, color, stroke)))
    pm = QPixmap(int(size * ratio), int(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * ratio, size * ratio))
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: str, size: int = 18, disabled: str | None = None) -> QIcon:
    result = QIcon()
    result.addPixmap(pixmap(name, color, size), QIcon.Mode.Normal)
    if disabled:
        result.addPixmap(pixmap(name, disabled, size), QIcon.Mode.Disabled)
    return result


_qss_dir = Path(tempfile.mkdtemp(prefix="docflow-icons-"))


def qss_icon_file(name: str, color: str, stroke: float = 2.5) -> str:
    """Записывает SVG во временный файл для url(...) в таблице стилей."""
    path = _qss_dir / f"{name}-{color.lstrip('#')}.svg"
    if not path.exists():
        path.write_bytes(svg(name, color, stroke))
    return path.as_posix()


class IconBinder:
    """Запоминает, какие иконки каким виджетам назначены, и перекрашивает их при смене темы."""

    def __init__(self):
        self._items: list[tuple[weakref.ref, str, str, int]] = []
        self.palette = None

    def color_for(self, role: str) -> str:
        return getattr(self.palette, role)

    def bind(self, widget, name: str, role: str = "text2", size: int = 18) -> None:
        self._items.append((weakref.ref(widget), name, role, size))
        self._apply(widget, name, role, size)

    def _apply(self, widget, name: str, role: str, size: int) -> None:
        if self.palette is None:
            return
        color = self.color_for(role)
        if isinstance(widget, QLabel):
            widget.setPixmap(pixmap(name, color, size))
        elif isinstance(widget, QAbstractButton):
            widget.setIcon(icon(name, color, size, disabled=self.palette.text3))
            widget.setIconSize(QSize(size, size))

    def refresh(self, palette) -> None:
        self.palette = palette
        alive = []
        for ref, name, role, size in self._items:
            widget = ref()
            if widget is None:
                continue
            try:
                self._apply(widget, name, role, size)
            except RuntimeError:  # C++-объект уже удалён
                continue
            alive.append((ref, name, role, size))
        self._items = alive


binder = IconBinder()
