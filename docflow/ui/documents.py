"""Экран «Документы»: источник данных, таблица записей и панель предпросмотра."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (QAbstractTableModel, QMargins, QModelIndex, QPointF,
                            QSortFilterProxyModel, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QPalette
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView,
                               QLabel, QProgressBar, QSizePolicy, QStackedWidget, QTableView,
                               QVBoxLayout, QWidget)

from ..core.data_loader import search_records
from ..core.models import DataFileInfo, DataSet, Record
from .widgets import (Banner, Card, EmptyState, IconTile, SearchField, badge, button, label,
                      set_badge, tool_button)


def plural(n: int, forms: tuple[str, str, str]) -> str:
    n_abs = abs(n) % 100
    if 11 <= n_abs <= 19:
        return forms[2]
    last = n_abs % 10
    if last == 1:
        return forms[0]
    if 2 <= last <= 4:
        return forms[1]
    return forms[2]


DOCS = ("документ", "документа", "документов")
RECORDS = ("запись", "записи", "записей")


def display_value(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return f"{len(value)} {plural(len(value), ('позиция', 'позиции', 'позиций'))}"
    if isinstance(value, dict):
        for key in ("name", "title", "название"):
            if key in value:
                return str(value[key])
        return ", ".join(str(v) for v in value.values() if not isinstance(v, (list, dict)))
    return str(value)


# ===================================================================== модель


class RecordsModel(QAbstractTableModel):
    checked_changed = Signal()

    def __init__(self):
        super().__init__()
        self.dataset: DataSet | None = None
        self.checked: set[int] = set()
        self.palette = None

    def set_dataset(self, dataset: DataSet | None) -> None:
        self.beginResetModel()
        self.dataset = dataset
        self.checked = set()
        self.endResetModel()
        self.checked_changed.emit()

    def record_at(self, row: int) -> Record | None:
        if self.dataset and 0 <= row < len(self.dataset.records):
            return self.dataset.records[row]
        return None

    def rowCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() or not self.dataset else len(self.dataset.records)

    def columnCount(self, parent=QModelIndex()):  # noqa: N802
        return 0 if parent.isValid() or not self.dataset else len(self.dataset.columns) + 2

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if orientation != Qt.Orientation.Horizontal or not self.dataset:
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            if section == 0:
                return ""
            if section == 1:
                return "№"
            return self.dataset.columns[section - 2]
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        record = self.record_at(index.row())
        if record is None:
            return None
        col = index.column()
        if col == 0:
            if role == Qt.ItemDataRole.CheckStateRole:
                return Qt.CheckState.Checked if record.index in self.checked else Qt.CheckState.Unchecked
            return None
        if col == 1:
            if role == Qt.ItemDataRole.DisplayRole:
                return str(record.index)
            if role == Qt.ItemDataRole.ForegroundRole and self.palette:
                return QColor(self.palette.text3)
            return None
        value = record.values.get(self.dataset.columns[col - 2])
        if role == Qt.ItemDataRole.DisplayRole:
            return display_value(value)
        if role == Qt.ItemDataRole.ToolTipRole:
            text = display_value(value)
            return text if len(text) > 40 else None
        if role == Qt.ItemDataRole.ForegroundRole and isinstance(value, (list, dict)) and self.palette:
            return QColor(self.palette.text2)
        return None

    def flags(self, index):
        base = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 0:
            base |= Qt.ItemFlag.ItemIsUserCheckable
        return base

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):  # noqa: N802
        if index.column() == 0 and role == Qt.ItemDataRole.CheckStateRole:
            record = self.record_at(index.row())
            if record is None:
                return False
            if Qt.CheckState(value) == Qt.CheckState.Checked:
                self.checked.add(record.index)
            else:
                self.checked.discard(record.index)
            self.dataChanged.emit(index, index, [role])
            self.checked_changed.emit()
            return True
        return False

    def set_checked(self, indexes: set[int]) -> None:
        self.checked = set(indexes)
        if self.rowCount():
            self.dataChanged.emit(self.index(0, 0), self.index(self.rowCount() - 1, 0),
                                  [Qt.ItemDataRole.CheckStateRole])
        self.checked_changed.emit()


class RecordsFilter(QSortFilterProxyModel):
    def __init__(self):
        super().__init__()
        self.query = ""
        self._visible: set[int] | None = None

    def set_query(self, query: str) -> None:
        modern = hasattr(self, "beginFilterChange")  # Qt 6.10+
        if modern:
            self.beginFilterChange()
        self.query = query
        model: RecordsModel = self.sourceModel()
        if model.dataset and query.strip():
            self._visible = {r.index for r in search_records(model.dataset, query)}
        else:
            self._visible = None
        if modern:
            self.endFilterChange()
        else:
            self.invalidateFilter()

    def filterAcceptsRow(self, row, parent):  # noqa: N802
        if self._visible is None:
            return True
        record = self.sourceModel().record_at(row)
        return record is not None and record.index in self._visible


# ===================================================================== центр


class DocumentsPage(QWidget):
    data_file_chosen = Signal(object)  # Path
    suggestion_chosen = Signal(object)  # Path подходящего файла
    open_file_requested = Signal()
    refresh_requested = Signal()
    mapping_requested = Signal()
    current_record_changed = Signal(object)  # Record | None
    selection_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("Page")
        self.model = RecordsModel()
        self.proxy = RecordsFilter()
        self.proxy.setSourceModel(self.model)
        self._files: list[DataFileInfo] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 24, 24)
        root.setSpacing(16)

        # Заголовок
        head = QVBoxLayout()
        head.setSpacing(4)
        head.addWidget(label("Документы", "PageTitle"))
        self.subtitle = label("Загрузите данные, выберите записи и создайте PDF одной кнопкой.",
                              "PageSubtitle", wrap=True)
        head.addWidget(self.subtitle)
        root.addLayout(head)

        # Источник данных
        source = Card(padding=16, spacing=12)
        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(IconTile("database"))
        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(label("Источник данных", "CardTitle"))
        self.source_hint = label("CSV или JSON", "Small")
        titles.addWidget(self.source_hint)
        row.addLayout(titles, 1)
        self.map_btn = button("Сопоставить поля", "mapping", "ghost")
        self.map_btn.clicked.connect(self.mapping_requested)
        self.map_btn.hide()
        row.addWidget(self.map_btn, 0, Qt.AlignmentFlag.AlignTop)
        refresh = tool_button("refresh", "Обновить список файлов")
        refresh.clicked.connect(self.refresh_requested)
        row.addWidget(refresh, 0, Qt.AlignmentFlag.AlignTop)
        source.layout_.addLayout(row)

        pick = QHBoxLayout()
        pick.setSpacing(8)
        self.combo = QComboBox()
        self.combo.setMinimumWidth(160)
        self.combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo.setPlaceholderText("Выберите файл из папок проекта…")
        self.combo.activated.connect(self._on_combo)
        pick.addWidget(self.combo, 1)
        self.open_btn = button("Открыть…", "file-up")
        self.open_btn.setToolTip("Открыть CSV или JSON с компьютера (⌘O)")
        self.open_btn.clicked.connect(self.open_file_requested)
        pick.addWidget(self.open_btn)
        source.layout_.addLayout(pick)

        self.meta_row = QHBoxLayout()
        self.meta_row.setSpacing(6)
        self.b_format = badge("")
        self.b_encoding = badge("")
        self.b_count = badge("", "accent")
        self.b_fields = badge("", "success")
        for b in (self.b_format, self.b_encoding, self.b_count, self.b_fields):
            self.meta_row.addWidget(b)
        self.meta_row.addStretch(1)
        self.meta_widget = QWidget()
        self.meta_widget.setLayout(self.meta_row)
        self.meta_row.setContentsMargins(0, 0, 0, 0)
        source.layout_.addWidget(self.meta_widget)
        self.meta_widget.hide()
        root.addWidget(source)

        self.banner = Banner()
        self.suggest_row = QHBoxLayout()
        self.suggest_row.setContentsMargins(0, 6, 0, 0)
        self.suggest_row.setSpacing(6)
        self.banner.layout().itemAt(1).layout().addLayout(self.suggest_row)
        self.banner.hide()
        root.addWidget(self.banner)

        # Таблица
        data_card = QFrame()
        data_card.setObjectName("Card")
        dc = QVBoxLayout(data_card)
        dc.setContentsMargins(0, 12, 0, 0)
        dc.setSpacing(10)
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(16, 0, 12, 0)
        toolbar.setSpacing(4)
        self.search = SearchField("Поиск по записям")
        self.search.setMaximumWidth(280)
        self.search.setMinimumWidth(150)
        self.search.textChanged.connect(self._on_search)
        toolbar.addWidget(self.search, 1)
        toolbar.addSpacing(12)
        self.sel_label = label("", "Small")
        toolbar.addWidget(self.sel_label)
        toolbar.addStretch(0)
        self.select_all_btn = button("Выбрать все", "check", "ghost")
        self.select_all_btn.clicked.connect(self.select_all)
        toolbar.addWidget(self.select_all_btn)
        self.clear_btn = button("Снять выбор", "x", "ghost")
        self.clear_btn.clicked.connect(self.clear_selection)
        toolbar.addWidget(self.clear_btn)
        dc.addLayout(toolbar)

        self.stack = QStackedWidget()
        self.table = QTableView()
        self.table.setModel(self.proxy)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.horizontalHeader().setHighlightSections(False)
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.setFrameShape(QFrame.Shape.NoFrame)
        self.table.selectionModel().currentRowChanged.connect(self._on_current)
        self.table.clicked.connect(self._on_click)
        self.model.checked_changed.connect(self._update_selection_label)
        self.model.checked_changed.connect(self.selection_changed)

        self.empty = EmptyState(
            "database", "Данные ещё не загружены",
            "Выберите CSV или JSON в списке выше или откройте файл с компьютера.",
            "Открыть файл", "file-up")
        self.empty.action_clicked.connect(self.open_file_requested)
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.table)
        dc.addWidget(self.stack, 1)
        root.addWidget(data_card, 1)
        self._update_selection_label()

    # ------------------------------------------------------------ источники

    def set_files(self, files: list[DataFileInfo], recent: list[str], current: Path | None) -> None:
        self._files = list(files)
        known = {f.path for f in files}
        for item in recent:
            p = Path(item)
            if p not in known and p.exists():
                self._files.append(DataFileInfo(p, p.suffix.lower().lstrip("."), 0, p.parent))
        self.combo.blockSignals(True)
        self.combo.clear()
        for f in self._files:
            self.combo.addItem(f.relative if f.root.name == "data" else f"{f.name} — {f.root.name}",
                               str(f.path))
        self.combo.setCurrentIndex(-1)
        if current:
            idx = self.combo.findData(str(current))
            if idx < 0:
                self.combo.addItem(current.name, str(current))
                idx = self.combo.count() - 1
            self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)

    def _on_combo(self, index: int) -> None:
        path = self.combo.itemData(index)
        if path:
            self.data_file_chosen.emit(Path(path))

    # ------------------------------------------------------------ данные

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        # В узком окне кнопки выбора показывают только иконку, текст — в подсказке.
        compact = self.width() < 720
        for btn, text in ((self.select_all_btn, "Выбрать все"), (self.clear_btn, "Снять выбор"),
                          (self.map_btn, "Сопоставить поля")):
            btn.setText("" if compact else text)
            btn.setToolTip(text if compact else "")
        if self.model.dataset and self.model.dataset.records:
            QTimer.singleShot(0, self._fit_columns)

    def set_dataset(self, dataset: DataSet | None) -> None:
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self.proxy.set_query("")
        self.model.set_dataset(dataset)
        self.map_btn.setVisible(dataset is not None)
        if dataset is None:
            self.meta_widget.hide()
            self.empty.set_content("database", "Данные ещё не загружены",
                                   "Выберите CSV или JSON в списке выше или откройте файл с компьютера.")
            self.stack.setCurrentWidget(self.empty)
            return
        self.meta_widget.show()
        set_badge(self.b_format, dataset.format.upper())
        enc = {"utf-8": "UTF-8", "utf-8-sig": "UTF-8 BOM", "cp1251": "Windows-1251",
               "utf-16": "UTF-16"}.get(dataset.encoding, dataset.encoding)
        delim = {",": "запятая", ";": "точка с запятой", "\t": "табуляция", "|": "черта"}.get(
            dataset.delimiter or "", "")
        set_badge(self.b_encoding, f"{enc} · {delim}" if delim else enc)
        n = len(dataset)
        set_badge(self.b_count, f"{n} {plural(n, RECORDS)}", "accent")
        if not dataset.records:
            self.empty.set_content("inbox", "В файле нет записей",
                                   "Файл прочитан, но строк с данными в нём нет. Добавьте записи "
                                   "или выберите другой файл.", show_action=False)
            self.stack.setCurrentWidget(self.empty)
        else:
            self.stack.setCurrentWidget(self.table)
            self._fit_columns()
            self.table.selectRow(0)

    def _fit_columns(self) -> None:
        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setMinimumSectionSize(36)
        self.table.resizeColumnsToContents()
        self.table.setColumnWidth(0, 40)
        self.table.setColumnWidth(1, 44)
        widths = {col: min(max(self.table.columnWidth(col) + 16, 70), 360)
                  for col in range(2, self.model.columnCount())}
        available = self.table.viewport().width() - 84
        # Если колонки не помещаются, сначала сужаем самые широкие (длинные названия).
        while sum(widths.values()) > available and max(widths.values(), default=0) > 160:
            widest = max(widths, key=widths.get)
            widths[widest] -= 10
        for col, width in widths.items():
            self.table.setColumnWidth(col, width)

    def show_validation(self, missing: list[str], ok_text: str | None, title: str = "",
                        text: str = "", suggestions: list[DataFileInfo] | None = None) -> None:
        while self.suggest_row.count():
            item = self.suggest_row.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if missing:
            set_badge(self.b_fields, f"Не хватает полей: {len(missing)}", "warning")
            self.banner.show_message("warning", title, text)
            for f in (suggestions or [])[:3]:
                b = button(f.name, "documents", None, icon_size=14)
                b.setToolTip(f"Открыть подходящий файл {f.relative}")
                b.clicked.connect(lambda _=False, p=f.path: self.suggestion_chosen.emit(p))
                self.suggest_row.addWidget(b)
            manual = button("Сопоставить вручную", "mapping", "ghost", icon_size=14)
            manual.clicked.connect(self.mapping_requested)
            self.suggest_row.addWidget(manual)
            self.suggest_row.addStretch(1)
        else:
            self.banner.hide()
            if ok_text:
                set_badge(self.b_fields, ok_text, "success")
        self.b_fields.setVisible(bool(missing) or bool(ok_text))

    def show_load_error(self, message: str) -> None:
        self.model.set_dataset(None)
        self.meta_widget.hide()
        self.map_btn.hide()
        self.empty.set_content("alert-circle", "Не удалось загрузить файл", message, show_action=True)
        self.stack.setCurrentWidget(self.empty)
        self.banner.hide()

    # ------------------------------------------------------------ выбор

    def _on_search(self, text: str) -> None:
        self.proxy.set_query(text)
        if self.model.dataset and self.model.dataset.records:
            if self.proxy.rowCount() == 0:
                self.empty.set_content("search", "Ничего не найдено",
                                       "Попробуйте изменить запрос или очистить поиск.",
                                       show_action=False)
                self.stack.setCurrentWidget(self.empty)
            else:
                self.stack.setCurrentWidget(self.table)
                if not self.table.currentIndex().isValid():
                    self.table.selectRow(0)
        self._update_selection_label()

    def _on_current(self, current: QModelIndex, _previous=None) -> None:
        record = self.model.record_at(self.proxy.mapToSource(current).row()) if current.isValid() else None
        self.current_record_changed.emit(record)

    def _on_click(self, index: QModelIndex) -> None:
        # Щелчок по ячейке «№» тоже переключает отметку — так удобнее попадать.
        if index.column() == 1:
            src = self.proxy.mapToSource(index)
            record = self.model.record_at(src.row())
            if record:
                state = Qt.CheckState.Unchecked if record.index in self.model.checked else Qt.CheckState.Checked
                self.model.setData(self.model.index(src.row(), 0), state.value,
                                   Qt.ItemDataRole.CheckStateRole)

    def visible_records(self) -> list[Record]:
        result = []
        for row in range(self.proxy.rowCount()):
            src = self.proxy.mapToSource(self.proxy.index(row, 0))
            record = self.model.record_at(src.row())
            if record:
                result.append(record)
        return result

    def select_all(self) -> None:
        self.model.set_checked(self.model.checked | {r.index for r in self.visible_records()})

    def clear_selection(self) -> None:
        self.model.set_checked(set())

    def current_record(self) -> Record | None:
        idx = self.table.currentIndex()
        if not idx.isValid() or self.stack.currentWidget() is not self.table:
            return None
        return self.model.record_at(self.proxy.mapToSource(idx).row())

    def checked_records(self) -> list[Record]:
        if not self.model.dataset:
            return []
        return [r for r in self.model.dataset.records if r.index in self.model.checked]

    def _update_selection_label(self) -> None:
        ds = self.model.dataset
        has = bool(ds and ds.records)
        for w in (self.select_all_btn, self.clear_btn, self.search):
            w.setEnabled(has)
        self.clear_btn.setEnabled(has and bool(self.model.checked))
        if not has:
            self.sel_label.setText("")
            return
        n = len(self.model.checked)
        shown = self.proxy.rowCount()
        total = len(ds.records)
        found = f"Найдено {shown} из {total} · " if self.proxy.query.strip() else ""
        self.sel_label.setText(f"{found}Выбрано: {n} из {total}")

    def apply_palette(self, palette) -> None:
        self.model.palette = palette
        if self.model.rowCount():
            self.model.dataChanged.emit(self.model.index(0, 1),
                                        self.model.index(self.model.rowCount() - 1,
                                                         self.model.columnCount() - 1))


# ===================================================================== предпросмотр


class PreviewPanel(QFrame):
    generate_clicked = Signal()
    cancel_clicked = Signal()
    open_document = Signal()
    open_folder = Signal()

    ZOOM_STEPS = (0.5, 0.67, 0.75, 0.9, 1.0, 1.1, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)

    def __init__(self):
        super().__init__()
        self.setObjectName("PreviewPanel")
        self.setMinimumWidth(360)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 22, 20, 20)
        root.setSpacing(14)

        head = QHBoxLayout()
        head.setSpacing(4)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        titles.addWidget(label("Предпросмотр", "PanelTitle"))
        self.caption = label("Реальный PDF выбранной записи", "Small")
        self.caption.setMinimumWidth(80)
        self.caption.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        titles.addWidget(self.caption)
        head.addLayout(titles, 1)
        self.zoom_out = tool_button("zoom-out", "Уменьшить")
        self.zoom_label = label("Ширина", "ZoomLabel")
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_in = tool_button("zoom-in", "Увеличить")
        self.fit_btn = tool_button("fit", "По ширине")
        self.zoom_out.clicked.connect(lambda: self.step_zoom(-1))
        self.zoom_in.clicked.connect(lambda: self.step_zoom(1))
        self.fit_btn.clicked.connect(self.fit_width)
        for w in (self.zoom_out, self.zoom_label, self.zoom_in, self.fit_btn):
            head.addWidget(w)
        root.addLayout(head)

        self.surface = QFrame()
        self.surface.setObjectName("PreviewSurface")
        sl = QVBoxLayout(self.surface)
        sl.setContentsMargins(1, 1, 1, 1)
        self.stack = QStackedWidget()
        self.view = QPdfView()
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.view.setPageSpacing(14)
        self.view.setDocumentMargins(QMargins(18, 18, 18, 18))
        self.view.setFrameShape(QFrame.Shape.NoFrame)
        # Постоянная вертикальная полоса: иначе в режиме «по ширине» полоса то
        # появляется, то исчезает, и компоновка зацикливается на многостраничных PDF.
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.view.zoomFactorChanged.connect(self._update_zoom_label)
        self.empty = EmptyState("eye", "Выберите шаблон",
                                "Слева выберите шаблон документа — здесь появится настоящий PDF.")
        self.loading = EmptyState("sparkle", "Готовим предпросмотр…",
                                  "WeasyPrint собирает PDF выбранной записи.")
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.view)
        self.stack.addWidget(self.loading)
        sl.addWidget(self.stack)
        root.addWidget(self.surface, 1)

        self.page_info = label("", "Faint")
        self.page_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.page_info)

        self.banner = Banner()
        self.open_doc_btn = button("Открыть", "external", "link")
        self.open_doc_btn.clicked.connect(self.open_document)
        self.open_dir_btn = button("Папка", "folder", "link")
        self.open_dir_btn.clicked.connect(self.open_folder)
        self.banner.actions.addWidget(self.open_doc_btn)
        self.banner.actions.addWidget(self.open_dir_btn)
        self.banner.hide()
        root.addWidget(self.banner)

        prog = QHBoxLayout()
        prog.setSpacing(10)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress_label = label("", "Small")
        self.cancel_btn = button("Отменить", None, "ghost")
        self.cancel_btn.clicked.connect(self.cancel_clicked)
        prog.addWidget(self.progress, 1)
        prog.addWidget(self.progress_label)
        prog.addWidget(self.cancel_btn)
        self.progress_box = QWidget()
        self.progress_box.setLayout(prog)
        prog.setContentsMargins(0, 0, 0, 0)
        self.progress_box.hide()
        root.addWidget(self.progress_box)

        self.generate_btn = button("Создать PDF", "download", "hero", icon_size=18)
        self.generate_btn.clicked.connect(self.generate_clicked)
        root.addWidget(self.generate_btn)
        self.hint = label("", "Faint", wrap=True)
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.hint)

        self._documents: list[QPdfDocument] = []
        self._fit = True
        self._set_zoom_enabled(False)

    # ------------------------------------------------------------ состояния

    def show_empty(self, icon_name: str, title: str, text: str) -> None:
        self.empty.set_content(icon_name, title, text, show_action=False)
        self.stack.setCurrentWidget(self.empty)
        self.page_info.setText("")
        self._set_zoom_enabled(False)

    def show_loading(self) -> None:
        # Если PDF уже показан, оставляем его до готовности нового — без мерцания.
        if self.stack.currentWidget() is not self.view:
            self.stack.setCurrentWidget(self.loading)

    def show_pdf(self, path: Path) -> bool:
        doc = QPdfDocument(self)
        doc.load(str(path))
        if doc.status() != QPdfDocument.Status.Ready or doc.pageCount() == 0:
            doc.deleteLater()
            return False
        position = self.view.pageNavigator().currentLocation() if self._documents else QPointF()
        page = self.view.pageNavigator().currentPage() if self._documents else 0
        self.view.setDocument(doc)
        if page and page < doc.pageCount():
            self.view.pageNavigator().jump(page, position)
        # Старые документы удаляем после переключения, чтобы не было пустого кадра.
        for old in self._documents:
            old.deleteLater()
        self._documents = [doc]
        self.stack.setCurrentWidget(self.view)
        n = doc.pageCount()
        size = doc.pagePointSize(0)
        fmt = "A4" if abs(size.width() - 595) < 3 or abs(size.height() - 595) < 3 else \
            f"{size.width() * 25.4 / 72:.0f}×{size.height() * 25.4 / 72:.0f} мм"
        self.page_info.setText(f"{n} {plural(n, ('страница', 'страницы', 'страниц'))} · {fmt}")
        self._set_zoom_enabled(True)
        return True

    def set_caption(self, text: str) -> None:
        self.caption.setText(text)
        self.caption.setToolTip(text)

    # ------------------------------------------------------------ масштаб

    def _set_zoom_enabled(self, enabled: bool) -> None:
        for w in (self.zoom_in, self.zoom_out, self.fit_btn):
            w.setEnabled(enabled)

    def _update_zoom_label(self, factor: float) -> None:
        if self.view.zoomMode() == QPdfView.ZoomMode.FitToWidth:
            self.zoom_label.setText("Ширина")
        else:
            self.zoom_label.setText(f"{round(factor * 100)} %")

    def step_zoom(self, direction: int) -> None:
        current = self.view.zoomFactor()
        steps = self.ZOOM_STEPS
        if direction > 0:
            target = next((s for s in steps if s > current + 0.01), steps[-1])
        else:
            target = next((s for s in reversed(steps) if s < current - 0.01), steps[0])
        self.view.setZoomMode(QPdfView.ZoomMode.Custom)
        self.view.setZoomFactor(target)
        self._fit = False
        self._update_zoom_label(target)

    def fit_width(self) -> None:
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self._fit = True
        self._update_zoom_label(1.0)

    # ------------------------------------------------------------ генерация

    def set_busy(self, busy: bool, total: int = 0) -> None:
        self.progress_box.setVisible(busy and total > 1)
        self.generate_btn.setEnabled(not busy)
        self.generate_btn.setText("Создаём PDF…" if busy else "Создать PDF")
        if busy:
            self.banner.hide()
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(0)
            self.progress_label.setText(f"0 из {total}")

    def set_progress(self, done: int, total: int) -> None:
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.progress_label.setText(f"{done} из {total}")

    def apply_palette(self, palette) -> None:
        pal = self.view.palette()
        pal.setColor(QPalette.ColorRole.Dark, QColor(palette.preview_bg))
        pal.setColor(QPalette.ColorRole.Window, QColor(palette.preview_bg))
        pal.setColor(QPalette.ColorRole.Base, QColor(palette.preview_bg))
        self.view.setPalette(pal)
        self.view.viewport().setAutoFillBackground(True)
        self.view.viewport().setPalette(pal)
