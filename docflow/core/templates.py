"""Загрузка HTML-шаблонов, их метаданных и сопоставление полей."""

from __future__ import annotations

import re
from pathlib import Path

from .calculations import COMPUTED_FIELDS, SYSTEM_FIELDS
from .errors import TemplateError
from .models import TemplateInfo, ValidationReport
from .template_engine import CompiledTemplate

META_RE = re.compile(r"<!--\s*docflow\s*(.*?)-->", re.DOTALL | re.IGNORECASE)
MAX_TEMPLATE_SIZE = 2 * 1024 * 1024

# Частые синонимы: колонка данных -> поле шаблона.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "id": ("номер", "number", "no", "№", "doc_id", "document_id"),
    "number": ("номер", "номер счёта", "номер счета", "no", "№", "invoice_id", "doc_id", "id"),
    "product": ("товар", "наименование", "name", "item", "title", "название", "product_name"),
    "price": ("цена", "cost", "unit_price", "стоимость"),
    "qty": ("количество", "кол-во", "quantity", "count", "amount_qty"),
    "date": ("дата", "created", "created_at", "issued"),
    "recipient": ("получатель", "имя", "фио", "full_name", "name"),
    "program": ("программа", "курс", "course"),
    "client": ("клиент", "покупатель", "customer", "buyer"),
}


# Понятные подписи полей для диалога сопоставления.
FIELD_LABELS: dict[str, str] = {
    "id": "Номер документа", "number": "Номер счёта", "date": "Дата документа",
    "due_date": "Срок оплаты", "client": "Покупатель", "items": "Позиции (список товаров)",
    "product": "Наименование товара", "price": "Цена за единицу", "qty": "Количество",
    "recipient": "Получатель (ФИО)", "program": "Название программы",
    "certificate_id": "Номер сертификата",
}
def field_label(name: str) -> str:
    return FIELD_LABELS.get(name, name)


# Поля позиции, из которых строится одна позиция счёта, если данные «плоские».
ITEM_FIELDS = ("product", "price", "qty", "unit")


def flat_item_mapping(columns: list[str]) -> dict[str, str]:
    """Колонки плоской таблицы, из которых можно собрать позицию (товар, цена…)."""
    return suggest_mapping(list(ITEM_FIELDS), columns)


def parse_meta(source: str) -> dict[str, str]:
    m = META_RE.search(source)
    if not m:
        return {}
    meta = {}
    for line in m.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip():
            meta[key.strip().lower()] = value.strip()
    return meta


def _split_list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def read_template_source(path: Path) -> str:
    if not path.is_file():
        raise TemplateError(f"Шаблон «{path.name}» не найден.")
    if path.stat().st_size > MAX_TEMPLATE_SIZE:
        raise TemplateError(f"Шаблон «{path.name}» слишком большой (больше 2 МБ).")
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TemplateError(f"Шаблон «{path.name}» должен быть сохранён в UTF-8.") from exc


def load_template(path: str | Path) -> tuple[TemplateInfo, CompiledTemplate]:
    path = Path(path).expanduser().resolve()
    source = read_template_source(path)
    try:
        compiled = CompiledTemplate(source)
    except TemplateError as exc:
        raise TemplateError(f"Ошибка в шаблоне «{path.name}». {exc}") from exc

    meta = parse_meta(source)
    usage = compiled.usage
    fields = list(usage.fields)
    computed = [f for f in fields if f in COMPUTED_FIELDS]
    if "required" in meta:
        required = _split_list(meta["required"])
    else:
        required = [
            f for f in fields
            if f not in usage.optional and f not in COMPUTED_FIELDS and f not in SYSTEM_FIELDS
        ]
    title_match = re.search(r"<title>(.*?)</title>", source, re.DOTALL | re.IGNORECASE)
    info = TemplateInfo(
        id=path.stem,
        path=path,
        name=meta.get("name") or (title_match.group(1).strip() if title_match else path.stem),
        description=meta.get("description", ""),
        icon=meta.get("icon", "file"),
        page="receipt" if meta.get("page", "").lower() in ("receipt", "лента") else "a4",
        fields=fields,
        required=required,
        computed=computed,
        lists=sorted(usage.lists),
        types={k: v for k, v in usage.types.items()
               if k not in COMPUTED_FIELDS and k not in SYSTEM_FIELDS},
    )
    return info, compiled


def _norm(name: str) -> str:
    return re.sub(r"[\s_\-.]+", "", name.casefold())


def suggest_mapping(required: list[str], columns: list[str],
                    saved: dict[str, str] | None = None) -> dict[str, str]:
    """Подбирает колонку данных для каждого поля шаблона."""
    mapping: dict[str, str] = {}
    norm_columns = {_norm(c): c for c in columns}
    for name in required:
        if saved and saved.get(name) in columns:
            mapping[name] = saved[name]
            continue
        if name in columns:
            mapping[name] = name
            continue
        if _norm(name) in norm_columns:
            mapping[name] = norm_columns[_norm(name)]
            continue
        for alias in FIELD_ALIASES.get(name, ()):
            if _norm(alias) in norm_columns:
                mapping[name] = norm_columns[_norm(alias)]
                break
    return mapping


def validate_fields(info: TemplateInfo, columns: list[str],
                    mapping: dict[str, str] | None = None) -> ValidationReport:
    mapping = {k: v for k, v in (mapping or {}).items() if v in columns}
    # Списки позиций не сопоставляются с обычной колонкой: либо колонка с тем же
    # именем (JSON), либо позиция собирается из колонок товара и цены.
    full = suggest_mapping([f for f in info.required if f not in info.lists], columns, mapping)
    for name in info.lists:
        if name in info.required and name in columns:
            full[name] = name
    flat = flat_item_mapping(columns)
    missing = [f for f in info.required if f not in full
               and not (f in info.lists and {"product", "price"} <= flat.keys())]
    used = set(full.values()) | set(info.fields)
    unused = [c for c in columns if c not in used]
    return ValidationReport(mapping=full, missing=missing, unused_columns=unused)


def apply_mapping(values: dict, mapping: dict[str, str]) -> dict:
    """Возвращает копию записи, где поля шаблона заполнены из сопоставленных колонок."""
    result = dict(values)
    for template_field, column in mapping.items():
        if column in values:
            result[template_field] = values[column]
    return result
