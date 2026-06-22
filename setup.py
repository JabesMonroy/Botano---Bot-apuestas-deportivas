from __future__ import annotations

import importlib
import subprocess
import sys

PASOS = [
    ("Creando base de datos", "scripts.init_db"),
    ("Cargando las 48 selecciones", "scripts.cargar_mapeo"),
    ("Descargando datos del Mundial (cuotas, resultados, tabla)", "scripts.actualizar"),
    ("Elo de selecciones", "scripts.ingestar_elo"),
    ("Valor de plantilla (Transfermarkt)", "scripts.ingestar_valor"),
    ("Córners / tarjetas / xG (Footystats)", "scripts.ingestar_stats"),
    ("Histórico de selección 2022-24 (puede tardar ~1 min)", "scripts.ingestar_historico"),
    ("Estimando las fuerzas del modelo", "scripts.estimar_fuerzas"),
    ("Calibrando corrección de empate y shrinkage", "scripts.calibrar_sesgo"),
    ("Calibrando peso del valor de plantilla", "scripts.calibrar_valor"),
    ("Calibrando peso del xG", "scripts.calibrar_xg"),
]


def _asegurar_dependencias() -> None:
    try:
        import dotenv  # noqa: F401
        import httpx  # noqa: F401
        import scipy  # noqa: F401
    except ImportError:
        print("Instalando dependencias (primera vez, puede tardar un poco)...\n")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"], check=False)
        print()


def main() -> int:
    print("Instalación inicial de Botano. Esto descarga y prepara todos los datos.\n")
    _asegurar_dependencias()
    for i, (desc, modulo) in enumerate(PASOS, 1):
        print(f"[{i}/{len(PASOS)}] {desc}...")
        try:
            importlib.import_module(modulo).main()
        except Exception as exc:
            print(f"   ERROR en este paso: {exc}")
            if modulo == "scripts.init_db":
                print("   No se puede continuar sin la base de datos.")
                return 1
            print("   Continúo con los demás pasos; puedes reintentar este luego.")
        print()
    print("Listo. Ahora ejecuta:  python bot.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
