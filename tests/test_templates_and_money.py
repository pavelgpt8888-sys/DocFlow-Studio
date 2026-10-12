from decimal import Decimal

import pytest

from docflow.core.calculations import enrich
from docflow.core.discovery import find_data_files, find_templates
from docflow.core.errors import TemplateError
from docflow.core.money import amount_in_words, format_money, format_number, parse_decimal
from docflow.core.template_engine import CompiledTemplate, render_string
from docflow.core.templates import load_template, suggest_mapping, validate_fields

from .conftest import PROJECT_ROOT, write

# ------------------------------------------------------------------ деньги


@pytest.mark.parametrize("raw, expected", [
    ("1234.50", "1234.50"), ("1 234,50", "1234.50"), ("1,234.50", "1234.50"),
    ("1.234,50", "1234.50"), ("89990", "89990"), ("12 990,99 ₽", "12990.99"),
    (3, "3"), (0.1, "0.1"), ("-5", "-5"),
])
def test_parse_decimal(raw, expected):
    assert parse_decimal(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["", "abc", "1,2,3x", None, True])
def test_parse_decimal_rejects(raw):
    with pytest.raises(ValueError):
        parse_decimal(raw)


def test_money_format():
    assert format_number(Decimal("1234567.5")) == "1 234 567,50"
    assert format_money(Decimal("0.005")) == "0,01 ₽"  # округление вверх
    assert format_number(Decimal("3"), None) == "3"


def test_total_is_exact_decimal():
    ctx, problems = enrich({"price": "0.1", "qty": "3"})
    assert not problems
    assert ctx["total"] == Decimal("0.30")  # с float было бы 0.30000000000000004
    ctx, _ = enrich({"price": "12990.99", "qty": "2"})
    assert ctx["total"] == Decimal("25981.98")


def test_invoice_vat_on_top():
    ctx, problems = enrich({"vat_rate": 20, "vat_included": "false", "items": [
        {"product": "A", "qty": 3, "price": "89990.00"},
        {"product": "B", "qty": "3", "price": "32490,50"},
        {"product": "C", "qty": 3, "price": "7490.00"},
    ]})
    assert not problems
    assert ctx["items"][1]["total"] == Decimal("97471.50")
    assert ctx["subtotal"] == Decimal("389911.50")
    assert ctx["vat"] == Decimal("77982.30")
    assert ctx["total"] == Decimal("467893.80")
    assert ctx["items_count"] == 3


def test_invoice_vat_included_by_default():
    # Российский счёт: цены уже с НДС, налог выделяется «в том числе».
    ctx, problems = enrich({"vat_rate": 22, "items": [{"product": "A", "qty": 1, "price": "122.00"}]})
    assert not problems and ctx["vat_included"] is True
    assert ctx["vat"] == Decimal("22.00")
    assert ctx["total"] == ctx["subtotal"] == Decimal("122.00")


@pytest.mark.parametrize("amount, words", [
    ("467893.80", "Четыреста шестьдесят семь тысяч восемьсот девяносто три рубля 80 копеек"),
    ("1.01", "Один рубль 01 копейка"),
    ("21000", "Двадцать одна тысяча рублей 00 копеек"),
    ("2001001.05", "Два миллиона одна тысяча один рубль 05 копеек"),
    ("0.50", "Ноль рублей 50 копеек"),
    ("112", "Сто двенадцать рублей 00 копеек"),
])
def test_amount_in_words(amount, words):
    assert amount_in_words(Decimal(amount)) == words


def test_empty_values_never_render_none():
    out = render_string("[{{ a|money }}][{{ b|number }}][{{ c|date_long }}][{{ d }}][{{ e|in_words }}]",
                        {"a": None, "b": "", "c": None, "d": None})
    assert out == "[][][][][]"


def test_invalid_number_reported_without_value():
    _, problems = enrich({"price": "секретно", "qty": "1"})
    assert problems == ["поле «price» должно быть числом."]
    assert "секретно" not in problems[0]


# ------------------------------------------------------------------ шаблонизатор


def test_placeholders_and_escaping():
    html = render_string("<p>{{ product }} — {{ qty }}</p>",
                         {"product": "<script>alert(1)</script> & «Ко»", "qty": 2})
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; «Ко»" in html


def test_attribute_escaping():
    html = render_string('<a title="{{ t }}">x</a>', {"t": '" onmouseover="x'})
    assert 'onmouseover="x' not in html
    assert "&quot;" in html


