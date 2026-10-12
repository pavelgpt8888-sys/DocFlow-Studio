"""Уникальные и безопасные имена файлов результатов."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh",
    "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o",
    "п": "p", "р": "r", "с": "s", "т": "t", "у": "u", "ф": "f", "х": "h", "ц": "ts",
    "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu",
    "я": "ya",
})


def slugify(text: str, max_length: int = 40) -> str:
    text = str(text).lower().translate(TRANSLIT)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text[:max_length].strip("-") or "document"


def build_filename(template_id: str, record_label: str, when: datetime | None = None) -> str:
    when = when or datetime.now()
    return f"{slugify(template_id, 24)}_{slugify(record_label)}_{when:%Y%m%d-%H%M%S}.pdf"


def reserve_path(directory: Path, filename: str):
    """Атомарно создаёт новый файл, не перезаписывая существующие.

    Возвращает (путь, открытый бинарный файл). При совпадении имени
    добавляется суффикс -2, -3 и т. д.
    """
    directory.mkdir(parents=True, exist_ok=True)
    stem, suffix = Path(filename).stem, Path(filename).suffix
    candidate = directory / filename
    n = 2
    while True:
        try:
            return candidate, open(candidate, "xb")
        except FileExistsError:
            candidate = directory / f"{stem}-{n}{suffix}"
            n += 1
            if n > 10_000:
                raise
