"""Денежные расчёты на Decimal и форматирование чисел по-русски."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

CENT = Decimal("0.01")
NBSP = " "
THIN = " "  # узкий неразрывный пробел для разрядов

MONEY_FIELDS = ("price", "total", "subtotal", "vat", "amount", "sum")
QUANTITY_FIELDS = ("qty", "quantity")


def parse_decimal(value: Any) -> Decimal:
    """Превращает «1 234,50», «1234.50», «1,234.50 ₽» или число в Decimal.

    Бросает ValueError, если строку нельзя прочитать как число.
    """
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise ValueError("логическое значение не является числом")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(repr(value))
    if value is None:
        raise ValueError("пустое значение")

    text = str(value).strip()
    text = re.sub(r"[\s  ']", "", text)
    text = re.sub(r"(руб\.?|р\.|₽|RUB|rub)$", "", text, flags=re.IGNORECASE)
    if not text:
        raise ValueError("пустое значение")

    if "," in text and "." in text:
        # Последний разделитель — десятичный, остальные — разряды.
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")

    if not re.fullmatch(r"[+-]?\d+(\.\d+)?", text):
        raise ValueError("ожидалось число")
    try:
        return Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - защищено регуляркой
        raise ValueError("ожидалось число") from exc


def quantize(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _group(digits: str) -> str:
    parts = []
    while len(digits) > 3:
        parts.insert(0, digits[-3:])
        digits = digits[:-3]
    parts.insert(0, digits)
    return THIN.join(parts)


def format_number(value: Decimal, places: int | None = 2) -> str:
    """12345.5 -> «12 345,50». При places=None дробная часть убирается, если она нулевая."""
    if places is None:
        if value == value.to_integral_value():
            places = 0
        else:
            places = 2 if abs(value.as_tuple().exponent) <= 2 else 3
    q = Decimal(1).scaleb(-places) if places else Decimal(1)
    value = value.quantize(q, rounding=ROUND_HALF_UP)
    sign = "-" if value < 0 else ""
    text = f"{abs(value):f}"
    whole, _, frac = text.partition(".")
    result = sign + _group(whole)
    if places:
        result += "," + frac.ljust(places, "0")
    return result


def format_money(value: Decimal, currency: str = "₽") -> str:
    return f"{format_number(value, 2)}{NBSP}{currency}"


# ------------------------------------------------------------ сумма прописью

_ONES_M = ("", "один", "два", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
_ONES_F = ("", "одна", "две", "три", "четыре", "пять", "шесть", "семь", "восемь", "девять")
_TEENS = ("десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать", "пятнадцать",
          "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать")
_TENS = ("", "", "двадцать", "тридцать", "сорок", "пятьдесят", "шестьдесят", "семьдесят",
         "восемьдесят", "девяносто")
_HUNDREDS = ("", "сто", "двести", "триста", "четыреста", "пятьсот", "шестьсот", "семьсот",
             "восемьсот", "девятьсот")
# (формы, женский род)
_SCALES = ((("рубль", "рубля", "рублей"), False), (("тысяча", "тысячи", "тысяч"), True),
           (("миллион", "миллиона", "миллионов"), False),
           (("миллиард", "миллиарда", "миллиардов"), False))


def plural_ru(n: int, forms: tuple[str, str, str]) -> str:
    n = abs(n) % 100
    if 11 <= n <= 19:
        return forms[2]
    n %= 10
    return forms[0] if n == 1 else forms[1] if 2 <= n <= 4 else forms[2]


def _triad(n: int, feminine: bool) -> list[str]:
    words = [_HUNDREDS[n // 100]]
    rest = n % 100
    if 10 <= rest <= 19:
        words.append(_TEENS[rest - 10])
    else:
        words.append(_TENS[rest // 10])
        words.append((_ONES_F if feminine else _ONES_M)[rest % 10])
    return [w for w in words if w]


def amount_in_words(value: Decimal) -> str:
    """467893.80 -> «Четыреста шестьдесят семь тысяч восемьсот девяносто три рубля 80 копеек»."""
    value = quantize(abs(value))
    rubles = int(value)
    kopecks = int((value - rubles) * 100)
    if rubles >= 10**12:
        raise ValueError("слишком большая сумма")
    parts: list[str] = []
    n, scale = rubles, 0
    groups: list[tuple[int, int]] = []
    while True:
        groups.append((n % 1000, scale))
        n //= 1000
        scale += 1
        if not n:
            break
    for triad, scale in reversed(groups):
        forms, feminine = _SCALES[scale]
        if triad == 0 and scale > 0:
            continue
        parts.extend(_triad(triad, feminine))
        if scale > 0:
            parts.append(plural_ru(triad, forms))
    if rubles == 0:
        parts.append("ноль")
    parts.append(plural_ru(rubles, _SCALES[0][0]))
    text = " ".join(parts)
    text = text[0].upper() + text[1:]
    return f"{text} {kopecks:02d} {plural_ru(kopecks, ('копейка', 'копейки', 'копеек'))}"
