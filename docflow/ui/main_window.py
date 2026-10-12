"""Главное окно: боковая панель, рабочая область и предпросмотр."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout,
                               QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QPushButton, QSplitter, QStackedWidget, QVBoxLayout, QWidget)

from ..core import DocFlowEngine
from ..core import renderer as core_renderer
from ..core.models import BatchResult, DataSet, Record, TemplateInfo
from ..core.settings import app_home
from ..core.system import open_path, reveal_in_finder
from ..core.templates import field_label
from . import icons
from .dialogs import MappingDialog
from .documents import DOCS, DocumentsPage, PreviewPanel, plural
from .pages import HistoryPage, SettingsPage, SourcesPage, TemplatesPage, template_icon
from .theme import ThemeManager, build_stylesheet, qt_palette
from .widgets import label
from .workers import TaskRunner

log = logging.getLogger(__name__)


def lower_first(text: str) -> str:
    """«Получатель (ФИО)» -> «получатель (ФИО)» — аббревиатуры не трогаем."""
    return text[:1].lower() + text[1:]


NAV = (
    ("documents", "Документы", "documents"),
    ("templates", "Шаблоны", "templates"),
    ("sources", "Источники данных", "database"),
    ("history", "История", "history"),
    ("settings", "Настройки", "settings"),
)


class Sidebar(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("Sidebar")
        self.setFixedWidth(236)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 20, 14, 16)
        lay.setSpacing(2)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        mark = label("DF", "LogoMark")
        mark.setFixedSize(30, 30)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.addWidget(mark)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("DocFlow Studio", "AppTitle"))
        names.addWidget(label("Генератор PDF-документов", "AppSubtitle"))
        brand.addLayout(names, 1)
        lay.addLayout(brand)
        lay.addSpacing(22)

        self.group = QButtonGroup(self)
        self.buttons: dict[str, QPushButton] = {}
        for key, text, icon_name in NAV:
            btn = QPushButton(text)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            icons.binder.bind(btn, icon_name, "text2", 17)
            self.group.addButton(btn)
            self.buttons[key] = btn
            lay.addWidget(btn)

        lay.addSpacing(22)
        section = QHBoxLayout()
        section.setContentsMargins(10, 0, 4, 0)
        section.addWidget(label("ШАБЛОНЫ", "SectionLabel"))
        section.addStretch(1)
        lay.addLayout(section)
        lay.addSpacing(6)
        self.templates = QListWidget()
        self.templates.setObjectName("TemplateList")
        self.templates.setIconSize(QSize(17, 17))
        self.templates.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.templates.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.templates.setCursor(Qt.CursorShape.PointingHandCursor)
        lay.addWidget(self.templates, 1)

        self.footer = label("Локально · без сети", "AppSubtitle")
        self.footer.setContentsMargins(10, 0, 0, 0)
        lay.addWidget(self.footer)


class MainWindow(QMainWindow):
    def __init__(self, engine: DocFlowEngine, theme: ThemeManager):
        super().__init__()
        self.engine = engine
        self.theme = theme
        self.tasks = TaskRunner(self)
        # WeasyPrint и Pango рендерят последовательно в одном потоке.
        from PySide6.QtCore import QThreadPool
        self.render_pool = QThreadPool(self)
        self.render_pool.setMaxThreadCount(1)

        self.templates: list[TemplateInfo] = []
        self.template: TemplateInfo | None = None
        self.dataset: DataSet | None = None
        self.mapping: dict[str, str] = {}
        self.missing: list[str] = []
        self.record: Record | None = None
        self.last_result: BatchResult | None = None
        self._preview_task_id = 0
        self._generate_task = None
        self._load_task_id = 0
        self._tmp = Path(tempfile.mkdtemp(prefix="docflow-preview-"))

        self.setWindowTitle("DocFlow Studio")
        self.setMinimumSize(1100, 680)
        self.resize(1380, 860)
        self._build()
        self._connect()

        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(180)
        self.preview_timer.timeout.connect(self._render_preview)

        self.theme.changed.connect(self.apply_theme)
        self.apply_theme(self.theme.palette)
        self.reload_templates()
        self.reload_sources()
        self.refresh_history()
        self.refresh_settings()
        self.sidebar.buttons["documents"].setChecked(True)
        self._update_state()
        self._warm_up_renderer()

    # ================================================================ сборка

    def _build(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        lay = QHBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.sidebar = Sidebar()
        lay.addWidget(self.sidebar)

        self.pages = QStackedWidget()
        self.pages.setObjectName("Pages")
        self.documents = DocumentsPage()
        self.preview = PreviewPanel()
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.documents)
        self.splitter.addWidget(self.preview)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([640, 400])
        self.documents.setMinimumWidth(500)

        self.templates_page = TemplatesPage()
        self.sources_page = SourcesPage()
        self.history_page = HistoryPage()
        self.settings_page = SettingsPage()
        self.page_map = {
            "documents": self.splitter, "templates": self.templates_page,
            "sources": self.sources_page, "history": self.history_page,
            "settings": self.settings_page,
        }
        for w in self.page_map.values():
            self.pages.addWidget(w)
        lay.addWidget(self.pages, 1)
        self.setCentralWidget(root)

    def _connect(self) -> None:
        for key, btn in self.sidebar.buttons.items():
            btn.clicked.connect(lambda _=False, k=key: self.show_page(k))
        self.sidebar.templates.currentRowChanged.connect(self._on_sidebar_template)

        d = self.documents
        d.data_file_chosen.connect(self.load_data)
        d.suggestion_chosen.connect(self.load_data)
        d.open_file_requested.connect(self.open_file_dialog)
        d.refresh_requested.connect(self.reload_sources)
        d.mapping_requested.connect(self.edit_mapping)
        d.current_record_changed.connect(self._on_record)
        d.selection_changed.connect(self._update_state)

        p = self.preview
        p.generate_clicked.connect(self.generate)
        p.cancel_clicked.connect(self.cancel_generation)
        p.open_document.connect(self.open_last_document)
        p.open_folder.connect(self.open_last_folder)

        t = self.templates_page
        t.template_chosen.connect(lambda info: (self.set_template(info), self.show_page("documents")))
        t.open_folder.connect(lambda: open_path(self.engine.project_root / "templates"))
        t.refresh.connect(self.reload_templates)

        s = self.sources_page
        s.add_folder.connect(self.add_folder)
        s.remove_folder.connect(self.remove_folder)
        s.file_chosen.connect(lambda path: (self.show_page("documents"), self.load_data(path)))
        s.refresh.connect(self.reload_sources)

        h = self.history_page
        h.open_folder.connect(lambda path: open_path(path) or self.toast_error(
            "Папка результатов не найдена — возможно, она была удалена."))
        h.clear_history.connect(self.clear_history)

        st = self.settings_page
        st.theme_changed.connect(self.set_theme)
        st.choose_output.connect(self.choose_output_dir)
        st.reset_output.connect(self.reset_output_dir)
        st.open_output.connect(self.open_output_dir)
        st.auto_open_changed.connect(self.set_auto_open)

        QShortcut(QKeySequence("Ctrl+O"), self, self.open_file_dialog)
        QShortcut(QKeySequence("Ctrl+Return"), self, self.generate)
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: (self.show_page("documents"),
                                                         self.documents.search.setFocus()))
        QShortcut(QKeySequence.StandardKey.ZoomIn, self, lambda: self.preview.step_zoom(1))
        QShortcut(QKeySequence.StandardKey.ZoomOut, self, lambda: self.preview.step_zoom(-1))

    def show_page(self, key: str) -> None:
        self.sidebar.buttons[key].setChecked(True)
        self.pages.setCurrentWidget(self.page_map[key])
        if key == "history":
            self.refresh_history()

    # ================================================================ тема

    def apply_theme(self, palette) -> None:
        qss = build_stylesheet(palette)
        qss = qss.replace("__CHEVRON__", icons.qss_icon_file("chevron-down", palette.text2, 2))
        qss = qss.replace("__CHECK__", icons.qss_icon_file("check", palette.on_accent, 3))
        qss = qss.replace("__DASH__", icons.qss_icon_file("dash", palette.on_accent, 3))
        qss += f"\n#Divider {{ background: {palette.border}; }}\n"
        app = QApplication.instance()
        app.setPalette(qt_palette(palette))
        app.setStyleSheet(qss)
        icons.binder.refresh(palette)
        self.documents.apply_palette(palette)
        self.preview.apply_palette(palette)
        self.history_page.palette = palette
        self._fill_sidebar_templates()
        if self.pages.currentWidget() is self.history_page:
            self.refresh_history()

    def set_theme(self, mode: str) -> None:
        self.engine.settings.theme = mode
        self.engine.settings.save()
        self.theme.set_mode(mode)

    # ================================================================ шаблоны

    def reload_templates(self) -> None:
        self.templates = self.engine.list_templates()
        if self.template:
            self.template = next((t for t in self.templates if t.path == self.template.path), None)
        if self.template is None and self.engine.settings.last_template:
            self.template = next((t for t in self.templates
                                  if str(t.path) == self.engine.settings.last_template), None)
            if self.template and self.dataset is None:
                QTimer.singleShot(0, self._auto_pick_data)
        self._fill_sidebar_templates()
        self.templates_page.set_templates(self.templates, self.template.path if self.template else None,
                                          self.engine.template_errors)
        self._revalidate()

    def _fill_sidebar_templates(self) -> None:
        lst = self.sidebar.templates
        lst.blockSignals(True)
        lst.clear()
        palette = self.theme.palette
        for info in self.templates:
            item = QListWidgetItem(info.name)
            item.setIcon(icons.icon(template_icon(info), palette.text2, 17))
            item.setToolTip(f"{info.name} · {info.page_label}\n{info.path.name}")
            item.setSizeHint(QSize(0, 34))
            lst.addItem(item)
        if self.template:
            idx = next((i for i, t in enumerate(self.templates) if t.path == self.template.path), -1)
            lst.setCurrentRow(idx)
            if idx >= 0:
                lst.item(idx).setIcon(icons.icon(template_icon(self.template), palette.accent, 17))
        lst.blockSignals(False)

    def _on_sidebar_template(self, row: int) -> None:
        if 0 <= row < len(self.templates):
            self.set_template(self.templates[row])

    def set_template(self, info: TemplateInfo) -> None:
        if self.template is None or self.template.path != info.path:
            self.preview.banner.hide()  # итог прошлой операции больше не актуален
        self.template = info
        self.engine.settings.last_template = str(info.path)
        self.engine.settings.save()
        self._fill_sidebar_templates()
        self.templates_page.set_templates(self.templates, info.path, self.engine.template_errors)
        self._revalidate()
        self._auto_pick_data()

    def _auto_pick_data(self) -> None:
        """Если текущие данные не подходят к шаблону, открываем подходящий файл проекта."""
        if not self.template or (self.dataset and not self.missing):
            return
        candidates = self.engine.compatible_files(self.template)
        if candidates:
            self.load_data(candidates[0].path)

    # ================================================================ данные

    def reload_sources(self) -> None:
        files = self.engine.list_data_files()
        s = self.engine.settings
        self.documents.set_files(files, s.recent_files, self.dataset.path if self.dataset else None)
        self.sources_page.set_state(self.engine.project_root / "data", s.extra_folders, files,
                                    s.recent_files)

    def open_file_dialog(self) -> None:
        start = str(Path(self.engine.settings.recent_files[0]).parent) if self.engine.settings.recent_files \
            else str(self.engine.project_root / "data")
        path, _ = QFileDialog.getOpenFileName(self, "Открыть данные", start,
                                              "Данные (*.csv *.json);;CSV (*.csv);;JSON (*.json)")
        if path:
            self.show_page("documents")
            self.load_data(Path(path))

    def load_data(self, path: Path) -> None:
        self.documents.source_hint.setText(f"Загружаем {path.name}…")

        def done(task_id: int, dataset: DataSet) -> None:
            if task_id != self._load_task_id:
                return
            self.dataset = dataset
            self.record = None
            self.preview.banner.hide()
            self.documents.source_hint.setText(self._short_path(dataset.path))
            self.documents.set_dataset(dataset)
            self.reload_sources()
            self._revalidate()
            if dataset.warnings:
                self.preview.banner.show_message(
                    "warning", "Файл загружен с замечаниями",
                    dataset.warnings[0] + (f" И ещё замечаний: {len(dataset.warnings) - 1}."
                                           if len(dataset.warnings) > 1 else ""))
                self._banner_buttons(False)

        def failed(task_id: int, message: str) -> None:
            if task_id != self._load_task_id:
                return
            self.dataset = None
            self.documents.source_hint.setText("CSV или JSON")
            self.documents.show_load_error(message)
            self._update_state()

        task = self.tasks.start(self.engine.load_data, path, on_done=done, on_error=failed)
        self._load_task_id = task.task_id

    def add_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Добавить папку с шаблонами и данными",
                                                  str(Path.home()))
        if not folder:
            return
        if Path(folder).resolve() in (Path.home().resolve(), Path("/")):
            self.toast_error("Выберите конкретную папку с документами, а не весь диск или домашнюю папку.")
            return
        if self.engine.settings.add_folder(Path(folder)):
            self.engine.settings.save()
        self.reload_sources()
        self.reload_templates()

    def remove_folder(self, folder: str) -> None:
        self.engine.settings.remove_folder(folder)
        self.engine.settings.save()
        self.reload_sources()
        self.reload_templates()

    # ================================================================ поля

    def _revalidate(self) -> None:
        if self.template and self.dataset:
            report = self.engine.validate(self.template, self.dataset)
            self.mapping, self.missing = report.mapping, report.missing
            renamed = {k: v for k, v in report.mapping.items() if k != v}
            ok = f"Поля сопоставлены: {len(renamed)}" if renamed else "Все поля найдены"
            title = text = ""
            suggestions = []
            if report.missing:
                labels = ", ".join(lower_first(field_label(f)) for f in report.missing)
                suggestions = [f for f in self.engine.compatible_files(self.template)
                               if f.path != self.dataset.path]
                found = len(self.template.required) - len(report.missing)
                if found == 0:
                    title = (f"Файл «{self.dataset.name}» не подходит для шаблона "
                             f"«{self.template.name}»")
                else:
                    title = f"Не хватает данных для шаблона «{self.template.name}»"
                text = f"В файле нет: {labels}."
                text += (" Откройте подходящий файл или сопоставьте колонки вручную."
                         if suggestions else " Сопоставьте колонки вручную или выберите другой файл.")
            self.documents.show_validation(report.missing, ok, title, text, suggestions)
        else:
            self.mapping, self.missing = {}, []
            self.documents.show_validation([], None)
        self._update_state()
        self.schedule_preview()

    def edit_mapping(self) -> None:
        if not (self.template and self.dataset):
            self.toast_error("Сначала выберите шаблон и загрузите данные.")
            return
        dialog = MappingDialog(self.template, self.dataset, self.mapping, self)
        if dialog.exec():
            self.engine.save_mapping(self.template, self.dataset, dialog.mapping())
            self._revalidate()

    # ================================================================ предпросмотр

    def _on_record(self, record: Record | None) -> None:
        self.record = record
        self._update_state()
        self.schedule_preview()

    def schedule_preview(self) -> None:
        if not self.template:
            self.preview.show_empty("templates", "Выберите шаблон",
                                    "Слева выберите шаблон документа — здесь появится настоящий PDF.")
            return
        if not self.dataset:
            self.preview.show_empty("database", "Загрузите данные",
                                    "Выберите CSV или JSON, чтобы увидеть документ с реальными значениями.")
            return
        if not self.dataset.records:
            self.preview.show_empty("inbox", "Записей нет", "В выбранном файле нет данных для документа.")
            return
        if self.missing:
            self.preview.show_empty("mapping", "Сопоставьте поля",
                                    "Шаблону не хватает данных: "
                                    + ", ".join(lower_first(field_label(f)) for f in self.missing) + ".")
            return
        if not self.record:
            self.preview.show_empty("table", "Выберите запись",
                                    "Щёлкните по строке таблицы, чтобы увидеть её документ.")
            return
        self.preview.show_loading()
        self.preview_timer.start()

    def _render_preview(self) -> None:
        if not (self.template and self.dataset and self.record) or self.missing:
            return
        self._preview_task_id += 1
        request = self._preview_task_id
        target = self._tmp / f"preview-{request}.pdf"
        info, record, mapping = self.template, self.record, dict(self.mapping)

        def done(_tid, path):
            if request != self._preview_task_id:  # пришёл устаревший результат
                Path(path).unlink(missing_ok=True)
                return
            if not self.preview.show_pdf(Path(path)):
                self.preview.show_empty("alert-circle", "Не удалось показать PDF",
                                        "Файл создан, но его не удалось открыть для просмотра.")
            for old in self._tmp.glob("preview-*.pdf"):
                if old != Path(path):
                    old.unlink(missing_ok=True)

        def failed(_tid, message):
            if request == self._preview_task_id:
                self.preview.show_empty("alert-circle", "Предпросмотр недоступен", message)

        self.tasks.start(self.engine.render_to, info, record, mapping, target,
                         on_done=done, on_error=failed, pool=self.render_pool)

    def _warm_up_renderer(self) -> None:
        """Заранее загружаем WeasyPrint, чтобы первый предпросмотр был быстрым."""
        def failed(_tid, message):
            self.preview.banner.show_message("danger", "PDF-движок недоступен", message)
            self._banner_buttons(False)

        self.tasks.start(core_renderer.load_weasyprint, on_error=failed, pool=self.render_pool)

    # ================================================================ генерация

    def _targets(self) -> list[Record]:
        checked = self.documents.checked_records()
        if checked:
            return checked
        return [self.record] if self.record else []

    def _update_state(self) -> None:
        targets = self._targets()
        busy = self._generate_task is not None
        ready = bool(self.template and self.dataset and targets and not self.missing)
        self.preview.generate_btn.setEnabled(ready and not busy)
        n = len(targets)
        if not self.template:
            hint = "Выберите шаблон в левой панели"
        elif not self.dataset:
            hint = "Загрузите CSV или JSON"
        elif self.missing:
            hint = "Сопоставьте недостающие поля"
        elif not targets:
            hint = "Выберите запись в таблице"
        elif self.documents.checked_records():
            hint = f"Будет создано {n} {plural(n, DOCS)} · папка {self._short_output()}"
        else:
            hint = f"Текущая запись № {targets[0].index} · папка {self._short_output()}"
        self.preview.hint.setText(hint)
        if self.template and self.record:
            self.preview.set_caption(f"{self.template.name} · № {self.record.index}")
        elif self.template:
            self.preview.set_caption(f"{self.template.name} · {self.template.page_label}")
        else:
            self.preview.set_caption("Реальный PDF выбранной записи")

    def _short_path(self, path: Path) -> str:
        """Путь относительно проекта или домашней папки — короче и понятнее."""
        for base, prefix in ((self.engine.project_root, ""), (Path.home(), "~/")):
            try:
                return prefix + str(path.relative_to(base))
            except ValueError:
                continue
        return str(path)

    def _short_output(self) -> str:
        out = self.engine.output_dir
        try:
            return str(out.relative_to(self.engine.project_root)) + "/"
        except ValueError:
            return out.name + "/"

    def generate(self) -> None:
        if self._generate_task is not None or not self.preview.generate_btn.isEnabled():
            return
        records = self._targets()
        info, dataset, mapping = self.template, self.dataset, dict(self.mapping)
        self.preview.set_busy(True, len(records))

        def progress(_tid, done, total):
            self.preview.set_progress(done, total)

        def done(_tid, result: BatchResult):
            self._generate_task = None
            self.preview.set_busy(False)
            self.last_result = result
            self._show_result(result)
            self.refresh_history()
            self._update_state()

        def failed(_tid, message):
            self._generate_task = None
            self.preview.set_busy(False)
            self.preview.banner.show_message("danger", "Не удалось создать PDF", message)
            self._banner_buttons(False)
            self._update_state()

        self._generate_task = self.tasks.start(
            self.engine.generate, info, dataset, records, mapping, source="gui",
            with_progress=True, on_done=done, on_error=failed, on_progress=progress,
            pool=self.render_pool)
        self._update_state()

    def cancel_generation(self) -> None:
        if self._generate_task is not None:
            self._generate_task.cancel_event.set()
            self.preview.progress_label.setText("Останавливаем…")

    def _banner_buttons(self, show_doc: bool, show_dir: bool | None = None) -> None:
        self.preview.open_doc_btn.setVisible(show_doc)
        self.preview.open_dir_btn.setVisible(show_doc if show_dir is None else show_dir)

    def _show_result(self, result: BatchResult) -> None:
        ok, bad = result.succeeded, result.failed
        b = self.preview.banner
        if result.cancelled:
            b.show_message("warning", "Генерация остановлена",
                           f"Создано {len(ok)} {plural(len(ok), DOCS)} до отмены.")
            self._banner_buttons(False, bool(ok))
        elif ok and not bad:
            if len(ok) == 1:
                b.show_message("success", "PDF создан", ok[0].path.name)
                self._banner_buttons(True, True)
                if self.engine.settings.auto_open_single:
                    open_path(ok[0].path)
            else:
                b.show_message("success", f"Создано {len(ok)} {plural(len(ok), DOCS)}",
                               f"Сохранено в {self._short_output()}")
                self._banner_buttons(False, True)
                self.preview.open_dir_btn.setText("Открыть папку")
                return
        elif ok:
            b.show_message("warning", f"Создано {len(ok)} из {len(ok) + len(bad)}",
                           f"Запись {bad[0].record_index}: {bad[0].error}")
            self._banner_buttons(False, True)
        else:
            b.show_message("danger", "PDF не создан", bad[0].error if bad else "Нет записей для генерации.")
            self._banner_buttons(False, False)
        self.preview.open_dir_btn.setText("Папка")

    def open_last_document(self) -> None:
        if self.last_result and self.last_result.succeeded:
            open_path(self.last_result.succeeded[0].path)

    def open_last_folder(self) -> None:
        if self.last_result and self.last_result.succeeded:
            if len(self.last_result.succeeded) == 1:
                reveal_in_finder(self.last_result.succeeded[0].path)
            else:
                open_path(self.last_result.output_dir)
        else:
            self.open_output_dir()

    # ================================================================ история и настройки

    def refresh_history(self) -> None:
        try:
            self.history_page.set_entries(self.engine.history.list())
        except Exception:  # noqa: BLE001 — повреждённая БД не должна ронять окно
            log.exception("Не удалось прочитать историю")
            self.history_page.set_entries([])

    def clear_history(self) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle("Очистить историю")
        box.setText("Очистить историю операций?")
        box.setInformativeText("Созданные PDF-файлы останутся на диске.")
        yes = box.addButton("Очистить", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is yes:
            self.engine.history.clear()
            self.refresh_history()

    def refresh_settings(self) -> None:
        s = self.engine.settings
        self.settings_page.set_state(s.theme, self.engine.output_dir, bool(s.output_dir),
                                     s.auto_open_single, app_home())
        self._update_state()

    def choose_output_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Папка для PDF", str(self.engine.output_dir))
        if folder:
            self.engine.settings.output_dir = folder
            self.engine.settings.save()
            self.refresh_settings()

    def reset_output_dir(self) -> None:
        self.engine.settings.output_dir = ""
        self.engine.settings.save()
        self.refresh_settings()

    def open_output_dir(self) -> None:
        out = self.engine.output_dir
        out.mkdir(parents=True, exist_ok=True)
        open_path(out)

    def set_auto_open(self, value: bool) -> None:
        self.engine.settings.auto_open_single = value
        self.engine.settings.save()

    def toast_error(self, message: str) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("DocFlow Studio")
        box.setText(message)
        box.addButton("Понятно", QMessageBox.ButtonRole.AcceptRole)
        box.exec()

    def closeEvent(self, event):  # noqa: N802
        if self._generate_task is not None:
            self._generate_task.cancel_event.set()
        self.render_pool.waitForDone(5000)
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().closeEvent(event)
