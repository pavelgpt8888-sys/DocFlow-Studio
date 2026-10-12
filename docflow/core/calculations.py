"""Вычисляемые поля документов: стоимость позиции, итог, НДС, сумма к оплате.

Все расчёты выполняются в Decimal с округлением до копеек.

НДС по умолчанию считается так, как принято в российских счетах: цены уже
включают налог («В том числе НДС»). Если в данных vat_included = false,
налог начисляется сверху цены.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from .money import parse_decimal, quantize

COMPUTED_FIELDS = {"total", "subtotal", "vat", "total_qty", "items_count", "vat_included"}
SYSTEM_FIELDS = {"today"}
NUMERIC_FIELDS = ("price", "qty", "quantity", "total", "vat_rate", "discount")


def _is_true(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() not in ("false", "нет", "0", "no", "")
    return bool(value)


def _is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _parse_numbers(values: dict[str, Any], where: str, problems: list[str]) -> dict[str, Any]:
    result = dict(values)
    for key in NUMERIC_FIELDS:
        if key in result and not _is_empty(result[key]):
            try:
                result[key] = parse_decimal(result[key])
            except ValueError:
                problems.append(f"{where}поле «{key}» должно быть числом.")
    if "quantity" in result and "qty" not in result:
        result["qty"] = result["quantity"]
    return result


def _line_total(values: dict[str, Any]) -> Decimal | None:
    price, qty = values.get("price"), values.get("qty")
    if isinstance(price, Decimal) and isinstance(qty, Decimal):
        total = price * qty
        discount = values.get("discount")
        if isinstance(discount, Decimal):
            total -= discount
        return quantize(total)
    return None


def enrich(values: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Возвращает (контекст с вычисленными полями, список проблем)."""
    problems: list[str] = []
    ctx = _parse_numbers(values, "", problems)
    ctx.setdefault("today", date.today().isoformat())

    items = ctx.get("items")
    if isinstance(items, list):
        parsed_items = []
        subtotal = Decimal("0")
        total_qty = Decimal("0")
        for pos, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                problems.append(f"Позиция {pos}: ожидался объект.")
                continue
            item = _parse_numbers(item, f"Позиция {pos}: ", problems)
            line = _line_total(item)
            if line is not None and _is_empty(items[pos - 1].get("total")):
                item["total"] = line
            if isinstance(item.get("total"), Decimal):
                subtotal += item["total"]
            if isinstance(item.get("qty"), Decimal):
                total_qty += item["qty"]
            parsed_items.append(item)
        ctx["items"] = parsed_items
        ctx["items_count"] = len(parsed_items)
        ctx["total_qty"] = total_qty
        ctx["subtotal"] = quantize(subtotal)
        rate = ctx.get("vat_rate")
        included = _is_true(ctx.get("vat_included", True))
        ctx["vat_included"] = included
        if isinstance(rate, Decimal) and rate > 0:
            if included:
                ctx["vat"] = quantize(subtotal * rate / (Decimal(100) + rate))
                ctx["total"] = ctx["subtotal"]
            else:
                ctx["vat"] = quantize(subtotal * rate / Decimal(100))
                ctx["total"] = quantize(subtotal + ctx["vat"])
        else:
            ctx["vat"] = None
            ctx["total"] = ctx["subtotal"]
    else:
        line = _line_total(ctx)
        if line is not None and _is_empty(values.get("total")):
            ctx["total"] = line
    return ctx, problems

