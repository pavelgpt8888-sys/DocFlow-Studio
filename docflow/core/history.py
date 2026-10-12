"""История операций в SQLite.

Хранятся только служебные сведения: время, шаблон, имя файла данных,
количество документов, статус и пути результатов. Значения полей записей
в историю не попадают.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL,
    template TEXT NOT NULL,
    data_file TEXT NOT NULL,
    requested INTEGER NOT NULL,
    succeeded INTEGER NOT NULL,
    failed INTEGER NOT NULL,
    output_dir TEXT NOT NULL,
    outputs TEXT NOT NULL,
    status TEXT NOT NULL
);
"""


@dataclass
class HistoryEntry:
    id: int
    created_at: datetime
    source: str
    template: str
    data_file: str
    requested: int
    succeeded: int
    failed: int
    output_dir: Path
    outputs: list[Path]
    status: str

    @property
    def status_label(self) -> str:
        return {"ok": "Успешно", "partial": "Частично", "error": "Ошибка",
                "cancelled": "Отменено"}.get(self.status, self.status)


class History:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=5)

    def add(self, *, source: str, template: str, data_file: str, requested: int,
            outputs: list[Path], failed: int, output_dir: Path, cancelled: bool = False) -> int:
        succeeded = len(outputs)
        if cancelled:
            status = "cancelled"
        elif failed and succeeded:
            status = "partial"
        elif failed or not succeeded:
            status = "error"
        else:
            status = "ok"
        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO operations (created_at, source, template, data_file, requested,"
                " succeeded, failed, output_dir, outputs, status) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), source, template, data_file,
                 requested, succeeded, failed, str(output_dir),
                 json.dumps([str(p) for p in outputs], ensure_ascii=False), status),
            )
            return int(cur.lastrowid)

    def list(self, limit: int = 200) -> list[HistoryEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, source, template, data_file, requested, succeeded,"
                " failed, output_dir, outputs, status FROM operations ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            HistoryEntry(r[0], datetime.fromisoformat(r[1]), r[2], r[3], r[4], r[5], r[6], r[7],
                         Path(r[8]), [Path(p) for p in json.loads(r[9])], r[10])
            for r in rows
        ]

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM operations")
