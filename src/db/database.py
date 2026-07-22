from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).parent / "schema.sql"


def _migrar(conn: sqlite3.Connection) -> None:
    with conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS combinadas ("
            "id INTEGER PRIMARY KEY, cuota_total REAL NOT NULL, stake REAL NOT NULL, "
            "fecha TEXT NOT NULL, resultado TEXT, ganancia REAL)"
        )
        try:
            conn.execute("ALTER TABLE apuestas ADD COLUMN combinada_id INTEGER REFERENCES combinadas(id)")
        except sqlite3.OperationalError:
            pass


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    _migrar(conn)
    return conn


def init_db(db_path: Path) -> None:
    conn = connect(db_path)
    try:
        with conn:
            conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    finally:
        conn.close()
