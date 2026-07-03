from __future__ import annotations

import unicodedata
from datetime import datetime, timezone

from src.config import load_config
from src.db.database import connect, init_db
from src.modelo.xg import cargar as cargar_xg
from src.scrapers.wc_events import WcEvents

OVERRIDES = {
    "usa": "USA",
    "united states": "USA",
    "turkiye": "TUR",
    "south korea": "KOR",
    "korea republic": "KOR",
    "republic of korea": "KOR",
    "ivory coast": "CIV",
    "dr congo": "COD",
    "congo dr": "COD",
    "cape verde": "CPV",
    "cape verde islands": "CPV",
    "iran": "IRN",
    "ir iran": "IRN",
    "saudi arabia": "KSA",
    "czechia": "CZE",
    "czech republic": "CZE",
}


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().strip().lower()


def _indice_equipos(conn) -> dict[str, int]:
    idx: dict[str, int] = {}
    codigo: dict[str, int] = {}
    for r in conn.execute(
        "SELECT id, fifa_code, nombre, odds_api_name, football_data_name, eloratings_name FROM equipos"
    ):
        codigo[r["fifa_code"]] = r["id"]
        for campo in ("nombre", "odds_api_name", "football_data_name", "eloratings_name"):
            if r[campo]:
                idx.setdefault(_norm(r[campo]), r["id"])
    for alias, fifa in OVERRIDES.items():
        if fifa in codigo:
            idx[alias] = codigo[fifa]
    return idx


def _buscar_partido(conn, id_a: int, id_b: int, fecha: str):
    return conn.execute(
        "SELECT id, equipo_local_id FROM partidos "
        "WHERE ((equipo_local_id=? AND equipo_visita_id=?) OR (equipo_local_id=? AND equipo_visita_id=?)) "
        "AND abs(julianday(substr(fecha,1,10)) - julianday(?)) <= 1.5",
        (id_a, id_b, id_b, id_a, fecha),
    ).fetchone()


def main() -> int:
    cfg = load_config()
    xg = cargar_xg(cfg.data_dir)
    if xg is None:
        print("falta el modelo de xG por tiro (corre scripts.calibrar_xg_disparo)")
        return 1
    init_db(cfg.db_path)
    conn = connect(cfg.db_path)
    idx = _indice_equipos(conn)

    wc = WcEvents(cfg.cache_dir)
    rutas = wc.rutas()
    ahora = datetime.now(timezone.utc).isoformat()
    ok, sin_equipo, sin_partido, discrepancias = 0, [], [], []

    for ruta in rutas:
        res = wc.resumen(ruta, xg["coefs"])
        ids = {n: idx.get(_norm(n)) for n in (res["local"], res["visita"])}
        faltan = [n for n, i in ids.items() if i is None]
        if faltan:
            sin_equipo.append((ruta.rsplit("/", 1)[-1], faltan))
            continue
        p = _buscar_partido(conn, ids[res["local"]], ids[res["visita"]], res["fecha"])
        if p is None:
            sin_partido.append(ruta.rsplit("/", 1)[-1])
            continue

        with conn:
            for nombre, eq_id in ids.items():
                st = res["equipos"][nombre]
                conn.execute(
                    "INSERT INTO estadisticas_mundial (partido_id, equipo_id, es_local, goles, xg, tiros, tiros_arco, "
                    "corners, amarillas, rojas, saques_meta, fuente, actualizado) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                    "ON CONFLICT(partido_id, equipo_id) DO UPDATE SET goles=excluded.goles, xg=excluded.xg, "
                    "tiros=excluded.tiros, tiros_arco=excluded.tiros_arco, corners=excluded.corners, "
                    "amarillas=excluded.amarillas, rojas=excluded.rojas, saques_meta=excluded.saques_meta, "
                    "actualizado=excluded.actualizado",
                    (p["id"], eq_id, 1 if eq_id == p["equipo_local_id"] else 0, st["goles"], st["xg"],
                     st["tiros"], st["tiros_arco"], st["corners"], st["amarillas"], st["rojas"],
                     st["saques_meta"], "wc2026-events (WhoScored)", ahora),
                )
        ok += 1

        marcador_db = conn.execute(
            "SELECT goles_local, goles_visita FROM resultados WHERE partido_id=?", (p["id"],)
        ).fetchone()
        if marcador_db and marcador_db["goles_local"] is not None:
            es_mismo_orden = ids[res["local"]] == p["equipo_local_id"]
            gl, gv = res["equipos"][res["local"]]["goles"], res["equipos"][res["visita"]]["goles"]
            if not es_mismo_orden:
                gl, gv = gv, gl
            if (gl, gv) != (marcador_db["goles_local"], marcador_db["goles_visita"]):
                discrepancias.append(
                    f"{res['local']} vs {res['visita']}: eventos 90' {gl}-{gv} | DB {marcador_db['goles_local']}-{marcador_db['goles_visita']}"
                )

    fila = conn.execute(
        "SELECT COUNT(DISTINCT partido_id) np, AVG(xg) xg, AVG(corners) c, AVG(amarillas+rojas) t, "
        "AVG(saques_meta) s, AVG(tiros) ti FROM estadisticas_mundial"
    ).fetchone()
    conn.close()

    print(f"archivos {len(rutas)} | ingestados {ok} | sin mapear equipo {len(sin_equipo)} | sin partido en DB {len(sin_partido)}")
    for archivo, faltan in sin_equipo:
        print(f"  [equipo sin mapear] {archivo}: {', '.join(faltan)}")
    for archivo in sin_partido:
        print(f"  [partido no encontrado] {archivo}")
    if fila["np"]:
        print(
            f"promedios por equipo/partido ({fila['np']} partidos): xG {fila['xg']:.2f} | corners {fila['c']:.2f} | "
            f"tarjetas {fila['t']:.2f} | saques de meta {fila['s']:.2f} | tiros {fila['ti']:.1f}"
        )
    if discrepancias:
        print(f"discrepancias de marcador (90' vs DB, esperables si hubo prorroga): {len(discrepancias)}")
        for d in discrepancias[:6]:
            print(f"  {d}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