def test_loops_conditions_filters():
    src = ("{% for i in items %}{{ loop.index }}.{{ i.name|upper }}={{ i.price|money }};{% endfor %}"
           "{% if note %}[{{ note }}]{% else %}[нет]{% endif %}{{ missing|default:\"—\" }}")
    out = render_string(src, {"items": [{"name": "чай", "price": "10"}, {"name": "кофе", "price": 5}]})
    assert out == "1.ЧАЙ=10,00 ₽;2.КОФЕ=5,00 ₽;[нет]—"


def test_dates():
    assert render_string("{{ d|date_long }}", {"d": "2026-10-01"}) == "1 октября 2026 г."
    assert render_string("{{ d|date }}", {"d": "2026-10-01"}) == "01.10.2026"


@pytest.mark.parametrize("src", [
    "{{ __import__('os') }}", "{{ a.__class__ }}x{{ f() }}", "{{ x|evil }}",
    "{% for a in b %}", "{% endif %}", "{% import os %}", "{{ 1 + 1 }}",
])
def test_template_cannot_execute_code(src):
    with pytest.raises(TemplateError):
        CompiledTemplate(src)


def test_dunder_path_resolves_only_dict_keys():
    # Даже допустимое по синтаксису имя ищется только в словарях, а не в атрибутах Python.
    assert render_string("{{ obj.__class__ }}", {"obj": {"a": 1}}) == ""


def test_field_analysis():
    t = CompiledTemplate("{{ id }}{{ seller|default:'x' }}{% if note %}{{ note }}{% endif %}"
                         "{% for it in items %}{{ it.name }}{% endfor %}{{ total }}")
    assert t.usage.fields == ["id", "seller", "note", "items", "total"]
    assert t.usage.optional == {"seller", "note"}


# ------------------------------------------------------------------ шаблоны и поиск


def test_demo_templates_metadata():
    info, _ = load_template(PROJECT_ROOT / "templates" / "receipt.html")
    assert info.name == "Товарный чек"
    assert info.page == "receipt"
    assert info.required == ["id", "product", "price", "qty"]
    assert "total" in info.computed
    inv, _ = load_template(PROJECT_ROOT / "templates" / "invoice.html")
    assert inv.required == ["number", "client", "items"]  # дата необязательна — тогда сегодняшняя
    assert inv.lists == ["items"] and inv.types["due_date"] == "date"
    cert, _ = load_template(PROJECT_ROOT / "templates" / "certificate.html")
    assert set(cert.required) == {"recipient", "program", "date", "certificate_id"}


def test_find_templates_recursive_and_skips_hidden(tmp_path):
    write(tmp_path / "a.html", "<p>{{ x }}</p>")
    write(tmp_path / "nested" / "deep" / "b.htm", "<p>{{ y }}</p>")
    write(tmp_path / ".hidden" / "c.html", "x")
    write(tmp_path / ".venv" / "d.html", "x")
    write(tmp_path / "notes.txt", "x")
    names = sorted(p.name for p in find_templates([tmp_path]))
    assert names == ["a.html", "b.htm"]


def test_find_demo_templates_and_data():
    names = {p.name for p in find_templates([PROJECT_ROOT / "templates"])}
    assert {"receipt.html", "invoice.html", "certificate.html"} <= names
    files = {f.name for f in find_data_files([PROJECT_ROOT / "data"])}
    assert {"receipts.csv", "receipts.json", "invoices.json", "certificates.csv"} <= files


def test_mapping_aliases_and_validation():
    info, _ = load_template(PROJECT_ROOT / "templates" / "receipt.html")
    mapping = suggest_mapping(info.required, ["Номер", "Товар", "Цена", "Количество"])
    assert mapping == {"id": "Номер", "product": "Товар", "price": "Цена", "qty": "Количество"}
    report = validate_fields(info, ["id", "product", "cost"])
    assert report.missing == ["qty"]
    assert report.mapping["price"] == "cost"
    report = validate_fields(info, ["a", "b", "c", "d"], {"id": "a", "product": "b", "price": "c", "qty": "d"})
    assert report.ok


def test_invoice_accepts_flat_table_and_number_alias():
    inv, _ = load_template(PROJECT_ROOT / "templates" / "invoice.html")
    report = validate_fields(inv, ["id", "product", "price", "qty", "date"])
    assert report.missing == ["client"]  # позиции собираются из товара и цены, номер — из id
    assert report.mapping["number"] == "id"


def test_broken_template_reports_line(tmp_path):
    path = write(tmp_path / "broken.html", "<p>\n{% for x in items %}\n{{ x }}</p>")
    with pytest.raises(TemplateError, match="Строка 2"):
        load_template(path)
