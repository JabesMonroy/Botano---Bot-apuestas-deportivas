from __future__ import annotations

import sqlite3
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.clients.api_football import ApiFootball
from src.config import Config, load_config
from src.db.database import connect
from src.imagenes import color_dominante

DIAS_ADELANTE = 10
DIAS_ATRAS = 4

CODIGO_POR_LIGA_API = {239: "CO1", 241: "COP"}

ESTADO = {
    "NS": "SCHEDULED", "TBD": "SCHEDULED",
    "FT": "FINISHED", "AET": "FINISHED", "PEN": "FINISHED",
    "PST": "POSTPONED", "CANC": "CANCELLED", "ABD": "CANCELLED", "AWD": "FINISHED", "WO": "FINISHED",
}
ESTADOS_JUGADO = {"FT", "AET", "PEN", "AWD", "WO"}


def _codigo_unico(conn: sqlite3.Connection, base: str, api_id: int) -> str:
    candidato = base
    sufijo = 2
    while True:
        fila = conn.execute("SELECT api_football_id FROM equipos WHERE fifa_code=?", (candidato,)).fetchone()
        if fila is None or fila["api_football_id"] == api_id:
            return candidato
        candidato = f"{base}{sufijo}"
        sufijo += 1


def actualizar(cfg: Config) -> dict:
    conn = connect(cfg.db_path)
    liga_id = {r["codigo"]: r["id"] for r in conn.execute("SELECT id, codigo FROM ligas WHERE codigo IN ('CO1','COP')")}
    if "CO1" not in liga_id:
        conn.close()
        raise RuntimeError("Liga BetPlay no registrada: corre scripts.ingestar_betplay o scripts.cargar_mapeo_clubes primero")

    af = ApiFootball(cfg.api_football_key, cfg.api_football_host, cfg.cache_dir / "api_football")
    fixtures = []
    hoy = datetime.now(timezone(timedelta(hours=-5))).date()
    for i in range(-DIAS_ATRAS, DIAS_ADELANTE):
        fecha = (hoy + timedelta(days=i)).isoformat()
        ttl = 1800 if i <= 0 else 21600
        data = af.fixtures(date=fecha, timezone="America/Bogota", ttl=ttl)
        fixtures += [
            fx for fx in data.get("response", [])
            if fx["league"]["country"] == "Colombia" and fx["league"]["id"] in CODIGO_POR_LIGA_API
            and CODIGO_POR_LIGA_API[fx["league"]["id"]] in liga_id
        ]
    af.close()

    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    equipos_nuevos = {t["id"]: t for fx in fixtures for t in (fx["teams"]["home"], fx["teams"]["away"])}
    liga_id_default = liga_id["CO1"]
    for api_id, t in equipos_nuevos.items():
        nombre, logo = t["name"], t.get("logo")
        fila = conn.execute("SELECT id, escudo_url FROM equipos WHERE api_football_id=?", (api_id,)).fetchone()
        if fila is not None:
            if fila["escudo_url"] is None and logo:
                conn.execute("UPDATE equipos SET escudo_url=? WHERE id=?", (logo, fila["id"]))
            continue
        base = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().split()[0][:3].upper() or "EQU"
        codigo = _codigo_unico(conn, base, api_id)
        conn.execute(
            "INSERT INTO equipos (fifa_code, nombre, api_football_id, liga_id, odds_api_name, escudo_url, actualizado) "
            "VALUES (?, ?, ?, ?, '', ?, ?)",
            (codigo, nombre, api_id, liga_id_default, logo, ahora),
        )
    conn.commit()

    pendientes_color = conn.execute(
        "SELECT id, escudo_url FROM equipos WHERE liga_id IN (?, ?) AND escudo_url IS NOT NULL AND color_principal IS NULL",
        (liga_id.get("CO1"), liga_id.get("COP")),
    ).fetchall()
    for eq in pendientes_color:
        color = color_dominante(eq["escudo_url"])
        if color:
            conn.execute("UPDATE equipos SET color_principal=? WHERE id=?", (color, eq["id"]))
    if pendientes_color:
        conn.commit()

    equipo_id_por_api = {
        r["api_football_id"]: r["id"] for r in conn.execute("SELECT id, api_football_id FROM equipos WHERE api_football_id IS NOT NULL")
    }
    n_partidos = n_resultados = 0
    with conn:
        for fx in fixtures:
            codigo_liga_fx = CODIGO_POR_LIGA_API[fx["league"]["id"]]
            liga_id_fx = liga_id[codigo_liga_fx]
            local_id = equipo_id_por_api.get(fx["teams"]["home"]["id"])
            visita_id = equipo_id_por_api.get(fx["teams"]["away"]["id"])
            if local_id is None or visita_id is None:
                continue
            conn.execute("INSERT OR IGNORE INTO equipos_competicion (equipo_id, liga_id) VALUES (?, ?)", (local_id, liga_id_fx))
            conn.execute("INSERT OR IGNORE INTO equipos_competicion (equipo_id, liga_id) VALUES (?, ?)", (visita_id, liga_id_fx))

            estado_corto = fx["fixture"]["status"]["short"]
            estado = ESTADO.get(estado_corto, "IN_PLAY")
            conn.execute(
                "INSERT INTO partidos (api_football_id, fecha, equipo_local_id, equipo_visita_id, fase, estado, liga_id, actualizado) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(api_football_id) DO UPDATE SET fecha=excluded.fecha, estado=excluded.estado, "
                "fase=excluded.fase, liga_id=excluded.liga_id, actualizado=excluded.actualizado",
                (fx["fixture"]["id"], fx["fixture"]["date"], local_id, visita_id, fx["league"].get("round"), estado, liga_id_fx, ahora),
            )
            n_partidos += 1
            if estado_corto in ESTADOS_JUGADO and fx["goals"]["home"] is not None:
                partido_id = conn.execute("SELECT id FROM partidos WHERE api_football_id=?", (fx["fixture"]["id"],)).fetchone()["id"]
                conn.execute(
                    "INSERT INTO resultados (partido_id, goles_local, goles_visita, finalizado) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(partido_id) DO UPDATE SET goles_local=excluded.goles_local, goles_visita=excluded.goles_visita, finalizado=excluded.finalizado",
                    (partido_id, fx["goals"]["home"], fx["goals"]["away"], fx["fixture"]["date"]),
                )
                n_resultados += 1
    conn.close()
    return {"partidos": n_partidos, "resultados": n_resultados, "equipos_nuevos": len(equipos_nuevos)}


def main() -> int:
    cfg = load_config()
    r = actualizar(cfg)
    print(f"Liga BetPlay + Copa BetPlay: {r['partidos']} partidos ({DIAS_ATRAS} días atrás a {DIAS_ADELANTE} adelante) | "
          f"{r['resultados']} resultados | {r['equipos_nuevos']} equipos nuevos vistos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
