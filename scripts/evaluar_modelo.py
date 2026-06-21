from __future__ import annotations

from src.config import load_config
from src.db.database import connect
from src.modelo.evaluacion import estrato, media, prob_fuerzas, resultado, rps
from src.modelo.fuerzas import _filas_historico, _parse, ajustar, cargar as cargar_fuerzas, construir_dataset, mapa_elo
from src.modelo.valor import sin_vig

HOSTS = {"USA", "MEX", "CAN"}


def _reporte_estratos(registros, ingenuo) -> None:
    for et in ("facil", "medio", "renido"):
        sub = [(p, o) for p, o in registros if estrato(p) == et]
        if not sub:
            continue
        rm = media([rps(p, o) for p, o in sub])
        ri = media([rps(ingenuo, o) for _, o in sub])
        print(f"    {et:7} n={len(sub):4}  RPS modelo {rm:.4f}  | ingenuo {ri:.4f}  | {'mejor' if rm < ri else 'PEOR'}")


def main() -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)

    filas = [r for r in _filas_historico(conn) if _parse(r["fecha"])]
    filas.sort(key=lambda r: _parse(r["fecha"]))
    corte = int(len(filas) * 0.7)
    train, test = filas[:corte], filas[corte:]
    elo_por_api = mapa_elo(conn, cfg.cache_dir)
    ds = construir_dataset(train, elo_por_api, min_partidos=5)
    params = ajustar(ds[0], ds[1], ds[2], ds[3], ds[4], ds[5], ds[6])

    n = len(train)
    hw = sum(1 for r in train if r["gh"] > r["ga"])
    dr = sum(1 for r in train if r["gh"] == r["ga"])
    ingenuo = (hw / n, dr / n, (n - hw - dr) / n)

    registros = []
    for r in test:
        p = prob_fuerzas(r["h"], r["a"], params, params["gamma"])
        if p is not None:
            registros.append((p, resultado(r["gh"], r["ga"])))

    print("=== 1) Validacion temporal out-of-sample (historico) ===")
    print(f"train {len(train)} | test {len(test)} | evaluables {len(registros)} | corte {_parse(test[0]['fecha']).date()}")
    rps_m = media([rps(p, o) for p, o in registros])
    rps_i = media([rps(ingenuo, o) for _, o in registros])
    print(f"RPS modelo {rps_m:.4f} | RPS ingenuo(base rates train) {rps_i:.4f} | mejora {(rps_i - rps_m) / rps_i * 100:.1f}%")
    print("  por dificultad (favorito segun modelo):")
    _reporte_estratos(registros, ingenuo)

    fz = cargar_fuerzas(cfg.data_dir)
    rows = conn.execute(
        "SELECT el.api_football_id h, ev.api_football_id a, el.fifa_code fh, r.goles_local gh, r.goles_visita ga "
        "FROM resultados r JOIN partidos p ON r.partido_id=p.id "
        "JOIN equipos el ON p.equipo_local_id=el.id JOIN equipos ev ON p.equipo_visita_id=ev.id"
    ).fetchall()
    reg2 = []
    for r in rows:
        if r["h"] is None or r["a"] is None:
            continue
        ventaja = fz["gamma"] if r["fh"] in HOSTS else 0.0
        p = prob_fuerzas(r["h"], r["a"], fz, ventaja)
        if p is not None:
            reg2.append((p, resultado(r["gh"], r["ga"])))

    print("\n=== 2) Mundial 2026 jugados (out-of-sample natural) ===")
    if reg2:
        uni = (1 / 3, 1 / 3, 1 / 3)
        print(f"n={len(reg2)} | RPS modelo {media([rps(p, o) for p, o in reg2]):.4f} | RPS uniforme {media([rps(uni, o) for _, o in reg2]):.4f}")
        print("  por dificultad (favorito segun modelo):")
        _reporte_estratos(reg2, uni)

    rows = conn.execute(
        "SELECT p.id, el.api_football_id h, ev.api_football_id a, el.fifa_code fl, ev.fifa_code fv "
        "FROM partidos p JOIN equipos el ON p.equipo_local_id=el.id JOIN equipos ev ON p.equipo_visita_id=ev.id"
    ).fetchall()
    difs = []
    for r in rows:
        if r["h"] is None or r["a"] is None:
            continue
        cuotas = {
            c["seleccion"]: c["cuota"]
            for c in conn.execute(
                "SELECT seleccion, cuota FROM cuotas WHERE partido_id=? AND casa='pinnacle' AND mercado='1X2'",
                (r["id"],),
            )
        }
        if not {r["fl"], "X", r["fv"]} <= cuotas.keys():
            continue
        p = prob_fuerzas(r["h"], r["a"], fz, 0.0)
        if p is None:
            continue
        nv = sin_vig({"1": cuotas[r["fl"]], "X": cuotas["X"], "2": cuotas[r["fv"]]})
        difs.append((p[0] - nv["1"], p[1] - nv["X"], p[2] - nv["2"]))

    conn.close()
    print("\n=== 3) Divergencia modelo - Pinnacle (proximos con cuota) ===")
    if difs:
        print(
            f"n={len(difs)} | sesgo medio  local {media([d[0] for d in difs]):+.3f}  "
            f"empate {media([d[1] for d in difs]):+.3f}  visita {media([d[2] for d in difs]):+.3f}"
        )
        print(f"  MAE por resultado: {media([sum(abs(x) for x in d) / 3 for d in difs]):.3f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
