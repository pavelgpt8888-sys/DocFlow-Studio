import json

import pytest

from docflow.cli import CliApp
from docflow.core import renderer
from docflow.core.history import History
from docflow.core.settings import Settings

import main as entry


def scripted(answers):
    it = iter(answers)

    def ask(_prompt):
        try:
            return next(it)
        except StopIteration:
            raise EOFError

    return ask


def test_cli_menu_without_selection_shows_errors(engine):
    out = []
    app = CliApp(engine, scripted(["4", "3", "5", "abc", "7"]), out.append, color=False, auto_open=False)
    assert app.run() == 0
    text = "\n".join(out)
    assert "Сначала выберите шаблон" in text
    assert "Сначала выберите данные" in text
    assert "Введите число от 1 до 7" in text
    assert "До встречи" in text


@pytest.mark.skipif(not renderer.is_available(), reason="WeasyPrint/Pango не установлены")
def test_cli_full_flow(engine):
    templates = [t.id for t in engine.list_templates()]
    data = [f.relative for f in engine.list_data_files()]
    out = []
    answers = ["1", str(templates.index("receipt") + 1),
               "2", str(data.index("receipts/receipts.csv") + 1),
               "3", "2", "4", "5", "7"]
    app = CliApp(engine, scripted(answers), out.append, color=False, auto_open=False)
    assert app.run() == 0
    text = "\n".join(out)
    assert "Выбран шаблон «Товарный чек»" in text
    assert "Готово: 1 из 1" in text
    assert "Готово: 6 из 6" in text
    assert len(list(engine.output_dir.glob("receipt_*.pdf"))) == 7


@pytest.mark.skipif(not renderer.is_available(), reason="WeasyPrint/Pango не установлены")
def test_cli_interactive_mapping(engine, tmp_path):
    csv = tmp_path / "odd.csv"
    csv.write_text("код,что,сколько стоит,штук\nA-1,Лампа,1500,2\n", encoding="utf-8")
    out = []
    answers = ["1", str([t.id for t in engine.list_templates()].index("receipt") + 1),
               "2", str(len(engine.list_data_files()) + 1), str(csv),
               "3", "1", "4", "1", "2", "3", "4", "7"]
    app = CliApp(engine, scripted(answers), out.append, color=False, auto_open=False)
    app.run()
    assert "Готово: 1 из 1" in "\n".join(out)
    saved = engine.settings.field_mappings["receipt::odd.csv"]
    assert saved == {"id": "код", "product": "что", "price": "сколько стоит", "qty": "штук"}


@pytest.mark.skipif(not renderer.is_available(), reason="WeasyPrint/Pango не установлены")
def test_main_batch_mode(tmp_path, project_root):
    code = entry.main(["--template", "certificate", "--data",
                       str(project_root / "data/certificates/certificates.json"),
                       "--record", "1,3", "--no-open", "--output", str(tmp_path / "o")])
    assert code == 0
    assert len(list((tmp_path / "o").glob("certificate_*.pdf"))) == 2


def test_main_batch_mode_errors(tmp_path, project_root):
    assert entry.main(["--template", "nope", "--data", "x.csv", "--all", "--no-open"]) == 2
    assert entry.main(["--template", "receipt", "--data", str(project_root / "data/receipts/receipts.csv"),
                       "--record", "99", "--no-open", "--output", str(tmp_path)]) == 2
    assert entry.main(["--template", "receipt"]) == 2


def test_settings_roundtrip_and_recent(tmp_path):
    path = tmp_path / "s.json"
    s = Settings.load(path)
    assert s.theme == "system" and s.auto_open_single
    for i in range(15):
        f = tmp_path / f"f{i}.csv"
        f.write_text("a\n1\n")
        s.add_recent(f)
    s.add_recent(tmp_path / "f3.csv")
    s.theme = "dark"
    s.save()
    again = Settings.load(path)
    assert again.theme == "dark"
    assert len(again.recent_files) == 10
    assert again.recent_files[0].endswith("f3.csv")


def test_corrupted_settings_fall_back_to_defaults(tmp_path):
    path = tmp_path / "s.json"
    path.write_text("{not json")
    assert Settings.load(path).theme == "system"
    path.write_text(json.dumps({"theme": 5, "auto_open_single": False, "unknown": 1}))
    s = Settings.load(path)
    assert s.theme == "system" and s.auto_open_single is False


def test_history_statuses(tmp_path):
    h = History(tmp_path / "h.db")
    h.add(source="gui", template="T", data_file="d.csv", requested=2, outputs=[tmp_path / "a.pdf"],
          failed=1, output_dir=tmp_path)
    h.add(source="gui", template="T", data_file="d.csv", requested=1, outputs=[], failed=1,
          output_dir=tmp_path)
    statuses = [e.status for e in h.list()]
    assert statuses == ["error", "partial"]
    h.clear()
    assert h.list() == []
