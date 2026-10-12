import pytest

from docflow.core.data_loader import load_dataset, search_records, select_records
from docflow.core.errors import DataLoadError

from .conftest import PROJECT_ROOT, write

DATA = PROJECT_ROOT / "data" / "receipts"


def test_csv_utf8_comma():
    ds = load_dataset(DATA / "receipts.csv")
    assert ds.columns == ["id", "product", "price", "qty"]
    assert len(ds) == 6
    assert ds.encoding == "utf-8"
    assert ds.delimiter == ","
    assert ds.records[0].values["product"].startswith("Ноутбук")
    # Кавычки внутри поля сохраняются
    assert '27"' in ds.records[2].values["product"]


def test_csv_utf8_bom_semicolon():
    ds = load_dataset(DATA / "receipts_utf8_bom_semicolon.csv")
    assert ds.encoding == "utf-8-sig"
    assert ds.delimiter == ";"
    assert ds.columns[0] == "id"  # BOM не попал в имя колонки
    assert ds.records[2].values["price"] == "32490,50"


def test_csv_windows_1251():
    ds = load_dataset(DATA / "receipts_windows1251.csv")
    assert ds.encoding == "cp1251"
    assert ds.columns == ["Номер", "Товар", "Цена", "Количество"]
    assert ds.records[1].values["Товар"].startswith("Смартфон")


def test_csv_tab_delimiter_and_short_rows(tmp_path):
    path = write(tmp_path / "t.csv", "id\tproduct\tprice\tqty\n1\tЧайник\t990\n2\tКофе\t450\t2\n")
    ds = load_dataset(path)
    assert ds.delimiter == "\t"
    assert ds.records[0].values["qty"] == ""
    assert ds.warnings and "Строка 2" in ds.warnings[0]


def test_json_list_and_wrapped():
    ds = load_dataset(DATA / "receipts.json")
    assert len(ds) == 5 and ds.format == "json"
    inv = load_dataset(PROJECT_ROOT / "data" / "invoices" / "invoices.json")
    assert len(inv) == 5
    assert isinstance(inv.records[0].values["items"], list)


def test_json_skips_non_objects(tmp_path):
    path = write(tmp_path / "x.json", '[{"id": 1}, 5, {"id": 2, "extra": "a"}]')
    ds = load_dataset(path)
    assert len(ds) == 2
    assert ds.columns == ["id", "extra"]
    assert ds.warnings


@pytest.mark.parametrize("content, message", [
    ("", "пустой"),
    ("   \n\n", "не содержит"),
    ("{broken", "ошибку JSON"),
    ("42", "список объектов"),
])
def test_bad_json(tmp_path, content, message):
    path = write(tmp_path / "bad.json", content)
    with pytest.raises(DataLoadError, match=message):
        load_dataset(path)


def test_empty_csv_and_header_only(tmp_path):
    with pytest.raises(DataLoadError):
        load_dataset(write(tmp_path / "e.csv", ""))
    ds = load_dataset(write(tmp_path / "h.csv", "id,product,price,qty\n"))
    assert len(ds) == 0 and ds.columns == ["id", "product", "price", "qty"]


def test_missing_and_unsupported(tmp_path):
    with pytest.raises(DataLoadError, match="не найден"):
        load_dataset(tmp_path / "nope.csv")
    with pytest.raises(DataLoadError, match="не поддерживается"):
        load_dataset(write(tmp_path / "a.xlsx", "x"))


def test_binary_garbage_does_not_crash(tmp_path):
    path = write(tmp_path / "garbage.csv", bytes(range(256)) * 4)
    with pytest.raises(DataLoadError, match="двоичный"):
        load_dataset(path)
    broken = write(tmp_path / "broken.csv", 'id,product\n1,"Чайник\n')
    ds = load_dataset(broken)  # незакрытая кавычка не роняет программу
    assert ds.columns == ["id", "product"]


def test_select_records():
    ds = load_dataset(DATA / "receipts.csv")
    assert [r.index for r in select_records(ds, "all")] == [1, 2, 3, 4, 5, 6]
    assert [r.index for r in select_records(ds, "2")] == [2]
    assert [r.index for r in select_records(ds, "1,3-5")] == [1, 3, 4, 5]
    assert [r.index for r in select_records(ds, [6, 6, 1])] == [6, 1]
    with pytest.raises(ValueError, match="Записи с номером 9"):
        select_records(ds, "9")
    with pytest.raises(ValueError):
        select_records(ds, "abc")


def test_search_is_case_insensitive_cyrillic():
    ds = load_dataset(DATA / "receipts.csv")
    found = search_records(ds, "НАУШНИКИ")
    assert [r.values["id"] for r in found] == ["R-1005"]
    assert len(search_records(ds, "")) == 6
