"""Вспомогательные разделы: шаблоны, источники данных, история, настройки."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QFrame, QGridLayout, QHBoxLayout,
                               QHeaderView, QScrollArea, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget)

from .. import __version__
from ..core.history import HistoryEntry
from ..core.models import DataFileInfo, TemplateInfo
from .documents import DOCS, plural
from .widgets import (Banner, Card, EmptyState, IconTile, Segmented, badge, button, icon_label,
                      label, tool_button)

TEMPLATE_ICONS = {"receipt": "receipt", "invoice": "invoice", "certificate": "certificate"}


def template_icon(info: TemplateInfo) -> str:
    return TEMPLATE_ICONS.get(info.icon, "documents")


class PageBase(QWidget):
    def __init__(self, title: str, subtitle: str):
        super().__init__()
        self.setObjectName("Page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("Page")
        scroll.setWidget(body)
        outer.addWidget(scroll)
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(28, 24, 28, 28)
        self.body.setSpacing(16)
        head = QHBoxLayout()
        head.setSpacing(8)
        titles = QVBoxLayout()
        titles.setSpacing(4)
        titles.addWidget(label(title, "PageTitle"))
        titles.addWidget(label(subtitle, "PageSubtitle", wrap=True))
        head.addLayout(titles, 1)
        self.head_actions = QHBoxLayout()
        self.head_actions.setSpacing(8)
        head.addLayout(self.head_actions)
        self.body.addLayout(head)


def _clear(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear(item.layout())


# ===================================================================== шаблоны


class TemplateCard(Card):
    chosen = Signal(object)

    def __init__(self, info: TemplateInfo, selected: bool):
        super().__init__(padding=18, spacing=10, hover=True)
        if selected:
            self.setObjectName("CardSelected")
        self.info = info
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(IconTile(template_icon(info), 40, 20))
        names = QVBoxLayout()
        names.setSpacing(1)
        names.addWidget(label(info.name, "CardTitle"))
        names.addWidget(label(info.path.name, "Faint"))
        top.addLayout(names, 1)
        if selected:
            top.addWidget(badge("Выбран", "accent"), 0, Qt.AlignmentFlag.AlignTop)
        self.layout_.addLayout(top)
        if info.description:
            self.layout_.addWidget(label(info.description, "Muted", wrap=True))
        chips = QHBoxLayout()
        chips.setSpacing(6)
        chips.addWidget(badge(info.page_label))
        chips.addWidget(badge(f"Полей: {len(info.required)}"))
        if info.computed:
            chips.addWidget(badge("Расчёт итогов", "success"))
        chips.addStretch(1)
        self.layout_.addLayout(chips)
        fields = label("Поля из данных: " + (", ".join(info.required) or "—"), "Small", wrap=True)
        self.layout_.addWidget(fields)
        if info.computed:
            self.layout_.addWidget(label("Вычисляются: " + ", ".join(info.computed), "Faint", wrap=True))
        self.layout_.addStretch(1)
        use = button("Использовать" if not selected else "Используется", "check" if selected else None,
                     None if selected else "primary")
        use.setEnabled(not selected)
        use.clicked.connect(lambda: self.chosen.emit(self.info))
        self.layout_.addWidget(use, 0, Qt.AlignmentFlag.AlignLeft)


class TemplatesPage(PageBase):
    template_chosen = Signal(object)
    open_folder = Signal()
    refresh = Signal()

    def __init__(self):
        super().__init__("Шаблоны", "HTML-шаблоны из папки templates/ и добавленных папок. "
                                    "Поля подставляются через {{ имя_поля }}.")
        folder = button("Открыть папку", "folder")
        folder.clicked.connect(self.open_folder)
        refresh = tool_button("refresh", "Обновить")
        refresh.clicked.connect(self.refresh)
        self.head_actions.addWidget(folder)
        self.head_actions.addWidget(refresh)
        self.errors = QVBoxLayout()
        self.errors.setSpacing(8)
        self.body.addLayout(self.errors)
        self.grid = QGridLayout()
        self.grid.setSpacing(16)
        self.body.addLayout(self.grid)
        self.body.addStretch(1)
        self._templates: list[TemplateInfo] = []
        self._selected: Path | None = None
        self._columns = 0

    def set_templates(self, templates: list[TemplateInfo], selected: Path | None,
                      errors: dict[Path, str]) -> None:
        self._templates, self._selected = templates, selected
        _clear(self.errors)
        for path, message in errors.items():
            b = Banner()
            b.show_message("danger", f"Шаблон «{path.name}» не загружен", message)
            self.errors.addWidget(b)
        self._rebuild()

    def _rebuild(self) -> None:
        _clear(self.grid)
        width = max(self.width() - 56, 300)
        self._columns = max(1, min(3, width // 320))
        if not self._templates:
            self.grid.addWidget(EmptyState("templates", "Шаблонов пока нет",
                                           "Положите HTML-файл в папку templates/ и нажмите «Обновить»."),
                                0, 0)
            return
        for i, info in enumerate(self._templates):
            card = TemplateCard(info, info.path == self._selected)
            card.chosen.connect(self.template_chosen)
            self.grid.addWidget(card, i // self._columns, i % self._columns)
        for c in range(self._columns):
            self.grid.setColumnStretch(c, 1)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        cols = max(1, min(3, max(self.width() - 56, 300) // 320))
        if cols != self._columns and self._templates:
            self._rebuild()


# ===================================================================== источники


class SourcesPage(PageBase):
    add_folder = Signal()
    remove_folder = Signal(str)
    file_chosen = Signal(object)
    refresh = Signal()

    def __init__(self):
        super().__init__("Источники данных",
                         "Программа ищет CSV и JSON только в папках из этого списка — "
                         "остальной компьютер не сканируется.")
        add = button("Добавить папку", "folder-plus", "primary")
        add.clicked.connect(self.add_folder)
        refresh = tool_button("refresh", "Обновить")
        refresh.clicked.connect(self.refresh)
        self.head_actions.addWidget(add)
        self.head_actions.addWidget(refresh)

        self.folders_card = Card(padding=8, spacing=0)
        self.body.addWidget(label("Папки", "CardTitle"))
        self.body.addWidget(self.folders_card)

        self.body.addSpacing(4)
        self.body.addWidget(label("Найденные файлы", "CardTitle"))
        files_card = Card(padding=0, spacing=0)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Файл", "Папка", "Формат", "Размер"])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.setMinimumHeight(240)
        self.table.cellDoubleClicked.connect(self._on_double)
        self.files_stack = QStackedWidget()
        self.files_empty = EmptyState("inbox", "Файлы не найдены",
                                      "Добавьте папку с CSV или JSON — файлы появятся здесь.")
        self.files_stack.addWidget(self.table)
        self.files_stack.addWidget(self.files_empty)
        files_card.layout_.addWidget(self.files_stack)
        self.body.addWidget(files_card)
        self.body.addWidget(label("Двойной щелчок по файлу открывает его в разделе «Документы».", "Faint"))

        self.body.addSpacing(4)
        self.body.addWidget(label("Недавние файлы", "CardTitle"))
        self.recent_card = Card(padding=8, spacing=0)
        self.body.addWidget(self.recent_card)
        self.body.addStretch(1)
        self._files: list[DataFileInfo] = []

    def _row(self, icon_name: str, title: str, subtitle: str, trailing: list[QWidget]) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(10, 8, 8, 8)
        lay.setSpacing(12)
        lay.addWidget(icon_label(icon_name, "text2", 18))
        texts = QVBoxLayout()
        texts.setSpacing(1)
        texts.addWidget(label(title))
        sub = label(subtitle, "Faint")
        sub.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        texts.addWidget(sub)
        lay.addLayout(texts, 1)
        for t in trailing:
            lay.addWidget(t)
        return w

    def set_state(self, project_data: Path, folders: list[str], files: list[DataFileInfo],
                  recent: list[str]) -> None:
        lay = self.folders_card.layout_
        _clear(lay)
        lay.addWidget(self._row("folder", "Демонстрационные данные", str(project_data),
                                [badge("Проект")]))
        for folder in folders:
            rm = tool_button("trash", "Убрать папку из списка")
            rm.clicked.connect(lambda _=False, f=folder: self.remove_folder.emit(f))
            lay.addWidget(self._row("folder", Path(folder).name, folder,
                                    [badge("Шаблоны и данные"), rm]))

        self._files = files
        self.table.setRowCount(len(files))
        for row, f in enumerate(files):
            size = f"{f.size / 1024:.1f} КБ" if f.size >= 1024 else f"{f.size} Б"
            for col, text in enumerate([f.name, str(f.path.parent.relative_to(f.root))
                                        if f.path.parent != f.root else f.root.name,
                                        f.format.upper(), size]):
                item = QTableWidgetItem(text)
                item.setToolTip(str(f.path))
                self.table.setItem(row, col, item)
        self.files_stack.setCurrentWidget(self.table if files else self.files_empty)
        self.table.setFixedHeight(min(38 * max(len(files), 1) + 40, 420))

        lay = self.recent_card.layout_
        _clear(lay)
        existing = [r for r in recent if Path(r).exists()]
        if not existing:
            lay.addWidget(label("  Здесь появятся файлы, которые вы открывали.", "Faint"))
            lay.itemAt(0).widget().setContentsMargins(10, 10, 10, 10)
        for path in existing[:6]:
            open_btn = button("Открыть", None, "link")
            open_btn.clicked.connect(lambda _=False, p=path: self.file_chosen.emit(Path(p)))
            lay.addWidget(self._row("documents", Path(path).name, str(Path(path).parent), [open_btn]))

    def _on_double(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._files):
            self.file_chosen.emit(self._files[row].path)


# ===================================================================== история


class HistoryPage(PageBase):
    open_folder = Signal(object)
    clear_history = Signal()

    def __init__(self):
        super().__init__("История", "Журнал созданных документов. Значения полей записей "
                                    "в историю не сохраняются.")
        self.clear_btn = button("Очистить", "trash", "ghost")
        self.clear_btn.clicked.connect(self.clear_history)
        self.head_actions.addWidget(self.clear_btn)
        card = Card(padding=0, spacing=0)
        self.stack = QStackedWidget()
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["Дата", "Шаблон", "Данные", "Документы", "Режим", "Статус"])
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setShowGrid(False)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        h = self.table.horizontalHeader()
        for col, mode in enumerate([QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.Stretch,
                                    QHeaderView.ResizeMode.Stretch, QHeaderView.ResizeMode.ResizeToContents,
                                    QHeaderView.ResizeMode.ResizeToContents,
                                    QHeaderView.ResizeMode.ResizeToContents]):
            h.setSectionResizeMode(col, mode)
        self.table.cellDoubleClicked.connect(self._on_double)
        self.empty = EmptyState("history", "История пока пуста",
                                "Здесь появятся созданные документы — с датой, шаблоном и статусом.")
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.table)
        card.layout_.addWidget(self.stack)
        card.setMinimumHeight(420)
        self.body.addWidget(card, 1)
        self.body.addWidget(label("Двойной щелчок по строке открывает папку с результатами.", "Faint"))
        self._entries: list[HistoryEntry] = []
        self.palette = None

    def set_entries(self, entries: list[HistoryEntry]) -> None:
        from PySide6.QtGui import QColor
        self._entries = entries
        self.table.setRowCount(len(entries))
        tones = {"ok": "success", "partial": "warning", "error": "danger", "cancelled": "text2"}
        for row, e in enumerate(entries):
            docs = (f"{e.succeeded} {plural(e.succeeded, DOCS)}" if e.succeeded == e.requested
                    else f"{e.succeeded} из {e.requested}")
            values = [e.created_at.strftime("%d.%m.%Y  %H:%M"), e.template, e.data_file, docs,
                      "Консоль" if e.source == "cli" else "Приложение", "●  " + e.status_label]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                if col == 5 and self.palette:
                    item.setForeground(QColor(getattr(self.palette, tones.get(e.status, "text2"))))
                if col == 0 and self.palette:
                    item.setForeground(QColor(self.palette.text2))
                self.table.setItem(row, col, item)
        self.stack.setCurrentWidget(self.table if entries else self.empty)
        self.clear_btn.setEnabled(bool(entries))

    def _on_double(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._entries):
            self.open_folder.emit(self._entries[row].output_dir)


# ===================================================================== настройки


class SettingsPage(PageBase):
    theme_changed = Signal(str)
    choose_output = Signal()
    reset_output = Signal()
    open_output = Signal()
    auto_open_changed = Signal(bool)

    def __init__(self):
        super().__init__("Настройки", "Оформление, папка результатов и поведение после генерации.")

        appearance = Card(padding=20, spacing=14)
        appearance.layout_.addWidget(label("Оформление", "CardTitle"))
        row = QHBoxLayout()
        row.addWidget(label("Тема интерфейса", "Muted"))
        row.addStretch(1)
        self.theme = Segmented([("system", "Системная", "monitor"), ("light", "Светлая", "sun"),
                                ("dark", "Тёмная", "moon")])
        self.theme.changed.connect(self.theme_changed)
        row.addWidget(self.theme)
        appearance.layout_.addLayout(row)
        self.body.addWidget(appearance)

        output = Card(padding=20, spacing=14)
        output.layout_.addWidget(label("Результаты", "CardTitle"))
        row = QHBoxLayout()
        row.setSpacing(8)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(label("Папка для PDF", "Muted"))
        self.output_path = label("", "Small", wrap=True)
        self.output_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        texts.addWidget(self.output_path)
        row.addLayout(texts, 1)
        b_open = button("Открыть", "external")
        b_open.clicked.connect(self.open_output)
        b_change = button("Изменить…", "folder")
        b_change.clicked.connect(self.choose_output)
        self.b_reset = button("По умолчанию", None, "ghost")
        self.b_reset.clicked.connect(self.reset_output)
        for b in (b_open, b_change, self.b_reset):
            row.addWidget(b)
        output.layout_.addLayout(row)
        self.auto_open = QCheckBox("Автоматически открывать PDF после создания одного документа")
        self.auto_open.toggled.connect(self.auto_open_changed)
        output.layout_.addWidget(self.auto_open)
        output.layout_.addWidget(label("Существующие файлы никогда не перезаписываются: при совпадении "
                                       "имени добавляется номер. Документы не отправляются на печать "
                                       "автоматически.", "Faint", wrap=True))
        self.body.addWidget(output)

        privacy = Card(padding=20, spacing=10)
        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(icon_label("lock", "accent", 18))
        top.addWidget(label("Конфиденциальность", "CardTitle"))
        top.addStretch(1)
        privacy.layout_.addLayout(top)
        privacy.layout_.addWidget(label(
            "Все операции выполняются на этом Mac. DocFlow Studio не делает сетевых запросов: "
            "загрузка внешних ресурсов при создании PDF запрещена, шаблоны не могут выполнять код, "
            "а значения из ваших файлов не попадают в журналы.", "Muted", wrap=True))
        self.body.addWidget(privacy)

        about = Card(padding=20, spacing=6)
        about.layout_.addWidget(label("О программе", "CardTitle"))
        about.layout_.addWidget(label(f"DocFlow Studio {__version__} · PySide6 · WeasyPrint · SQLite",
                                      "Muted"))
        self.storage = label("", "Faint", wrap=True)
        self.storage.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        about.layout_.addWidget(self.storage)
        self.body.addWidget(about)
        self.body.addStretch(1)

    def set_state(self, theme: str, output_dir: Path, custom: bool, auto_open: bool,
                  storage: Path) -> None:
        self.theme.set_value(theme)
        self.output_path.setText(str(output_dir))
        self.b_reset.setVisible(custom)
        self.auto_open.blockSignals(True)
        self.auto_open.setChecked(auto_open)
        self.auto_open.blockSignals(False)
        self.storage.setText(f"Настройки и история: {storage}")
