from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

COLUMNAS = [
    "fifa_code",
    "nombre",
    "confederacion",
    "api_football_id",
    "sofascore_id",
    "fbref_id",
    "eloratings_name",
    "odds_api_name",
    "football_data_id",
    "football_data_name",
]

FUENTES = {
    "fifa_code",
    "nombre",
    "api_football_id",
    "sofascore_id",
    "fbref_id",
    "eloratings_name",
    "odds_api_name",
    "football_data_id",
    "football_data_name",
}


@dataclass
class EquipoMapeo:
    fifa_code: str
    nombre: str
    confederacion: str = ""
    api_football_id: int | None = None
    sofascore_id: int | None = None
    fbref_id: str = ""
    eloratings_name: str = ""
    odds_api_name: str = ""
    football_data_id: int | None = None
    football_data_name: str = ""


def _to_int(valor: str) -> int | None:
    valor = (valor or "").strip()
    return int(valor) if valor else None


def cargar_csv(path: Path) -> list[EquipoMapeo]:
    with path.open(encoding="utf-8", newline="") as fh:
        filas = list(csv.DictReader(fh))
    return [
        EquipoMapeo(
            fifa_code=fila["fifa_code"].strip().upper(),
            nombre=fila["nombre"].strip(),
            confederacion=fila.get("confederacion", "").strip(),
            api_football_id=_to_int(fila.get("api_football_id", "")),
            sofascore_id=_to_int(fila.get("sofascore_id", "")),
            fbref_id=fila.get("fbref_id", "").strip(),
            eloratings_name=fila.get("eloratings_name", "").strip(),
            odds_api_name=fila.get("odds_api_name", "").strip(),
            football_data_id=_to_int(fila.get("football_data_id", "")),
            football_data_name=fila.get("football_data_name", "").strip(),
        )
        for fila in filas
    ]


def guardar_csv(path: Path, equipos: list[EquipoMapeo]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    equipos = sorted(equipos, key=lambda e: (e.confederacion, e.fifa_code))
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNAS)
        writer.writeheader()
        for e in equipos:
            writer.writerow(
                {
                    "fifa_code": e.fifa_code,
                    "nombre": e.nombre,
                    "confederacion": e.confederacion,
                    "api_football_id": e.api_football_id or "",
                    "sofascore_id": e.sofascore_id or "",
                    "fbref_id": e.fbref_id,
                    "eloratings_name": e.eloratings_name,
                    "odds_api_name": e.odds_api_name,
                    "football_data_id": e.football_data_id or "",
                    "football_data_name": e.football_data_name,
                }
            )


def upsert_db(conn: sqlite3.Connection, equipos: list[EquipoMapeo]) -> int:
    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sql = """
        INSERT INTO equipos (
            fifa_code, nombre, confederacion, api_football_id,
            sofascore_id, fbref_id, eloratings_name, odds_api_name,
            football_data_id, football_data_name, actualizado
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(fifa_code) DO UPDATE SET
            nombre = excluded.nombre,
            confederacion = excluded.confederacion,
            api_football_id = COALESCE(excluded.api_football_id, equipos.api_football_id),
            sofascore_id = COALESCE(excluded.sofascore_id, equipos.sofascore_id),
            fbref_id = CASE WHEN excluded.fbref_id != '' THEN excluded.fbref_id ELSE equipos.fbref_id END,
            eloratings_name = CASE WHEN excluded.eloratings_name != '' THEN excluded.eloratings_name ELSE equipos.eloratings_name END,
            odds_api_name = CASE WHEN excluded.odds_api_name != '' THEN excluded.odds_api_name ELSE equipos.odds_api_name END,
            football_data_id = COALESCE(excluded.football_data_id, equipos.football_data_id),
            football_data_name = CASE WHEN excluded.football_data_name != '' THEN excluded.football_data_name ELSE equipos.football_data_name END,
            actualizado = excluded.actualizado
    """
    with conn:
        conn.executemany(
            sql,
            [
                (
                    e.fifa_code,
                    e.nombre,
                    e.confederacion,
                    e.api_football_id,
                    e.sofascore_id,
                    e.fbref_id,
                    e.eloratings_name,
                    e.odds_api_name,
                    e.football_data_id,
                    e.football_data_name,
                    ahora,
                )
                for e in equipos
            ],
        )
    return len(equipos)


def resolver(conn: sqlite3.Connection, fuente: str, valor: object) -> sqlite3.Row | None:
    if fuente not in FUENTES:
        raise ValueError(f"Fuente no valida: {fuente}")
    cur = conn.execute(f"SELECT * FROM equipos WHERE {fuente} = ?", (valor,))
    return cur.fetchone()
