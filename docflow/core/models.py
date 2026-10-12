"""Простые структуры данных, общие для ядра, CLI и GUI."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Record:
    """Одна строка CSV или один объект JSON."""

    index: int  # порядковый номер в источнике, начиная с 1
    values: dict[str, Any]

    def label(self) -> str:
        """Короткий идентификатор записи для имён файлов и списков."""
        for key in ("id", "number", "номер", "certificate_id", "invoice_id"):
            value = self.values.get(key)
            if value not in (None, ""):
                return str(value)
        return f"{self.index}"


@dataclass
class DataSet:
    path: Path
    format: str  # "csv" | "json"
    columns: list[str]
    records: list[Record]
    encoding: str = "utf-8"
    delimiter: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name

    def __len__(self) -> int:
        return len(self.records)


@dataclass
class TemplateInfo:
    """Шаблон, найденный на диске, вместе с его метаданными."""

    id: str
    path: Path
    name: str
    description: str = ""
    icon: str = "file"
    page: str = "a4"  # "a4" | "receipt"
    fields: list[str] = field(default_factory=list)  # все поля, которые использует шаблон
    required: list[str] = field(default_factory=list)  # обязательные поля из данных
    computed: list[str] = field(default_factory=list)  # поля, которые считает ядро
    lists: list[str] = field(default_factory=list)  # поля-списки (позиции счёта)
    types: dict[str, str] = field(default_factory=dict)  # поле -> "date" | "number"

    @property
    def page_label(self) -> str:
        return "Кассовая лента 80 мм" if self.page == "receipt" else "A4"


@dataclass
class DataFileInfo:
    path: Path
    format: str
    size: int
    root: Path

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def relative(self) -> str:
        try:
            return str(self.path.relative_to(self.root))
        except ValueError:
            return self.path.name


@dataclass
class ValidationReport:
    """Результат сопоставления полей шаблона с колонками данных."""

    mapping: dict[str, str]  # поле шаблона -> колонка данных
    missing: list[str]  # обязательные поля, для которых нет колонки
    unused_columns: list[str]
    record_problems: dict[int, list[str]] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.missing


@dataclass
class GeneratedDocument:
    record_index: int
    record_label: str
    path: Path | None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.path is not None and self.error is None


@dataclass
class BatchResult:
    template_id: str
    output_dir: Path
    documents: list[GeneratedDocument] = field(default_factory=list)
    cancelled: bool = False

    @property
    def succeeded(self) -> list[GeneratedDocument]:
        return [d for d in self.documents if d.ok]

    @property
    def failed(self) -> list[GeneratedDocument]:
        return [d for d in self.documents if not d.ok]
