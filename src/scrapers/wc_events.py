from __future__ import annotations

import csv
import io
import json
import re
import time
from pathlib import Path

import httpx

from src.modelo.xg import desde_whoscored, prob_gol

ARBOL = "https://api.github.com/repos/nlbair/wc2026-events/git/trees/main?recursive=1"
RAW = "https://raw.githubusercontent.com/nlbair/wc2026-events/main/"
PERIODOS_90 = {"FirstHalf", "SecondHalf"}
_QUAL = re.compile(r"'displayName': '([A-Za-z]+)'")


def _stats_vacias() -> dict:
    return {"goles": 0, "xg": 0.0, "tiros": 0, "tiros_arco": 0, "corners": 0,
            "amarillas": 0, "rojas": 0, "saques_meta": 0}


class WcEvents:
    def __init__(self, cache_dir: Path, ttl_indice: float = 21600) -> None:
        self._cache = cache_dir / "wc_events"
        self._cache.mkdir(parents=True, exist_ok=True)
        self._ttl = ttl_indice

    def rutas(self) -> list[str]:
        destino = self._cache / "tree.json"
        if destino.exists() and time.time() - destino.stat().st_mtime < self._ttl:
            arbol = json.loads(destino.read_text(encoding="utf-8"))
        else:
            r = httpx.get(ARBOL, timeout=60, follow_redirects=True)
            r.raise_for_status()
            arbol = r.json()
            destino.write_text(json.dumps(arbol), encoding="utf-8")
        return sorted(
            e["path"] for e in arbol["tree"]
            if e["path"].startswith("data/raw/") and e["path"].endswith("_events.csv")
        )

    def resumen(self, ruta: str, coefs_xg: list[float]) -> dict:
        nombre = ruta.rsplit("/", 1)[-1].replace(".csv", ".json")
        destino = self._cache / nombre
        if destino.exists():
            return json.loads(destino.read_text(encoding="utf-8"))
        r = httpx.get(RAW + ruta, timeout=120, follow_redirects=True)
        r.raise_for_status()
        res = _procesar(r.text, coefs_xg)
        destino.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
        time.sleep(0.4)
        return res


def _f(txt: str) -> float | None:
    try:
        return float(txt)
    except (TypeError, ValueError):
        return None


def _procesar(texto_csv: str, coefs_xg: list[float]) -> dict:
    filas = csv.DictReader(io.StringIO(texto_csv))
    meta: dict = {}
    equipos: dict[str, dict] = {}
    otro: dict[str, str] = {}

    for fila in filas:
        if not meta:
            meta = {
                "fecha": fila["match_date"],
                "local": fila["home_team"],
                "visita": fila["away_team"],
                "marcador": [int(float(fila["home_score"])), int(float(fila["away_score"]))],
            }
            equipos = {meta["local"]: _stats_vacias(), meta["visita"]: _stats_vacias()}
            otro = {meta["local"]: meta["visita"], meta["visita"]: meta["local"]}

        equipo = fila.get("team")
        if equipo not in equipos or fila.get("period_name") not in PERIODOS_90:
            continue
        ev = fila.get("event", "")
        quals = set(_QUAL.findall(fila.get("qualifiers") or ""))
        st = equipos[equipo]

        if fila.get("cardType") in ("Yellow", "SecondYellow", "Red"):
            if fila["cardType"] == "Red":
                st["rojas"] += 1
            elif fila["cardType"] == "SecondYellow":
                st["amarillas"] += 1
                st["rojas"] += 1
            else:
                st["amarillas"] += 1

        if ev == "CornerAwarded" and fila.get("outcome") == "Successful":
            st["corners"] += 1
        elif ev == "Pass" and "GoalKick" in quals:
            st["saques_meta"] += 1

        if fila.get("isShot") == "True" and "OwnGoal" not in quals:
            st["tiros"] += 1
            if ev == "Goal" or (ev == "SavedShot" and "Blocked" not in quals):
                st["tiros_arco"] += 1
            x, y = _f(fila.get("x")), _f(fila.get("y"))
            if x is not None and y is not None:
                d, a = desde_whoscored(x, y)
                st["xg"] += prob_gol(coefs_xg, d, a, "Head" in quals, "Penalty" in quals)

        if fila.get("isGoal") == "True":
            destino_gol = otro[equipo] if "OwnGoal" in quals else equipo
            equipos[destino_gol]["goles"] += 1

    for st in equipos.values():
        st["xg"] = round(st["xg"], 3)
    return {**meta, "equipos": equipos}
