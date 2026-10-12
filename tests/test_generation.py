import socket
from datetime import datetime
from pathlib import Path

import pytest
from pypdf import PdfReader

from docflow.core import renderer
from docflow.core.data_loader import load_dataset
from docflow.core.errors import ValidationError
from docflow.core.models import Record
from docflow.core.naming import build_filename, reserve_path, slugify

from .conftest import PROJECT_ROOT, write

pytestmark = pytest.mark.skipif(not renderer.is_available(),
                                reason="WeasyPrint/Pango не установлены")

DATA = PROJECT_ROOT / "data"


def pdf_text(path: Path) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(path).pages)


def norm(text: str) -> str:
    return " ".join(text.replace(" ", " ").replace(" ", " ").split())


def test_receipt_pdf_content(engine):
    info = engine.find_template("receipt")
    ds = engine.load_data(DATA / "receipts" / "receipts.csv", remember=False)
    result = engine.generate(info, ds, [ds.records[1]])
    assert len(result.succeeded) == 1
    path = result.succeeded[0].path
    assert path.parent == engine.output_dir and path.suffix == ".pdf"
    assert path.read_bytes().startswith(b"%PDF")
    text = norm(pdf_text(path))
    assert "Товарный чек № R-1002" in norm(text.replace("ТОВАРНЫЙ ЧЕК", "Товарный чек"))
    assert "Смартфон Nova X5" in text
    assert "109 980,00 ₽" in text  # 54 990 × 2
    assert "нефискальный".upper() in text.upper()


def test_cyrillic_windows1251_with_mapping(engine):
    info = engine.find_template("receipt")
    ds = engine.load_data(DATA / "receipts" / "receipts_windows1251.csv", remember=False)
    report = engine.validate(info, ds)
    assert report.ok
    result = engine.generate(info, ds, ds.records[:1], report.mapping)
    path = result.succeeded[0].path
    assert "r-1001" in path.name  # метка записи берётся после сопоставления полей
    text = norm(pdf_text(path))
    assert "Ноутбук AeroBook 14 Pro" in text
    assert "89 990,00 ₽" in text


def test_invoice_multipage_and_vat(engine):
    info = engine.find_template("invoice")
    ds = engine.load_data(DATA / "invoices" / "invoices.json", remember=False)
    result = engine.generate(info, ds, ds.records)
    assert len(result.succeeded) == 5 and not result.failed
    first = norm(pdf_text(result.succeeded[0].path))
    assert "Всего к оплате: 389 911,50 ₽" in first
    assert "В том числе НДС (22%): 70 311,91" in first
    assert "Триста восемьдесят девять тысяч девятьсот одиннадцать рублей 50 копеек" in first
    assert "None" not in first and "Подытог" not in first
    on_top = norm(pdf_text(next(d.path for d in result.succeeded if "0143" in d.path.name)))
    assert "НДС (22%): 68 640,00" in on_top and "Всего к оплате: 380 640,00 ₽" in on_top
    big = next(d.path for d in result.succeeded if "0145" in d.path.name)
    assert len(PdfReader(big).pages) >= 2  # таблица переносится на вторую страницу
    assert "Страница 2 из" in norm(pdf_text(big))


def test_invoice_from_flat_csv(engine, tmp_path):
    info = engine.find_template("invoice")
    path = write(tmp_path / "flat.csv", "id,client,product,price,qty\nA-7,ООО «Тест»,Монитор,1000,2\n")
    ds = engine.load_data(path, remember=False)
    report = engine.validate(info, ds)
    assert report.ok
    doc = engine.generate(info, ds, ds.records, report.mapping).succeeded[0].path
    text = norm(pdf_text(doc))
    assert "№ A-7" in text and "Монитор" in text
    assert "ООО«Тест»" in text.replace(" ", "")  # извлечение текста иногда вставляет пробел из-за кернинга
    assert "Всего к оплате: 2 000,00 ₽" in text


def test_wrong_mapping_is_rejected(engine):
    """Колонка с товаром в поле даты и строка вместо позиций — понятная ошибка, а не мусор в PDF."""
    info = engine.find_template("invoice")
    ds = engine.load_data(DATA / "receipts" / "receipts.csv", remember=False)
    mapping = {"number": "price", "date": "product", "client": "id", "items": "qty"}
    result = engine.generate(info, ds, ds.records[:1], mapping)
    assert not result.succeeded
    error = result.failed[0].error
    assert "«date» должно быть датой" in error
    assert "«items» должно содержать список позиций" in error


def test_compatible_files(engine):
    names = {f.name for f in engine.compatible_files(engine.find_template("certificate"))}
    assert names == {"certificates.csv", "certificates.json"}
    receipts = {f.name for f in engine.compatible_files(engine.find_template("receipt"))}
    assert "receipts_windows1251.csv" in receipts and "invoices.json" not in receipts


def test_certificate_batch_and_page_size(engine):
    info = engine.find_template("certificate")
    ds = engine.load_data(DATA / "certificates" / "certificates.csv", remember=False)
    result = engine.generate(info, ds, ds.records)
    assert len(result.succeeded) == 5
    page = PdfReader(result.succeeded[0].path).pages[0]
    w, h = float(page.mediabox.width), float(page.mediabox.height)
    assert round(w) == 842 and round(h) == 595  # A4 альбомная
    assert "Анна Сергеевна Вымышленная" in norm(pdf_text(result.succeeded[0].path))


