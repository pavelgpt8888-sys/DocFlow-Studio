"""Консольный режим DocFlow Studio.

Интерактивное меню и неинтерактивный запуск с аргументами. Вся логика
генерации находится в ядре — здесь только диалог с пользователем.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import Callable

from .core import DocFlowEngine, DocFlowError
from .core.data_loader import select_records
from .core.models import BatchResult, DataSet, Record, TemplateInfo
from .core.system import open_path

MENU = (
    ("1", "Выбрать шаблон"),
    ("2", "Выбрать данные"),
    ("3", "Выбрать запись"),
    ("4", "Создать PDF"),
    ("5", "Создать PDF для всех записей"),
    ("6", "Открыть результат"),
    ("7", "Выход"),
)

BOLD, DIM, GREEN, RED, ACCENT, RESET = "\033[1m", "\033[2m", "\033[32m", "\033[31m", "\033[38;5;105m", "\033[0m"


class CliApp:
    def __init__(self, engine: DocFlowEngine, input_fn: Callable[[str], str] = input,
                 output: Callable[[str], None] = print, color: bool | None = None,
                 auto_open: bool = True):
        self.engine = engine
        self.ask = input_fn
        self.out = output
        self.color = sys.stdout.isatty() if color is None else color
        self.auto_open = auto_open
        self.template: TemplateInfo | None = None
        self.dataset: DataSet | None = None
        self.record: Record | None = None
        self.mapping: dict[str, str] = {}
        self.last_result: BatchResult | None = None

    # ------------------------------------------------------------ вывод

    def c(self, text: str, style: str) -> str:
        return f"{style}{text}{RESET}" if self.color else text

    def error(self, text: str) -> None:
        self.out(self.c(f"  ✕ {text}", RED))

    def success(self, text: str) -> None:
        self.out(self.c(f"  ✓ {text}", GREEN))

    def header(self) -> None:
        self.out("")
        self.out(self.c("  DocFlow Studio", BOLD) + self.c("  · консольный режим", DIM))
        self.out(self.c("  " + "─" * 46, DIM))
        rows = (
            ("Шаблон", self.template.name if self.template else "не выбран"),
            ("Данные", f"{self.dataset.name} · записей: {len(self.dataset)}" if self.dataset else "не выбраны"),
            ("Запись", f"№ {self.record.index} · {self.record_label(self.record)}" if self.record else "не выбрана"),
        )
        for label, value in rows:
            self.out(f"  {self.c(label.ljust(8), DIM)} {value}")
        self.out(self.c("  " + "─" * 46, DIM))
        for key, title in MENU:
            self.out(f"  {self.c(key, ACCENT)}  {title}")

    def prompt(self, text: str) -> str:
        return self.ask(f"\n  {text}: ").strip()

    def choose(self, title: str, options: list[str]) -> int | None:
        """Показывает нумерованный список, возвращает индекс (с 0) или None."""
        self.out(f"\n  {self.c(title, BOLD)}")
        for i, option in enumerate(options, start=1):
            self.out(f"  {self.c(str(i).rjust(2), ACCENT)}  {option}")
        answer = self.prompt("Номер (Enter — отмена)")
        if not answer:
            return None
        if not answer.isdigit() or not 1 <= int(answer) <= len(options):
            self.error("Нет такого номера.")
            return None
        return int(answer) - 1

    def record_label(self, record: Record) -> str:
        from .core.templates import apply_mapping
        values = apply_mapping(record.values, self.mapping)
        text = " · ".join(str(values[k]) for k in ("id", "number", "product", "recipient")
                          if k in values and not isinstance(values[k], (list, dict)))
        return text or f"запись {record.index}"

    # ------------------------------------------------------------ действия

    def select_template(self) -> None:
        templates = self.engine.list_templates()
        if not templates:
            self.error("Шаблоны не найдены. Добавьте HTML-файл в папку templates/.")
            return
        idx = self.choose("Шаблоны", [f"{t.name}  {self.c(f'{t.path.name} · {t.page_label}', DIM)}"
                                      for t in templates])
        if idx is not None:
            self.template = templates[idx]
            self.success(f"Выбран шаблон «{self.template.name}».")
            self.refresh_mapping()

    def select_data(self) -> None:
        files = self.engine.list_data_files()
        options = [f"{f.relative}  {self.c(f.format.upper(), DIM)}" for f in files]
        options.append("Указать путь к файлу…")
        idx = self.choose("Файлы данных", options)
        if idx is None:
            return
        path = files[idx].path if idx < len(files) else Path(self.prompt("Путь к CSV или JSON"))
        self.load_data(path)

    def load_data(self, path: Path) -> bool:
        try:
            self.dataset = self.engine.load_data(path)
        except DocFlowError as exc:
            self.error(str(exc))
            return False
        self.record = None
        self.success(f"Загружено записей: {len(self.dataset)} ({self.dataset.encoding}).")
        for warning in self.dataset.warnings[:5]:
            self.out(self.c(f"  ! {warning}", DIM))
        self.refresh_mapping()
        return True

    def refresh_mapping(self) -> None:
        if not (self.template and self.dataset):
            return
        report = self.engine.validate(self.template, self.dataset)
        self.mapping = report.mapping
        if report.missing:
            self.out(self.c(f"  ! Не найдены поля: {', '.join(report.missing)}", RED))

    def ensure_mapping(self) -> bool:
        assert self.template and self.dataset
        report = self.engine.validate(self.template, self.dataset, self.mapping)
        self.mapping = report.mapping
        for name in report.missing:
            idx = self.choose(f"Какая колонка соответствует полю «{name}»?", self.dataset.columns)
            if idx is None:
                self.error(f"Поле «{name}» не сопоставлено — генерация невозможна.")
                return False
            self.mapping[name] = self.dataset.columns[idx]
        if report.missing:
            self.engine.save_mapping(self.template, self.dataset, self.mapping)
        return True

    def select_record(self) -> None:
        if not self.dataset:
            self.error("Сначала выберите данные (пункт 2).")
            return
        if not self.dataset.records:
            self.error("В файле нет записей.")
            return
        width = max(20, min(70, shutil.get_terminal_size((90, 20)).columns - 12))
        options = [self.record_label(r)[:width] for r in self.dataset.records]
        idx = self.choose("Записи", options)
        if idx is not None:
            self.record = self.dataset.records[idx]
            self.success(f"Выбрана запись № {self.record.index}.")

    def _ready(self) -> bool:
        if not self.template:
            self.error("Сначала выберите шаблон (пункт 1).")
            return False
        if not self.dataset:
            self.error("Сначала выберите данные (пункт 2).")
            return False
        return self.ensure_mapping()

    def generate(self, records: list[Record]) -> BatchResult | None:
        assert self.template and self.dataset

        def progress(done: int, total: int) -> None:
            bar = "█" * int(24 * done / total) + "░" * (24 - int(24 * done / total))
            end = "\n" if done == total else "\r"
            sys.stdout.write(f"  {bar} {done}/{total}{end}")
            sys.stdout.flush()

        try:
            result = self.engine.generate(self.template, self.dataset, records, self.mapping,
                                          progress=progress if len(records) > 1 else None,
                                          source="cli")
        except DocFlowError as exc:
            self.error(str(exc))
            return None
        self.last_result = result
        for doc in result.documents:
            if doc.ok:
                self.success(f"{doc.path.name}")
            else:
                self.error(f"Запись {doc.record_index}: {doc.error}")
        self.out(f"\n  Готово: {len(result.succeeded)} из {len(records)}. "
                 f"Папка: {result.output_dir}")
        return result

    def generate_one(self) -> None:
        if not self._ready():
            return
        if not self.record:
            self.error("Сначала выберите запись (пункт 3).")
            return
        result = self.generate([self.record])
        if result and result.succeeded and self.auto_open and self.engine.settings.auto_open_single:
            open_path(result.succeeded[0].path)

    def generate_all(self) -> None:
        if not self._ready():
            return
        assert self.dataset
        if not self.dataset.records:
            self.error("В файле нет записей.")
            return
        self.generate(self.dataset.records)

    def open_result(self) -> None:
        if not self.last_result:
            out_dir = self.engine.output_dir
            if out_dir.exists():
                open_path(out_dir)
                self.success(f"Открыта папка {out_dir}.")
            else:
                self.error("Документы ещё не создавались.")
            return
        docs = self.last_result.succeeded
        if len(docs) == 1:
            open_path(docs[0].path)
            self.success(f"Открыт {docs[0].path.name}.")
        else:
            open_path(self.last_result.output_dir)
            self.success("Открыта папка результатов.")

    # ------------------------------------------------------------ цикл

    def run(self) -> int:
        actions = {
            "1": self.select_template, "2": self.select_data, "3": self.select_record,
            "4": self.generate_one, "5": self.generate_all, "6": self.open_result,
        }
        while True:
            self.header()
            try:
                choice = self.prompt("Выберите пункт")
            except (EOFError, KeyboardInterrupt):
                self.out("")
                return 0
            if choice in ("7", "q", "й", "exit", "выход"):
                self.out("  До встречи!")
                return 0
            action = actions.get(choice)
            if action is None:
                self.error("Введите число от 1 до 7.")
                continue
            try:
                action()
            except (EOFError, KeyboardInterrupt):
                self.out("")
                return 0
            except DocFlowError as exc:
                self.error(str(exc))


def run_batch(app: CliApp, args: argparse.Namespace) -> int:
    """Неинтерактивный режим: --template и --data, затем --record или --all."""
    try:
        app.template = app.engine.find_template(args.template)
    except DocFlowError as exc:
        app.error(str(exc))
        return 2
    if not app.load_data(Path(args.data)):
        return 2
    report = app.engine.validate(app.template, app.dataset)
    app.mapping = report.mapping
    if report.missing:
        app.error("Не найдены поля: " + ", ".join(report.missing) +
                  ". Запустите интерактивный режим, чтобы сопоставить поля.")
        return 2
    try:
        records = select_records(app.dataset, "all" if args.all else args.record)
    except ValueError as exc:
        app.error(str(exc))
        return 2
    result = app.generate(records)
    if result is None:
        return 1
    if len(result.succeeded) == 1 and app.auto_open and app.engine.settings.auto_open_single:
        open_path(result.succeeded[0].path)
    return 0 if not result.failed else 1


def main(args: argparse.Namespace, project_root: Path) -> int:
    engine = DocFlowEngine(project_root)
    if args.output:
        engine.settings.output_dir = str(Path(args.output).expanduser().resolve())
    app = CliApp(engine, auto_open=not args.no_open)
    if args.template or args.data:
        if not (args.template and args.data and (args.record or args.all)):
            app.error("Для запуска без меню укажите --template, --data и --record или --all.")
            return 2
        return run_batch(app, args)
    return app.run()
