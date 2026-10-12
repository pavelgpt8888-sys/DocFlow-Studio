"""Запуск графического интерфейса."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QStyleFactory

from ..core import DocFlowEngine
from .main_window import MainWindow
from .theme import ThemeManager


def create_app(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName("DocFlow Studio")
    app.setApplicationDisplayName("DocFlow Studio")
    app.setOrganizationName("DocFlow")
    # Fusion даёт предсказуемую отрисовку под нашу таблицу стилей;
    # шрифт остаётся системным шрифтом macOS (SF Pro).
    app.setStyle(QStyleFactory.create("Fusion"))
    font = QFont(app.font())
    font.setPointSizeF(13)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    app.setFont(font)
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, True)
    return app


def build_window(project_root: Path) -> MainWindow:
    engine = DocFlowEngine(project_root)
    theme = ThemeManager(engine.settings.theme)
    return MainWindow(engine, theme)


def run(project_root: Path) -> int:
    app = create_app()
    window = build_window(project_root)
    window.show()
    window.raise_()
    return app.exec()
