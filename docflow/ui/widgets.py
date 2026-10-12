"""Небольшие переиспользуемые элементы интерфейса."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from .icons import binder


def label(text: str = "", name: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if name:
        lbl.setObjectName(name)
    lbl.setWordWrap(wrap)
    return lbl


def button(text: str, icon_name: str | None = None, variant: str | None = None,
           role: str | None = None, icon_size: int = 16) -> QPushButton:
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if variant:
        btn.setProperty("variant", variant)
    if icon_name:
        default_role = "on_accent" if variant in ("primary", "hero") else "text2"
        binder.bind(btn, icon_name, role or default_role, icon_size)
    return btn


def tool_button(icon_name: str, tooltip: str, size: int = 17) -> QToolButton:
    btn = QToolButton()
    btn.setToolTip(tooltip)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    binder.bind(btn, icon_name, "text2", size)
    return btn


def icon_label(icon_name: str, role: str = "text2", size: int = 18) -> QLabel:
    lbl = QLabel()
    lbl.setFixedSize(size, size)
    binder.bind(lbl, icon_name, role, size)
    return lbl


def badge(text: str, tone: str = "") -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName({"": "Badge", "accent": "BadgeAccent", "success": "BadgeSuccess",
                       "warning": "BadgeWarning", "danger": "BadgeDanger"}[tone])
    lbl.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return lbl


def set_badge(lbl: QLabel, text: str, tone: str = "") -> None:
    lbl.setText(text)
    lbl.setObjectName({"": "Badge", "accent": "BadgeAccent", "success": "BadgeSuccess",
                       "warning": "BadgeWarning", "danger": "BadgeDanger"}[tone])
    repolish(lbl)


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class Card(QFrame):
    def __init__(self, parent=None, padding: int = 16, spacing: int = 12, hover: bool = False):
        super().__init__(parent)
        self.setObjectName("CardHover" if hover else "Card")
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(padding, padding, padding, padding)
        self.layout_.setSpacing(spacing)


class IconTile(QFrame):
    """Квадратная плашка с иконкой — для карточек и пустых состояний."""

    def __init__(self, icon_name: str, size: int = 36, icon_size: int = 18, role: str = "accent"):
        super().__init__()
        self.setObjectName("IconTile")
        self.setFixedSize(size, size)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.icon = icon_label(icon_name, role, icon_size)
        lay.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignCenter)

    def set_icon(self, icon_name: str, role: str = "accent", size: int = 18) -> None:
        binder.bind(self.icon, icon_name, role, size)


class EmptyState(QWidget):
    """Спокойное пустое состояние: иконка, заголовок, пояснение и действие."""

    action_clicked = Signal()

    def __init__(self, icon_name: str, title: str, text: str, action: str | None = None,
                 action_icon: str | None = None):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(32, 32, 32, 32)
        lay.setSpacing(0)
        lay.addStretch(1)
        self.tile = IconTile(icon_name, 52, 24)
        lay.addWidget(self.tile, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(16)
        self.title = label(title, "EmptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self.title)
        lay.addSpacing(6)
        self.text = label(text, "EmptyText", wrap=True)
        self.text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text.setFixedWidth(320)  # фиксированная ширина — корректный перенос строк
        self.text.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        lay.addWidget(self.text, 0, Qt.AlignmentFlag.AlignHCenter)
        self.action = None
        if action:
            lay.addSpacing(18)
            self.action = button(action, action_icon, "primary")
            self.action.clicked.connect(self.action_clicked)
            lay.addWidget(self.action, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(1)

    def set_content(self, icon_name: str, title: str, text: str, show_action: bool = True) -> None:
        self.tile.set_icon(icon_name, "accent", 24)
        self.title.setText(title)
        self.text.setText(text)
        if self.action:
            self.action.setVisible(show_action)


class SearchField(QLineEdit):
    def __init__(self, placeholder: str = "Поиск"):
        super().__init__()
        self.setObjectName("Search")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self._icon = icon_label("search", "text3", 15)
        self._icon.setParent(self)
        self._icon.move(11, 0)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        self._icon.move(11, (self.height() - self._icon.height()) // 2)


class Segmented(QFrame):
    """Сегментированный переключатель (как в системных настройках macOS)."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str, str | None]]):
        super().__init__()
        self.setObjectName("Segmented")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        self.group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        for key, text, icon_name in options:
            btn = QPushButton(text)
            btn.setObjectName("Segment")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            if icon_name:
                binder.bind(btn, icon_name, "text2", 15)
            self.group.addButton(btn)
            self.buttons[key] = btn
            btn.clicked.connect(lambda _=False, k=key: self.changed.emit(k))
            lay.addWidget(btn)

    def set_value(self, key: str) -> None:
        if key in self.buttons:
            self.buttons[key].setChecked(True)


class Banner(QFrame):
    """Плашка с сообщением: успех, предупреждение, ошибка."""

    def __init__(self):
        super().__init__()
        self.setObjectName("Banner")
        self.setProperty("tone", "info")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(10)
        self.icon = icon_label("check-circle", "success", 18)
        lay.addWidget(self.icon, 0, Qt.AlignmentFlag.AlignTop)
        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        self.title = label("", "BannerTitle", wrap=True)
        self.text = label("", "Small", wrap=True)
        text_box.addWidget(self.title)
        text_box.addWidget(self.text)
        lay.addLayout(text_box, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(4)
        lay.addLayout(self.actions)

    def show_message(self, tone: str, title: str, text: str = "") -> None:
        icon_name, role = {
            "success": ("check-circle", "success"), "warning": ("alert", "warning"),
            "danger": ("alert-circle", "danger"), "info": ("sparkle", "accent"),
        }[tone]
        binder.bind(self.icon, icon_name, role, 18)
        self.setProperty("tone", tone)
        repolish(self)
        self.title.setText(title)
        self.text.setText(text)
        self.text.setVisible(bool(text))
        self.show()


def hline() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFixedHeight(1)
    return line
