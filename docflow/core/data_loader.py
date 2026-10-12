"""Чтение CSV и JSON с автоопределением кодировки и разделителя."""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

from .errors import DataLoadError
from .models import DataSet, Record

MAX_FILE_SIZE = 50 * 1024 * 1024
CSV_DELIMITERS = ",;\t|"
SUPPORTED_EXTENSIONS = {".csv": "csv", ".json": "json"}


def detect_format(path: Path) -> str:
    fmt = SUPPORTED_EXTENSIONS.get(path.suffix.lower())
    if fmt is None:
        raise DataLoadError(f"Формат файла «{path.name}» не поддерживается. Выберите CSV или JSON.")
    return fmt


def decode_bytes(raw: bytes) -> tuple[str, str]:
    """Возвращает (текст, кодировка). Поддерживает UTF-8, UTF-8 BOM, UTF-16 BOM и Windows-1251."""
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "utf-16"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    # cp1251 декодирует почти любые байты, поэтому он идёт последним.
    return raw.decode("cp1251", errors="replace"), "cp1251"


def _read_raw(path: Path) -> bytes:
    if not path.exists():
        raise DataLoadError(f"Файл «{path.name}» не найден.")
    if not path.is_file():
        raise DataLoadError(f"«{path.name}» не является файлом.")
    size = path.stat().st_size
    if size == 0:
        raise DataLoadError(f"Файл «{path.name}» пустой.")
    if size > MAX_FILE_SIZE:
        raise DataLoadError(f"Файл «{path.name}» больше 50 МБ — такие файлы не поддерживаются.")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise DataLoadError(f"Не удалось прочитать «{path.name}»: нет доступа к файлу.") from exc
    if b"\x00" in raw[:4096] and not raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        raise DataLoadError(f"Файл «{path.name}» похож на двоичный, а не на текстовый CSV или JSON.")
    return raw


def detect_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(sample, delimiters=CSV_DELIMITERS).delimiter
    except csv.Error:
        header = text.splitlines()[0] if text.splitlines() else ""
        counts = {d: header.count(d) for d in CSV_DELIMITERS}
        best = max(counts, key=counts.get)
        return best if counts[best] else ","


def _clean_columns(raw_columns: list[str]) -> list[str]:
    columns: list[str] = []
    for i, name in enumerate(raw_columns, start=1):
        name = (name or "").strip().lstrip("﻿")
        if not name:
            name = f"column_{i}"
        base, n = name, 2
        while name in columns:
            name = f"{base}_{n}"
            n += 1
        columns.append(name)
    return columns


def parse_csv(text: str, path: Path, encoding: str) -> DataSet:
    if not text.strip():
        raise DataLoadError(f"Файл «{path.name}» не содержит данных.")
    delimiter = detect_delimiter(text)
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        rows = list(reader)
    except csv.Error as exc:
        raise DataLoadError(f"Файл «{path.name}» повреждён: не удалось разобрать строки CSV.") from exc

    rows = [r for r in rows if any(cell.strip() for cell in r)]
    if not rows:
        raise DataLoadError(f"Файл «{path.name}» не содержит данных.")
    columns = _clean_columns(rows[0])
    warnings: list[str] = []
    records: list[Record] = []
    for line_no, row in enumerate(rows[1:], start=2):
        if len(row) != len(columns):
            warnings.append(
                f"Строка {line_no}: ожидалось столбцов — {len(columns)}, найдено — {len(row)}."
            )
        padded = (row + [""] * len(columns))[: len(columns)]
        values = {col: cell.strip() for col, cell in zip(columns, padded)}
        records.append(Record(index=len(records) + 1, values=values))

    return DataSet(path, "csv", columns, records, encoding, delimiter, warnings)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _normalize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize_value(v) for v in value]
    if isinstance(value, float):
        # Не теряем точность при дальнейших расчётах на Decimal.
        return repr(value)
    return value


def parse_json(text: str, path: Path, encoding: str) -> DataSet:
    if not text.strip():
        raise DataLoadError(f"Файл «{path.name}» не содержит данных.")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DataLoadError(
            f"Файл «{path.name}» содержит ошибку JSON в строке {exc.lineno}, позиция {exc.colno}."
        ) from exc

    if isinstance(payload, dict):
        for key in ("records", "items", "data", "rows"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    if not isinstance(payload, list):
        raise DataLoadError(f"Файл «{path.name}» должен содержать список объектов.")

    warnings: list[str] = []
    records: list[Record] = []
    columns: list[str] = []
    for pos, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            warnings.append(f"Элемент {pos} пропущен: ожидался объект.")
            continue
        values = {str(k).strip(): _normalize_value(v) for k, v in item.items()}
        for key in values:
            if key not in columns:
                columns.append(key)
        records.append(Record(index=len(records) + 1, values=values))

    return DataSet(path, "json", columns, records, encoding, None, warnings)


def load_dataset(path: str | Path) -> DataSet:
    path = Path(path).expanduser()
    fmt = detect_format(path)
    text, encoding = decode_bytes(_read_raw(path))
    if fmt == "csv":
        return parse_csv(text, path, encoding)
    return parse_json(text, path, encoding)


def select_records(dataset: DataSet, selection: str | list[int] | None) -> list[Record]:
    """Выбирает записи по номерам (с 1).

    selection: None или "all" — все записи; список чисел; строка вида «1,3,5-7».
    """
    if selection is None or selection == "all":
        return list(dataset.records)
    if isinstance(selection, str):
        indexes: list[int] = []
        for part in selection.replace(" ", "").split(","):
            if not part:
                continue
            if "-" in part:
                start, _, end = part.partition("-")
                if not (start.isdigit() and end.isdigit()):
                    raise ValueError(f"Неверный диапазон «{part}».")
                indexes.extend(range(int(start), int(end) + 1))
            elif part.isdigit():
                indexes.append(int(part))
            else:
                raise ValueError(f"Неверный номер записи «{part}».")
        selection = indexes
    by_index = {r.index: r for r in dataset.records}
    result: list[Record] = []
    for idx in selection:
        if idx not in by_index:
            raise ValueError(f"Записи с номером {idx} нет. Доступно записей: {len(dataset)}.")
        if by_index[idx] not in result:
            result.append(by_index[idx])
    return result


def search_records(dataset: DataSet, query: str) -> list[Record]:
    """Регистронезависимый поиск по всем простым значениям записи."""
    query = query.strip().casefold()
    if not query:
        return list(dataset.records)
    found = []
    for record in dataset.records:
        for value in record.values.values():
            if not isinstance(value, (list, dict)) and query in str(value).casefold():
                found.append(record)
                break
    return found
