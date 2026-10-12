"""Единое ядро DocFlow: используется GUI, CLI и будущими интеграциями.

Ядро не зависит от Qt и консоли. Любой внешний клиент (Telegram, REST API,
CRM, 1С) может работать через методы этого класса.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable

from . import data_loader, discovery, renderer, templates
from .calculations import enrich
from .errors import DocFlowError, TemplateError, ValidationError
from .history import History
from .models import (BatchResult, DataFileInfo, DataSet, GeneratedDocument, Record,
                     TemplateInfo, ValidationReport)
from .naming import build_filename, reserve_path
from .settings import Settings, app_home
from .money import parse_decimal
from .template_engine import CompiledTemplate, to_date

log = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]


class DocFlowEngine:
    def __init__(self, project_root: Path, settings: Settings | None = None,
                 history: History | None = None):
        self.project_root = Path(project_root).resolve()
        self.settings = settings or Settings.load()
        self.history = history or History(app_home() / "history.sqlite3")
        self.template_errors: dict[Path, str] = {}
        self._cache: dict[Path, tuple[float, TemplateInfo, CompiledTemplate]] = {}
        self._columns: dict[Path, tuple[float, list[str] | None]] = {}

    # ------------------------------------------------------------ папки

    @property
    def template_roots(self) -> list[Path]:
        return [self.project_root / "templates"] + [Path(f) for f in self.settings.extra_folders]

    @property
    def data_roots(self) -> list[Path]:
        return [self.project_root / "data"] + [Path(f) for f in self.settings.extra_folders]

    @property
    def output_dir(self) -> Path:
        if self.settings.output_dir:
            return Path(self.settings.output_dir).expanduser()
        return self.project_root / "output"

    # ------------------------------------------------------------ шаблоны

    def get_template(self, path: Path) -> tuple[TemplateInfo, CompiledTemplate]:
        path = Path(path).resolve()
        try:
            mtime = path.stat().st_mtime
        except OSError as exc:
            raise TemplateError(f"Шаблон «{path.name}» не найден.") from exc
        cached = self._cache.get(path)
        if cached and cached[0] == mtime:
            return cached[1], cached[2]
        info, compiled = templates.load_template(path)
        self._cache[path] = (mtime, info, compiled)
        return info, compiled

    def list_templates(self) -> list[TemplateInfo]:
        result: list[TemplateInfo] = []
        self.template_errors = {}
        for path in discovery.find_templates(self.template_roots):
            try:
                result.append(self.get_template(path)[0])
            except DocFlowError as exc:
                self.template_errors[path] = str(exc)
        return result

    def find_template(self, key: str) -> TemplateInfo:
        """Ищет шаблон по id, имени файла или пути."""
        candidate = Path(key).expanduser()
        if candidate.suffix.lower() in (".html", ".htm") and candidate.is_file():
            return self.get_template(candidate)[0]
        for info in self.list_templates():
            if key in (info.id, info.path.name, info.name):
                return info
        raise TemplateError(f"Шаблон «{key}» не найден.")

    # ------------------------------------------------------------ данные

    def list_data_files(self) -> list[DataFileInfo]:
        return discovery.find_data_files(self.data_roots)

    def load_data(self, path: Path, remember: bool = True) -> DataSet:
        dataset = data_loader.load_dataset(path)
        if remember:
            self.settings.add_recent(dataset.path)
            self.settings.save()
        log.info("Загружен файл данных: формат %s, записей %d", dataset.format, len(dataset))
        return dataset

    def _columns_of(self, path: Path) -> list[str] | None:
        """Колонки файла (с кешем по времени изменения); None — файл не читается."""
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None
        cached = self._columns.get(path)
        if cached and cached[0] == mtime:
            return cached[1]
        try:
            columns = data_loader.load_dataset(path).columns
        except DocFlowError:
            columns = None
        self._columns[path] = (mtime, columns)
        return columns

    def compatible_files(self, info: TemplateInfo, limit_size: int = 2 * 1024 * 1024
                         ) -> list[DataFileInfo]:
        """Файлы данных из разрешённых папок, в которых есть все поля шаблона."""
        result = []
        for f in self.list_data_files():
            if f.size > limit_size:
                continue
            columns = self._columns_of(f.path)
            if not columns:
                continue
            saved = self.settings.field_mappings.get(Settings.mapping_key(info.id, f.path), {})
            if not templates.validate_fields(info, columns, saved).missing:
                result.append(f)
        return result

    # ------------------------------------------------------------ поля

    def validate(self, info: TemplateInfo, dataset: DataSet,
                 mapping: dict[str, str] | None = None) -> ValidationReport:
        if mapping is None:
            mapping = self.settings.field_mappings.get(
                Settings.mapping_key(info.id, dataset.path), {})
        return templates.validate_fields(info, dataset.columns, mapping)

    def save_mapping(self, info: TemplateInfo, dataset: DataSet, mapping: dict[str, str]) -> None:
        self.settings.field_mappings[Settings.mapping_key(info.id, dataset.path)] = dict(mapping)
        self.settings.save()

    def build_context(self, info: TemplateInfo, record: Record,
                      mapping: dict[str, str]) -> tuple[dict[str, Any], list[str]]:
        values = templates.apply_mapping(record.values, mapping)
        problems: list[str] = []
        for name in info.lists:
            value = values.get(name)
            if isinstance(value, list) or value in (None, ""):
                if value in (None, "") and name == "items":
                    # Плоская строка CSV — одна позиция из колонок товара и цены.
                    flat = templates.flat_item_mapping(list(record.values))
                    if {"product", "price"} <= flat.keys():
                        values[name] = [{k: record.values[c] for k, c in flat.items()}]
                continue
            problems.append(f"Поле «{name}» должно содержать список позиций, а не одно значение. "
                            "Проверьте сопоставление полей.")
            values[name] = []
        ctx, calc_problems = enrich(values)
        problems += calc_problems
        for name, kind in info.types.items():
            value = ctx.get(name)
            if value is None or (isinstance(value, str) and not value.strip()):
                continue
            if kind == "date" and to_date(value) is None:
                problems.append(f"Поле «{name}» должно быть датой (например, 2026-10-01 или "
                                "01.10.2026). Проверьте сопоставление полей.")
            elif kind == "number" and not isinstance(value, Decimal):
                try:
                    parse_decimal(value)
                except ValueError:
                    problems.append(f"Поле «{name}» должно быть числом.")
        for name in info.required:
            value = ctx.get(name)
            if value is None or (isinstance(value, (str, list, dict)) and not
                                 (value.strip() if isinstance(value, str) else value)):
                problems.append(f"Не заполнено обязательное поле «{name}».")
        return ctx, problems

    def render_html(self, info: TemplateInfo, record: Record, mapping: dict[str, str]) -> str:
        _, compiled = self.get_template(info.path)
        ctx, problems = self.build_context(info, record, mapping)
        if problems:
            raise ValidationError(
                f"Запись {record.index} не прошла проверку: " + " ".join(problems), problems)
        return compiled.render(ctx)

    # ------------------------------------------------------------ PDF

    def render_to(self, info: TemplateInfo, record: Record, mapping: dict[str, str],
                  target: Path) -> Path:
        """Рендер в указанный файл (используется для предпросмотра)."""
        html = self.render_html(info, record, mapping)
        renderer.render_pdf(html, info.path.parent, target)
        return Path(target)

    def generate(self, info: TemplateInfo, dataset: DataSet, records: list[Record],
                 mapping: dict[str, str] | None = None, output_dir: Path | None = None,
                 progress: ProgressCallback | None = None,
                 should_cancel: Callable[[], bool] | None = None,
                 source: str = "gui") -> BatchResult:
        if mapping is None:
            mapping = self.validate(info, dataset).mapping
        out_dir = Path(output_dir) if output_dir else self.output_dir
        result = BatchResult(info.id, out_dir)
        stamp = datetime.now()
        total = len(records)
        for pos, record in enumerate(records, start=1):
            if should_cancel and should_cancel():
                result.cancelled = True
                break
            result.documents.append(self._generate_one(info, record, mapping, out_dir, stamp))
            if progress:
                progress(pos, total)

        self.history.add(
            source=source, template=info.name, data_file=dataset.name, requested=total,
            outputs=[d.path for d in result.succeeded if d.path], failed=len(result.failed),
            output_dir=out_dir, cancelled=result.cancelled,
        )
        log.info("Генерация завершена: успешно %d, ошибок %d",
                 len(result.succeeded), len(result.failed))
        return result

    def _generate_one(self, info: TemplateInfo, record: Record, mapping: dict[str, str],
                      out_dir: Path, stamp: datetime) -> GeneratedDocument:
        label = Record(record.index, templates.apply_mapping(record.values, mapping)).label()
        try:
            html = self.render_html(info, record, mapping)
        except DocFlowError as exc:
            return GeneratedDocument(record.index, label, None, str(exc))
        path, handle = reserve_path(out_dir, build_filename(info.id, label, stamp))
        try:
            with handle:
                renderer.render_pdf(html, info.path.parent, handle)
        except DocFlowError as exc:
            path.unlink(missing_ok=True)
            return GeneratedDocument(record.index, label, None, str(exc))
        except Exception:  # noqa: BLE001 — не даём одной записи уронить пакет
            path.unlink(missing_ok=True)
            log.exception("Непредвиденная ошибка генерации")
            return GeneratedDocument(record.index, label, None,
                                     "Непредвиденная ошибка при создании PDF.")
        return GeneratedDocument(record.index, label, path)
