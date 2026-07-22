from __future__ import annotations

import unicodedata

import pandas as pd

from src.clients.football_data_uk import FootballDataUk
from src.config import load_config
from src.db.database import connect
from src.ligas import LIGAS, registrar as registrar_ligas
from src.scrapers.understat import Understat

TEMPORADAS = ["2019-20", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25", "2025-26"]

OVERRIDES = {
    "manchester united": "man united",
    "manchester city": "man city",
    "newcastle united": "newcastle",
    "wolverhampton wanderers": "wolves",
    "nottingham forest": "nott'm forest",
    "west bromwich albion": "west brom",
    "sheffield united": "sheffield united",
    "atletico madrid": "ath madrid",
    "athletic club": "ath bilbao",
    "real sociedad": "sociedad",
    "celta vigo": "celta",
    "real betis": "betis",
    "espanyol": "espanol",
    "rayo vallecano": "vallecano",
    "real valladolid": "valladolid",
    "deportivo alaves": "alaves",
    "real oviedo": "oviedo",
    "borussia m.gladbach": "m'gladbach",
    "borussia dortmund": "dortmund",
    "rasenballsport leipzig": "rb leipzig",
    "eintracht frankfurt": "ein frankfurt",
    "fortuna duesseldorf": "fortuna dusseldorf",
    "fc cologne": "fc koln",
    "hertha berlin": "hertha",
    "bayer leverkusen": "leverkusen",
    "vfb stuttgart": "stuttgart",
    "arminia bielefeld": "bielefeld",
    "greuther fuerth": "greuther furth",
    "vfl bochum": "bochum",
    "fc heidenheim": "heidenheim",
    "mainz 05": "mainz",
    "st. pauli": "st pauli",
    "hamburger sv": "hamburg",
    "ac milan": "milan",
    "parma calcio 1913": "parma",
    "spal 2013": "spal",
    "paris saint germain": "paris sg",
    "saint-etienne": "st etienne",
    "clermont foot": "clermont",
}

STATS = [
    ("HS", "tiros_local"), ("AS", "tiros_visita"),
    ("HST", "tiros_arco_local"), ("AST", "tiros_arco_visita"),
    ("HC", "corners_local"), ("AC", "corners_visita"),
    ("HF", "faltas_local"), ("AF", "faltas_visita"),
    ("HY", "amarillas_local"), ("AY", "amarillas_visita"),
    ("HR", "rojas_local"), ("AR", "rojas_visita"),
]

CUOTAS = [
    ("PSH", "ps_h"), ("PSD", "ps_d"), ("PSA", "ps_a"),
    ("PSCH", "psc_h"), ("PSCD", "psc_d"), ("PSCA", "psc_a"),
    ("P>2.5", "p_over25"), ("P<2.5", "p_under25"),
    ("PC>2.5", "pc_over25"), ("PC<2.5", "pc_under25"),
    ("AHh", "ah_linea"), ("AHCh", "ahc_linea"),
    ("PCAHH", "pcah_h"), ("PCAHA", "pcah_a"),
]


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode()
    return t.strip().lower()


def _valor(fila, col):
    if col not in fila or pd.isna(fila[col]):
        return None
    return float(fila[col])


def _entero(fila, col):
    v = _valor(fila, col)
    return int(v) if v is not None else None


def _ingestar_extra(conn, fdu: FootballDataUk, liga, liga_id: dict) -> int:
    df = fdu.extra(liga.fd_uk)
    filas = []
    for _, fila in df.iterrows():
        fecha = pd.to_datetime(fila["Date"], dayfirst=True).date().isoformat()
        temporada = str(int(fila["Season"])) if not pd.isna(fila.get("Season")) else fecha[:4]
        local, visita = str(fila["Home"]), str(fila["Away"])
        registro = [
            liga_id[liga.codigo], temporada, fecha, local, visita,
            _entero(fila, "HG"), _entero(fila, "AG"),
        ]
        registro += [None for _ in STATS]
        cuotas_extra = {"ps_h": _valor(fila, "PH"), "ps_d": _valor(fila, "PD"), "ps_a": _valor(fila, "PA")}
        registro += [cuotas_extra.get(c) for _, c in CUOTAS]
        registro += [None, None]
        filas.append(registro)

    columnas = (
        "liga_id, temporada, fecha, local, visita, goles_local, goles_visita, "
        + ", ".join(c for _, c in STATS) + ", "
        + ", ".join(c for _, c in CUOTAS) + ", xg_local, xg_visita"
    )
    marcas = ",".join("?" * (7 + len(STATS) + len(CUOTAS) + 2))
    with conn:
        conn.execute("DELETE FROM partidos_club WHERE liga_id=?", (liga_id[liga.codigo],))
        conn.executemany(f"INSERT INTO partidos_club ({columnas}) VALUES ({marcas})", filas)
    print(f"  {liga.codigo}: {len(filas)} partidos (solo resultados + cuota apertura Pinnacle, sin xG ni estadísticas de partido)")
    return len(filas)


def main() -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    schema = (cfg.data_dir.parent / "src" / "db" / "schema_clubes.sql").read_text(encoding="utf-8")
    conn.executescript(schema)

    fdu = FootballDataUk(cfg.cache_dir / "football_data_uk")
    us = Understat(cfg.cache_dir / "understat")

    liga_id = registrar_ligas(conn)

    total, con_xg, sin_xg_detalle = 0, 0, []
    for liga in LIGAS:
        if not liga.fd_uk:
            continue
        if liga.fd_uk_extra:
            total += _ingestar_extra(conn, fdu, liga, liga_id)
            continue
        codigo, us_liga = liga.codigo, liga.understat
        for temporada in TEMPORADAS:
            df = fdu.temporada(codigo, temporada)
            anio = int(temporada.split("-")[0])
            try:
                xg = {
                    (_norm(p["local"]), _norm(p["visita"])): p
                    for p in us.partidos(us_liga, anio)
                }
                xg_alias = {
                    (OVERRIDES.get(l, l), OVERRIDES.get(v, v)): p
                    for (l, v), p in xg.items()
                }
            except Exception as exc:
                print(f"  {codigo} {temporada}: sin Understat ({exc})")
                xg_alias = {}

            filas, emparejados = [], 0
            for _, fila in df.iterrows():
                fecha = pd.to_datetime(fila["Date"], dayfirst=True).date().isoformat()
                local, visita = str(fila["HomeTeam"]), str(fila["AwayTeam"])
                clave = (_norm(local), _norm(visita))
                p_xg = xg_alias.get(clave)
                if p_xg:
                    emparejados += 1
                registro = [
                    liga_id[codigo], temporada, fecha, local, visita,
                    _entero(fila, "FTHG"), _entero(fila, "FTAG"),
                ]
                registro += [_entero(fila, col) for col, _ in STATS]
                registro += [_valor(fila, col) for col, _ in CUOTAS]
                registro += [p_xg["xg_local"] if p_xg else None, p_xg["xg_visita"] if p_xg else None]
                filas.append(registro)

            columnas = (
                "liga_id, temporada, fecha, local, visita, goles_local, goles_visita, "
                + ", ".join(c for _, c in STATS) + ", "
                + ", ".join(c for _, c in CUOTAS) + ", xg_local, xg_visita"
            )
            marcas = ",".join("?" * (7 + len(STATS) + len(CUOTAS) + 2))
            with conn:
                conn.execute(
                    "DELETE FROM partidos_club WHERE liga_id=? AND temporada=?",
                    (liga_id[codigo], temporada),
                )
                conn.executemany(
                    f"INSERT INTO partidos_club ({columnas}) VALUES ({marcas})", filas
                )
            total += len(filas)
            con_xg += emparejados
            if xg_alias and emparejados < len(filas):
                faltan = [
                    f"{l} vs {v}"
                    for (l, v) in ((_norm(str(f['HomeTeam'])), _norm(str(f['AwayTeam']))) for _, f in df.iterrows())
                    if (l, v) not in xg_alias
                ]
                sin_xg_detalle.append(f"{codigo} {temporada}: {len(filas) - emparejados} sin xG (ej. {faltan[:2]})")
            print(f"  {codigo} {temporada}: {len(filas)} partidos, {emparejados} con xG")

    conn.close()
    print(f"\ntotal {total} partidos | {con_xg} con xG de Understat ({con_xg / total * 100:.1f}%)")
    for d in sin_xg_detalle:
        print("  aviso:", d)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