def test_receipt_tape_width(engine):
    info = engine.find_template("receipt")
    ds = engine.load_data(DATA / "receipts" / "receipts.json", remember=False)
    path = engine.generate(info, ds, ds.records[:1]).succeeded[0].path
    width_mm = float(PdfReader(path).pages[0].mediabox.width) * 25.4 / 72
    assert round(width_mm) == 80


def test_unique_names_never_overwrite(engine):
    info = engine.find_template("receipt")
    ds = engine.load_data(DATA / "receipts" / "receipts.csv", remember=False)
    a = engine.generate(info, ds, ds.records[:1]).succeeded[0].path
    original = a.read_bytes()
    b = engine.generate(info, ds, ds.records[:1]).succeeded[0].path
    c = engine.generate(info, ds, ds.records[:1]).succeeded[0].path
    assert len({a, b, c}) == 3
    assert a.read_bytes() == original


def test_reserve_path_suffixes(tmp_path):
    p1, f1 = reserve_path(tmp_path, "doc.pdf")
    p2, f2 = reserve_path(tmp_path, "doc.pdf")
    f1.close(), f2.close()
    assert p1.name == "doc.pdf" and p2.name == "doc-2.pdf"


def test_filename_slug():
    assert slugify("Счёт № СЧ-2026/01") == "schet-sch-2026-01"
    name = build_filename("receipt", "R-1001", datetime(2026, 10, 12, 9, 5, 7))
    assert name == "receipt_r-1001_20261012-090507.pdf"


def test_bad_record_does_not_break_batch(engine, tmp_path):
    info = engine.find_template("receipt")
    path = write(tmp_path / "mixed.csv", "id,product,price,qty\n1,Чайник,990,1\n2,,100,1\n3,Кофе,abc,1\n")
    ds = engine.load_data(path, remember=False)
    result = engine.generate(info, ds, ds.records)
    assert len(result.succeeded) == 1
    assert len(result.failed) == 2
    assert "product" in result.failed[0].error
    assert "price" in result.failed[1].error
    assert len(list(engine.output_dir.glob("*.pdf"))) == 1  # без пустых «обрубков»


def test_render_html_validation_error(engine):
    info = engine.find_template("receipt")
    with pytest.raises(ValidationError) as exc:
        engine.render_html(info, Record(1, {"id": "1"}), {})
    assert "product" in str(exc.value)


def test_cancel_batch(engine):
    info = engine.find_template("receipt")
    ds = engine.load_data(DATA / "receipts" / "receipts.csv", remember=False)
    calls = []
    result = engine.generate(info, ds, ds.records, progress=lambda d, t: calls.append(d),
                             should_cancel=lambda: len(calls) >= 2)
    assert result.cancelled and len(result.succeeded) == 2


def test_history_records_operation(engine):
    info = engine.find_template("certificate")
    ds = engine.load_data(DATA / "certificates" / "certificates.json", remember=False)
    engine.generate(info, ds, ds.records[:2], source="cli")
    entry = engine.history.list()[0]
    assert (entry.template, entry.data_file, entry.requested, entry.succeeded) == \
        ("Сертификат", "certificates.json", 2, 2)
    assert entry.status == "ok" and entry.source == "cli"
    assert all(p.exists() for p in entry.outputs)


def test_network_resources_are_blocked(engine, tmp_path, monkeypatch):
    attempts = []

    def forbidden(*args, **kwargs):
        attempts.append(args)
        raise OSError("network disabled in test")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    tpl = write(tmp_path / "tpl" / "net.html",
                '<link rel="stylesheet" href="https://example.com/x.css">'
                '<img src="http://example.com/a.png"><img src="file:///etc/hosts">'
                "<p>{{ id }}</p>")
    info = engine.get_template(tpl)[0]
    out = tmp_path / "net.pdf"
    renderer.render_pdf(engine.render_html(info, Record(1, {"id": "ok"}), {}), tpl.parent, out)
    assert out.exists() and not attempts
    assert not renderer.is_allowed_url("https://example.com/x.css", [tpl.parent])
    assert not renderer.is_allowed_url("file:///etc/hosts", [tpl.parent])
    assert renderer.is_allowed_url("data:text/plain,hi", [tpl.parent])


def test_at_least_five_real_pdfs(engine):
    """Сводная проверка: создаём по документу каждого вида и пакет — всего не меньше пяти PDF."""
    jobs = [("receipt", "receipts/receipts.csv"), ("invoice", "invoices/invoices.json"),
            ("certificate", "certificates/certificates.csv")]
    created = []
    for tid, rel in jobs:
        info = engine.find_template(tid)
        ds = load_dataset(DATA / rel)
        result = engine.generate(info, ds, ds.records[:2], engine.validate(info, ds).mapping)
        created += [d.path for d in result.succeeded]
    assert len(created) >= 5
    for path in created:
        reader = PdfReader(path)
        assert len(reader.pages) >= 1
        assert pdf_text(path).strip()
