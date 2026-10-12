"""Палитры светлой и тёмной темы и единая таблица стилей Qt."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPalette


@dataclass(frozen=True)
class Palette:
    name: str
    bg: str
    sidebar: str
    card: str
    text: str
    text2: str
    text3: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str
    on_accent: str
    border: str
    border_strong: str
    hover: str
    pressed: str
    selection: str
    preview_bg: str
    success: str
    success_soft: str
    warning: str
    warning_soft: str
    danger: str
    danger_soft: str
    scroll: str


LIGHT = Palette(
    name="light",
    bg="#F7F8FA", sidebar="#F1F2F5", card="#FFFFFF",
    text="#171923", text2="#717784", text3="#A0A5B2",
    accent="#5B5FEF", accent_hover="#4E52E3", accent_pressed="#4246D0",
    accent_soft="#EEEEFE", on_accent="#FFFFFF",
    border="#E6E8EE", border_strong="#D6D9E1",
    hover="#EEF0F4", pressed="#E5E7EC", selection="#ECEDFE",
    preview_bg="#EDEFF3",
    success="#1E9E63", success_soft="#E7F6EE",
    warning="#B26A00", warning_soft="#FDF3E1",
    danger="#D23F3F", danger_soft="#FCEBEB",
    scroll="#CDD0D8",
)

DARK = Palette(
    name="dark",
    bg="#111318", sidebar="#0D0F13", card="#1B1E26",
    text="#F5F6F8", text2="#A0A5B2", text3="#6B7080",
    accent="#8588FF", accent_hover="#9598FF", accent_pressed="#7477F0",
    accent_soft="#252848", on_accent="#FFFFFF",
    border="#272B35", border_strong="#343946",
    hover="#232732", pressed="#2A2F3B", selection="#262A4D",
    preview_bg="#0B0D11",
    success="#4CC38A", success_soft="#15291F",
    warning="#E5A84B", warning_soft="#2E2414",
    danger="#F07171", danger_soft="#35191C",
    scroll="#3A3F4C",
)


def build_stylesheet(p: Palette) -> str:
    return f"""
* {{
    outline: none;
}}
QWidget {{
    color: {p.text};
    font-size: 13px;
    selection-background-color: {p.selection};
    selection-color: {p.text};
}}
QMainWindow, #Root, #Pages, #Page {{
    background: {p.bg};
}}
QToolTip {{
    background: {p.card};
    color: {p.text};
    border: 1px solid {p.border_strong};
    border-radius: 6px;
    padding: 5px 8px;
}}

/* ---------- Боковая панель ---------- */
#Sidebar {{
    background: {p.sidebar};
    border-right: 1px solid {p.border};
}}
#AppTitle {{
    font-size: 15px;
    font-weight: 700;
}}
#AppSubtitle {{
    color: {p.text3};
    font-size: 11px;
}}
#SectionLabel {{
    color: {p.text3};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
}}
QPushButton#NavButton {{
    text-align: left;
    padding: 0 10px;
    min-height: 32px;
    max-height: 32px;
    border: none;
    border-radius: 7px;
    background: transparent;
    color: {p.text2};
    font-weight: 500;
}}
QPushButton#NavButton:hover {{
    background: {p.hover};
    color: {p.text};
}}
QPushButton#NavButton:checked {{
    background: {p.card};
    color: {p.text};
    font-weight: 600;
    border: 1px solid {p.border};
}}
QListWidget#TemplateList {{
    background: transparent;
    border: none;
}}
QListWidget#TemplateList::item {{
    border-radius: 7px;
    padding: 6px 8px;
    margin: 1px 0;
    color: {p.text2};
}}
QListWidget#TemplateList::item:hover {{
    background: {p.hover};
    color: {p.text};
}}
QListWidget#TemplateList::item:selected {{
    background: {p.accent_soft};
    color: {p.accent};
}}

/* ---------- Заголовки и текст ---------- */
#PageTitle {{
    font-size: 22px;
    font-weight: 700;
}}
#PageSubtitle, #Muted {{
    color: {p.text2};
}}
#Small {{
    color: {p.text2};
    font-size: 12px;
}}
#Warning {{
    color: {p.warning};
    font-size: 12px;
}}
#Faint {{
    color: {p.text3};
    font-size: 12px;
}}
#CardTitle {{
    font-size: 14px;
    font-weight: 600;
}}
#PanelTitle {{
    font-size: 14px;
    font-weight: 600;
}}

