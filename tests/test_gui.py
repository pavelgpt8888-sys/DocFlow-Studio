"""Дымовой тест интерфейса: окно собирается, загружает данные, показывает PDF и генерирует документы."""

import os
import time

import pytest

pytest.importorskip("PySide6.QtPdfWidgets")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from docflow.core import renderer  # noqa: E402

pytestmark = pytest.mark.skipif(not renderer.is_available(), reason="WeasyPrint/Pango не установлены")


def wait_until(condition, timeout=20.0):
    app = QApplication.instance()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        app.processEvents()
        if condition():
            return True
        time.sleep(0.02)
    return False


@pytest.fixture
def window(engine, monkeypatch):
    from docflow.ui import main_window as mw
    from docflow.ui.app import create_app
    from docflow.ui.theme import ThemeManager

    opened = []
    monkeypatch.setattr(mw, "open_path", lambda p: opened.append(p) or True)
    create_app([])
    win = mw.MainWindow(engine, ThemeManager("light"))
    win.opened = opened
    win.resize(1280, 800)
    win.show()
    yield win
    win.close()


def test_empty_states(window):
    assert window.preview.generate_btn.isEnabled() is False
    assert window.preview.stack.currentWidget() is window.preview.empty
    assert window.preview.empty.title.text() == "Выберите шаблон"
    assert window.documents.stack.currentWidget() is window.documents.empty


def test_full_flow_preview_and_generate(window, project_root):
    win = window
    win.set_template(next(t for t in win.templates if t.id == "receipt"))
    win.load_data(project_root / "data/receipts/receipts.csv")
    assert wait_until(lambda: win.dataset is not None and len(win.dataset) == 6)
    # Реальный PDF в предпросмотре
    assert wait_until(lambda: win.preview.stack.currentWidget() is win.preview.view)
    assert win.preview._documents[0].pageCount() == 1

    # Поиск
    win.documents.search.setText("наушники")
    assert win.documents.proxy.rowCount() == 1
    win.documents.search.setText("")

    # Одна запись → автооткрытие
    assert win.preview.generate_btn.isEnabled()
    win.generate()
    assert wait_until(lambda: win.last_result is not None)
    assert len(win.last_result.succeeded) == 1
    assert win.opened == [win.last_result.succeeded[0].path]
    assert win.preview.banner.title.text() == "PDF создан"

    # Все записи → без автооткрытия, предложение открыть папку
    win.documents.select_all()
    assert "Выбрано: 6 из 6" in win.documents.sel_label.text()
    win.last_result = None
    win.generate()
    assert wait_until(lambda: win.last_result is not None)
    assert len(win.last_result.succeeded) == 6
    assert len(win.opened) == 1
    assert win.preview.open_dir_btn.isVisible()


def test_theme_switch_and_pages(window):
    window.set_theme("dark")
    assert window.theme.palette.name == "dark"
    for key in ("templates", "sources", "history", "settings", "documents"):
        window.show_page(key)
    window.set_theme("light")
    assert window.theme.palette.name == "light"


def test_missing_fields_blocks_generation(window, project_root):
    win = window
    win.set_template(next(t for t in win.templates if t.id == "receipt"))
    win.load_data(project_root / "data/invoices/invoices.json")
    assert wait_until(lambda: win.dataset is not None and win.dataset.name == "invoices.json")
    assert set(win.missing) == {"product", "price", "qty"}
    assert not win.preview.generate_btn.isEnabled()
    assert win.preview.empty.title.text() == "Сопоставьте поля"


def test_broken_file_shows_message(window, tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    window.load_data(bad)
    assert wait_until(lambda: window.documents.empty.title.text() == "Не удалось загрузить файл")
    assert "ошибку JSON" in window.documents.empty.text.text()
