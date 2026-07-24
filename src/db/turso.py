from __future__ import annotations

from pathlib import Path

import libsql

from src.config import Config

SCHEMA = Path(__file__).parent / "schema_apuestas_turso.sql"


class Row:
    __slots__ = ("_cols", "_vals")

    def __init__(self, cols: tuple[str, ...], vals: tuple):
        self._cols = cols
        self._vals = vals

    def __getitem__(self, clave):
        if isinstance(clave, str):
            return self._vals[self._cols.index(clave)]
        return self._vals[clave]

    def keys(self):
        return list(self._cols)

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)

    def __repr__(self):
        return f"<Row {dict(zip(self._cols, self._vals))}>"


class Cursor:
    def __init__(self, cursor_nativo):
        self._c = cursor_nativo

    def _cols(self) -> tuple[str, ...]:
        return tuple(d[0] for d in self._c.description) if self._c.description else ()

    def fetchone(self) -> Row | None:
        v = self._c.fetchone()
        return None if v is None else Row(self._cols(), v)

    def fetchall(self) -> list[Row]:
        cols = self._cols()
        return [Row(cols, v) for v in self._c.fetchall()]

    def __iter__(self):
        return iter(self.fetchall())

    def __getattr__(self, nombre):
        return getattr(self._c, nombre)


class Conexion:
    def __init__(self, conn_nativa):
        self._conn = conn_nativa

    def execute(self, sql: str, params=()) -> Cursor:
        return Cursor(self._conn.execute(sql, params))

    def executescript(self, script: str) -> None:
        self._conn.executescript(script)

    def __enter__(self) -> "Conexion":
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self._conn.__exit__(exc_type, exc, tb)

    def __getattr__(self, nombre):
        return getattr(self._conn, nombre)


def connect(cfg: Config) -> Conexion:
    conn = Conexion(libsql.connect(database=cfg.turso_database_url, auth_token=cfg.turso_auth_token))
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conn