/* ---------- Карточки ---------- */
#Card {{
    background: {p.card};
    border: 1px solid {p.border};
    border-radius: 12px;
}}
#CardHover {{
    background: {p.card};
    border: 1px solid {p.border};
    border-radius: 12px;
}}
#CardHover:hover {{
    border-color: {p.border_strong};
}}
#CardSelected {{
    background: {p.card};
    border: 1.5px solid {p.accent};
    border-radius: 12px;
}}
#PreviewPanel {{
    background: {p.card};
    border-left: 1px solid {p.border};
}}
#PreviewSurface {{
    background: {p.preview_bg};
    border: 1px solid {p.border};
    border-radius: 10px;
}}
#IconTile {{
    background: {p.accent_soft};
    border-radius: 9px;
}}
#LogoMark {{
    background: {p.accent};
    border-radius: 8px;
    color: {p.on_accent};
    font-weight: 800;
    font-size: 12px;
}}

/* ---------- Кнопки ---------- */
QPushButton {{
    background: {p.card};
    border: 1px solid {p.border_strong};
    border-radius: 8px;
    padding: 0 12px;
    min-height: 32px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {p.hover};
}}
QPushButton:pressed {{
    background: {p.pressed};
}}
QPushButton:disabled {{
    color: {p.text3};
    background: {p.bg};
    border-color: {p.border};
}}
QPushButton[variant="primary"] {{
    background: {p.accent};
    color: {p.on_accent};
    border: 1px solid {p.accent};
    font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{
    background: {p.accent_hover};
    border-color: {p.accent_hover};
}}
QPushButton[variant="primary"]:pressed {{
    background: {p.accent_pressed};
}}
QPushButton[variant="primary"]:disabled {{
    background: {p.border};
    border-color: {p.border};
    color: {p.text3};
}}
QPushButton[variant="hero"] {{
    background: {p.accent};
    color: {p.on_accent};
    border: none;
    border-radius: 10px;
    min-height: 46px;
    font-size: 15px;
    font-weight: 650;
}}
QPushButton[variant="hero"]:hover {{
    background: {p.accent_hover};
}}
QPushButton[variant="hero"]:pressed {{
    background: {p.accent_pressed};
}}
QPushButton[variant="hero"]:disabled {{
    background: {p.border};
    color: {p.text3};
}}
QPushButton[variant="ghost"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {p.text2};
}}
QPushButton[variant="ghost"]:hover {{
    background: {p.hover};
    color: {p.text};
}}
QPushButton[variant="ghost"]:disabled {{
    color: {p.text3};
}}
QPushButton[variant="link"] {{
    background: transparent;
    border: none;
    color: {p.accent};
    padding: 0 4px;
    min-height: 24px;
    font-weight: 600;
}}
QPushButton[variant="link"]:hover {{
    color: {p.accent_hover};
    text-decoration: underline;
}}
QPushButton[variant="danger"] {{
    color: {p.danger};
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    min-width: 30px;
    min-height: 30px;
    max-height: 30px;
    padding: 0;
}}
QToolButton:hover {{
    background: {p.hover};
}}
QToolButton:pressed {{
    background: {p.pressed};
}}
QToolButton:disabled {{
    color: {p.text3};
}}

/* Сегментированный переключатель */
#Segmented {{
    background: {p.bg};
    border: 1px solid {p.border};
    border-radius: 9px;
}}
QPushButton#Segment {{
    background: transparent;
    border: none;
    border-radius: 7px;
    min-height: 28px;
    padding: 0 14px;
    color: {p.text2};
}}
QPushButton#Segment:checked {{
    background: {p.card};
    color: {p.text};
    font-weight: 600;
    border: 1px solid {p.border};
}}

/* ---------- Поля ввода ---------- */
QLineEdit, QComboBox {{
    background: {p.card};
    border: 1px solid {p.border_strong};
    border-radius: 8px;
    padding: 0 10px;
    min-height: 32px;
}}
QLineEdit:focus, QComboBox:focus, QComboBox:on {{
    border: 1px solid {p.accent};
}}
QLineEdit#Search {{
    padding-left: 32px;
}}
QComboBox::drop-down {{
    border: none;
    width: 26px;
}}
QComboBox::down-arrow {{
    image: url(__CHEVRON__);
    width: 14px;
    height: 14px;
}}
QComboBox QAbstractItemView {{
    background: {p.card};
    border: 1px solid {p.border_strong};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {p.selection};
    selection-color: {p.text};
}}
QCheckBox {{
    spacing: 8px;
}}
QCheckBox::indicator, QTableView::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 5px;
    border: 1.5px solid {p.border_strong};
    background: {p.card};
}}
QCheckBox::indicator:hover, QTableView::indicator:hover {{
    border-color: {p.accent};
}}
QCheckBox::indicator:checked, QTableView::indicator:checked {{
    background: {p.accent};
    border-color: {p.accent};
    image: url(__CHECK__);
}}
QCheckBox::indicator:indeterminate {{
    background: {p.accent};
    border-color: {p.accent};
    image: url(__DASH__);
}}

