"""Минимальный безопасный шаблонизатор.

Поддерживается только:
    {{ поле }}, {{ item.поле }}, {{ поле|фильтр }}, {{ поле|default:"—" }}
    {% for item in items %} ... {% endfor %}   (внутри доступен loop.index)
    {% if поле %} ... {% else %} ... {% endif %}
    {# комментарий #}

Шаблон не может вызывать функции, обращаться к атрибутам Python-объектов
или выполнять код: выражение — это только путь из имён, разрешаемый
по словарям контекста. Каждое подставляемое значение экранируется.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable

from .errors import TemplateError
from .money import amount_in_words, format_money, format_number, parse_decimal

TOKEN_RE = re.compile(r"({{.*?}}|{%.*?%}|{#.*?#})", re.DOTALL)
NAME_RE = r"[A-Za-z_Ѐ-ӿ][\w]*"
PATH_RE = re.compile(rf"^{NAME_RE}(\.{NAME_RE})*$")
FILTER_RE = re.compile(rf"^({NAME_RE})(?::\s*(\"[^\"]*\"|'[^']*'))?$")
FOR_RE = re.compile(rf"^for\s+({NAME_RE})\s+in\s+(\S+)$")
IF_RE = re.compile(r"^if\s+(not\s+)?(\S+)$")
MAX_ITERATIONS = 10_000

MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)


def to_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:19] if "T" in text else text, fmt).date()
        except ValueError:
            continue
    return None


def _is_blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _filter_money(value: Any, arg: str | None) -> str:
    if _is_blank(value):
        return ""
    try:
        return format_money(parse_decimal(value), arg or "₽")
    except ValueError:
        return str(value)


def _filter_number(value: Any, arg: str | None) -> str:
    if _is_blank(value):
        return ""
    try:
        places = int(arg) if arg and arg.isdigit() else None
        return format_number(parse_decimal(value), places)
    except ValueError:
        return str(value)


def _filter_date(value: Any, arg: str | None) -> str:
    if _is_blank(value):
        return ""
    d = to_date(value)
    return d.strftime("%d.%m.%Y") if d else str(value)


def _filter_date_long(value: Any, arg: str | None) -> str:
    if _is_blank(value):
        return ""
    d = to_date(value)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year} г." if d else str(value)


def _filter_in_words(value: Any, arg: str | None) -> str:
    if _is_blank(value):
        return ""
    try:
        return amount_in_words(parse_decimal(value))
    except ValueError:
        return ""


def _filter_default(value: Any, arg: str | None) -> Any:
    return value if _truthy(value) else (arg or "")


FILTERS: dict[str, Callable[[Any, str | None], Any]] = {
    "money": _filter_money,
    "number": _filter_number,
    "date": _filter_date,
    "date_long": _filter_date_long,
    "default": _filter_default,
    "upper": lambda v, a: str(v).upper(),
    "lower": lambda v, a: str(v).lower(),
    "capitalize": lambda v, a: str(v)[:1].upper() + str(v)[1:],
    "count": lambda v, a: len(v) if isinstance(v, (list, dict, str)) else 0,
    "in_words": _filter_in_words,
}

# Какой тип значения ожидает фильтр — для проверки данных до рендеринга.
FILTER_TYPES = {"money": "number", "number": "number", "in_words": "number",
                "date": "date", "date_long": "date"}


def _truthy(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Decimal):
        return value != 0
    return bool(value)


def to_display(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return format_number(value, None)
    if isinstance(value, bool):
        return "да" if value else "нет"
    if isinstance(value, (list, dict)):
        return ""
    return str(value)


# ---------------------------------------------------------------- узлы дерева


@dataclass
class Text:
    text: str


@dataclass
class Var:
    path: str
    filters: list[tuple[str, str | None]]
    line: int


@dataclass
class For:
    var: str
    path: str
    body: list = field(default_factory=list)
    line: int = 0


@dataclass
class If:
    path: str
    negate: bool
    body: list = field(default_factory=list)
    else_body: list = field(default_factory=list)
    line: int = 0


# ---------------------------------------------------------------- разбор


def _line_of(source: str, pos: int) -> int:
    return source.count("\n", 0, pos) + 1


def _parse_var(inner: str, line: int) -> Var:
    parts = [p.strip() for p in inner.split("|")]
    path = parts[0]
    if not PATH_RE.match(path):
        raise TemplateError(f"Строка {line}: недопустимое выражение «{path}». Разрешены только имена полей.")
    filters = []
    for spec in parts[1:]:
        m = FILTER_RE.match(spec)
        if not m or m.group(1) not in FILTERS:
            raise TemplateError(f"Строка {line}: неизвестный фильтр «{spec}».")
        arg = m.group(2)[1:-1] if m.group(2) else None
        filters.append((m.group(1), arg))
    return Var(path, filters, line)


def parse(source: str) -> list:
    root: list = []
    stack: list[tuple[Any, list]] = []  # (узел-блок, текущий список детей)
    current = root
    pos = 0
    for m in TOKEN_RE.finditer(source):
        if m.start() > pos:
            current.append(Text(source[pos : m.start()]))
        pos = m.end()
        token = m.group(0)
        line = _line_of(source, m.start())
        inner = token[2:-2].strip()
        if token.startswith("{#"):
            continue
        if token.startswith("{{"):
            current.append(_parse_var(inner, line))
            continue
        # {% ... %}
        if fm := FOR_RE.match(inner):
            if not PATH_RE.match(fm.group(2)):
                raise TemplateError(f"Строка {line}: недопустимый список «{fm.group(2)}».")
            node = For(fm.group(1), fm.group(2), line=line)
            current.append(node)
            stack.append((node, current))
            current = node.body
        elif im := IF_RE.match(inner):
            if not PATH_RE.match(im.group(2)):
                raise TemplateError(f"Строка {line}: недопустимое условие «{im.group(2)}».")
            node = If(im.group(2), bool(im.group(1)), line=line)
            current.append(node)
            stack.append((node, current))
            current = node.body
        elif inner == "else":
            if not stack or not isinstance(stack[-1][0], If):
                raise TemplateError(f"Строка {line}: «else» без «if».")
            current = stack[-1][0].else_body
        elif inner in ("endfor", "endif"):
            expected = For if inner == "endfor" else If
            if not stack or not isinstance(stack[-1][0], expected):
                raise TemplateError(f"Строка {line}: лишний «{inner}».")
            _, current = stack.pop()
        else:
            raise TemplateError(f"Строка {line}: неизвестная конструкция «{{% {inner} %}}».")
    if pos < len(source):
        current.append(Text(source[pos:]))
    if stack:
        node = stack[-1][0]
        kind = "for" if isinstance(node, For) else "if"
        raise TemplateError(f"Строка {node.line}: блок «{kind}» не закрыт.")
    return root


# ---------------------------------------------------------------- анализ полей


@dataclass
class FieldUsage:
    fields: list[str] = field(default_factory=list)  # верхнеуровневые поля, по порядку
    optional: set[str] = field(default_factory=set)
    lists: set[str] = field(default_factory=set)  # поля, по которым идёт цикл
    types: dict[str, str] = field(default_factory=dict)  # поле -> "date" | "number"


def analyze(nodes: list) -> FieldUsage:
    usage = FieldUsage()
    required_seen: set[str] = set()

    def add(name: str, optional: bool) -> None:
        if name not in usage.fields:
            usage.fields.append(name)
        if optional:
            usage.optional.add(name)
        else:
            required_seen.add(name)

    def walk(items: list, bound: set[str], conditional: bool) -> None:
        for node in items:
            if isinstance(node, Var):
                root = node.path.split(".")[0]
                if root not in bound:
                    is_opt = conditional or any(f == "default" for f, _ in node.filters)
                    add(root, is_opt)
                    if "." not in node.path:
                        for f, _ in node.filters:
                            if f in FILTER_TYPES:
                                usage.types.setdefault(root, FILTER_TYPES[f])
            elif isinstance(node, For):
                root = node.path.split(".")[0]
                if root not in bound:
                    add(root, conditional)
                    usage.lists.add(root)
                walk(node.body, bound | {node.var, "loop"}, conditional)
            elif isinstance(node, If):
                root = node.path.split(".")[0]
                if root not in bound:
                    add(root, True)
                walk(node.body, bound, True)
                walk(node.else_body, bound, True)

    walk(nodes, set(), False)
    usage.optional -= required_seen
    return usage


# ---------------------------------------------------------------- отрисовка


def _resolve(path: str, scopes: list[dict]) -> Any:
    head, *rest = path.split(".")
    value: Any = None
    for scope in reversed(scopes):
        if head in scope:
            value = scope[head]
            break
    for part in rest:
        value = value.get(part) if isinstance(value, dict) else None
    return value


def _render(nodes: list, scopes: list[dict], out: list[str], budget: list[int]) -> None:
    for node in nodes:
        if isinstance(node, Text):
            out.append(node.text)
        elif isinstance(node, Var):
            value = _resolve(node.path, scopes)
            for name, arg in node.filters:
                value = FILTERS[name](value, arg)
            out.append(html.escape(to_display(value), quote=True))
        elif isinstance(node, For):
            items = _resolve(node.path, scopes)
            if not isinstance(items, list):
                continue
            for i, item in enumerate(items, start=1):
                budget[0] -= 1
                if budget[0] < 0:
                    raise TemplateError("Шаблон содержит слишком много повторений.")
                loop = {"index": i, "first": i == 1, "last": i == len(items)}
                _render(node.body, scopes + [{node.var: item, "loop": loop}], out, budget)
        elif isinstance(node, If):
            value = _truthy(_resolve(node.path, scopes))
            if node.negate:
                value = not value
            _render(node.body if value else node.else_body, scopes, out, budget)


class CompiledTemplate:
    def __init__(self, source: str):
        self.source = source
        self.nodes = parse(source)
        self.usage = analyze(self.nodes)

    def render(self, context: dict[str, Any]) -> str:
        out: list[str] = []
        _render(self.nodes, [dict(context)], out, [MAX_ITERATIONS])
        return "".join(out)


def render_string(source: str, context: dict[str, Any]) -> str:
    return CompiledTemplate(source).render(context)
