from __future__ import annotations

from src.config import load_config
from src.db.database import connect
from src.modelo.calibracion import calibrar_beta, datos_calibracion
from src.modelo.parametros import guardar, tasa_base_torneo


def main() -> int:
    cfg = load_config()
    conn = connect(cfg.db_path)
    base = tasa_base_torneo(conn)
    datos = datos_calibracion(conn)
    conn.close()
    if not datos:
        print("sin partidos con cuotas para calibrar")
        return 1

    rho = -0.08
    beta, ce0, ce1 = calibrar_beta(datos, base, rho)
    guardar(
        cfg.data_dir,
        beta,
        rho,
        80.0,
        extra={"tasa_base_calibracion": round(base, 3), "n_partidos": len(datos), "cross_entropy": round(ce1, 4)},
    )

    print(f"partidos de calibracion: {len(datos)} | tasa base {base:.2f} gol/equipo")
    print(f"beta 0.200 (inicial) -> cross-entropy {ce0:.4f}")
    print(f"beta {beta:.3f} (optimo) -> cross-entropy {ce1:.4f}")
    print(f"mejora: {(ce0 - ce1) / ce0 * 100:.1f}% | guardado en data/modelos/parametros.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
