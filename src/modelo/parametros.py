from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.modelo.dixon_coles import ParametrosModelo

HOSTS = {"USA", "MEX", "CAN"}
ARCHIVO = "parametros.json"


def tasa_base_torneo(conn: sqlite3.Connection) -> float:
    filas = conn.execute("SELECT goles_local, goles_visita FROM resultados").fetchall()
    if not filas:
        return 1.35
    goles = sum(r["goles_local"] + r["goles_visita"] for r in filas)
    return goles / (2 * len(filas))


def _ruta(data_dir: Path) -> Path:
    return data_dir / "modelos" / ARCHIVO


def cargar(data_dir: Path, conn: sqlite3.Connection, local_es_host: bool = False) -> ParametrosModelo:
    ruta = _ruta(data_dir)
    cfg = json.loads(ruta.read_text(encoding="utf-8")) if ruta.exists() else {}
    return ParametrosModelo(
        tasa_base=tasa_base_torneo(conn),
        beta_elo=cfg.get("beta_elo", 0.20),
        rho=cfg.get("rho", -0.08),
        ventaja_local_elo=cfg.get("ventaja_local_elo", 80.0) if local_es_host else 0.0,
    )


def guardar(data_dir: Path, beta_elo: float, rho: float, ventaja_local_elo: float, extra: dict | None = None) -> None:
    ruta = _ruta(data_dir)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    datos = {"beta_elo": beta_elo, "rho": rho, "ventaja_local_elo": ventaja_local_elo}
    if extra:
        datos.update(extra)
    ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False), encoding="utf-8")