/* ---------- Таблицы ---------- */
QTableView {{
    background: {p.card};
    border: none;
    gridline-color: transparent;
    alternate-background-color: {p.card};
}}
QTableView::item {{
    border-bottom: 1px solid {p.border};
    padding: 0 10px;
}}
QTableView::item:hover {{
    background: {p.hover};
}}
QTableView::item:selected {{
    background: {p.selection};
    color: {p.text};
}}
QHeaderView {{
    background: {p.card};
    border: none;
}}
QHeaderView::section {{
    background: {p.card};
    color: {p.text2};
    font-size: 12px;
    font-weight: 600;
    border: none;
    border-bottom: 1px solid {p.border_strong};
    padding: 0 10px;
    min-height: 34px;
}}
QTableCornerButton::section {{
    background: {p.card};
    border: none;
}}

/* ---------- Прокрутка ---------- */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {p.scroll};
    border-radius: 3px;
    min-height: 28px;
    min-width: 28px;
}}
QScrollBar::handle:hover {{
    background: {p.text3};
}}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
    border: none;
    width: 0;
    height: 0;
}}

/* ---------- Метки состояния ---------- */
#Badge {{
    background: {p.hover};
    color: {p.text2};
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
#BadgeAccent {{
    background: {p.accent_soft};
    color: {p.accent};
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
#BadgeSuccess {{
    background: {p.success_soft};
    color: {p.success};
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
#BadgeWarning {{
    background: {p.warning_soft};
    color: {p.warning};
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
#BadgeDanger {{
    background: {p.danger_soft};
    color: {p.danger};
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}
#Banner[tone="success"] {{
    background: {p.success_soft};
    border-radius: 10px;
}}
#Banner[tone="warning"] {{
    background: {p.warning_soft};
    border-radius: 10px;
}}
#Banner[tone="danger"] {{
    background: {p.danger_soft};
    border-radius: 10px;
}}
#Banner[tone="info"] {{
    background: {p.accent_soft};
    border-radius: 10px;
}}
#BannerTitle {{
    font-weight: 600;
}}
#EmptyTitle {{
    font-size: 15px;
    font-weight: 600;
}}
#EmptyText {{
    color: {p.text2};
}}
#ZoomLabel {{
    color: {p.text2};
    font-size: 12px;
    min-width: 44px;
}}

QProgressBar {{
    background: {p.hover};
    border: none;
    border-radius: 3px;
    max-height: 6px;
    min-height: 6px;
}}
QProgressBar::chunk {{
    background: {p.accent};
    border-radius: 3px;
}}
QSplitter::handle {{
    background: transparent;
}}
QDialog {{
    background: {p.bg};
}}
QMenu {{
    background: {p.card};
    border: 1px solid {p.border_strong};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 14px;
    border-radius: 5px;
}}
QMenu::item:selected {{
    background: {p.selection};
}}
QMessageBox {{
    background: {p.card};
}}
"""


class ThemeManager(QObject):
    """Хранит выбранный режим и сообщает об изменении темы."""

    changed = Signal(object)  # Palette

    def __init__(self, mode: str = "system"):
        super().__init__()
        self.mode = mode
        self.palette = self._resolve()
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorSchemeChanged"):
            hints.colorSchemeChanged.connect(self._on_system_change)

    def _system_is_dark(self) -> bool:
        hints = QGuiApplication.styleHints()
        if hasattr(hints, "colorScheme"):
            return hints.colorScheme() == Qt.ColorScheme.Dark
        return False

    def _resolve(self) -> Palette:
        if self.mode == "dark":
            return DARK
        if self.mode == "light":
            return LIGHT
        return DARK if self._system_is_dark() else LIGHT

    def set_mode(self, mode: str) -> None:
        self.mode = mode
        self._apply()

    def _on_system_change(self, *_):
        if self.mode == "system":
            self._apply()

    def _apply(self) -> None:
        new = self._resolve()
        if new != self.palette:
            self.palette = new
            self.changed.emit(new)
        else:
            self.changed.emit(new)


def qt_palette(p: Palette) -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(p.bg))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(p.text))
    pal.setColor(QPalette.ColorRole.Base, QColor(p.card))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(p.bg))
    pal.setColor(QPalette.ColorRole.Text, QColor(p.text))
    pal.setColor(QPalette.ColorRole.Button, QColor(p.card))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(p.text))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(p.selection))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(p.text))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(p.text3))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(p.card))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(p.text))
    pal.setColor(QPalette.ColorRole.Link, QColor(p.accent))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(p.text3))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(p.text3))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(p.text3))
    return pal
