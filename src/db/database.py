from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).parent / "schema.sql"


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        with conn:
            conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    finally:
        conn.close()
