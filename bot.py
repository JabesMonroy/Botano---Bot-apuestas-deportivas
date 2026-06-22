from __future__ import annotations

from src.config import load_config
from src.db.database import connect

GLOSARIO = """
QUÉ SIGNIFICA CADA TÉRMINO
============================================================

Elo
  Fuerza de una selección según sus resultados. Sube al ganar
  (más si el rival es fuerte) y baja al perder.
  Referencia: 2000+ = elite, ~1800 = buena, ~1500 = floja.

xG (goles esperados)
  Calidad de las ocasiones que GENERA un equipo por partido:
  cuántos goles "merecería" por sus oportunidades (no los que mete).
xGA
  Igual, pero de las ocasiones que CONCEDE (su defensa). Menos = mejor.
  Se muestra como  xG/xGA  (ej. 1.74/0.70 = genera 1.74, concede 0.70).

Valor de plantilla
  Valor de mercado de los jugadores (Transfermarkt). Aproxima la
  calidad individual del plantel.

EV (valor esperado)
  Cuánto ganas o pierdes de media por cada unidad apostada, según el bot.
    EV +0.05    -> a la larga ganarías ~5% (hay valor, candidato a apostar).
    EV negativo -> la cuota paga menos de lo justo (no apostar).
    n/f         -> el modelo no es fiable ahí (no apostar por esa diferencia).

Modelo / Mercado / Apostar (columnas del pronóstico)
  Modelo  = probabilidad que estima el bot.
  Mercado = probabilidad de la cuota de Pinnacle, sin el margen de la casa.
  Apostar = mezcla de las dos; es la que se usa para el EV.

Over (O) = "más de"
  O9.5 córners  = MÁS de 9.5, o sea 10 o más córners.
  O2.5 goles    = 3 o más goles.
  O3.5 tarjetas = 4 o más tarjetas.
  El % es la probabilidad de que ocurra (ej. O9.5: 45% = 45% de que haya 10+).

Ambos anotan (BTTS)
  Probabilidad de que los DOS equipos marquen al menos un gol.

Confianza
  Alto/medio/bajo según cuánto coincide el modelo con el mercado
  y la calidad de los datos.

CLV (en el historial)
  ¿Tu cuota fue mejor que la de cierre del mercado? Si tu CLV es
  positivo con el tiempo, es la mejor señal de que vas bien.
============================================================"""

MENU = """
============================================================
   BOTANO — Análisis de apuestas · Mundial 2026
============================================================
  1) Actualizar datos del Mundial (cuotas, resultados, tabla)
  2) Analizar un partido (reporte completo)
  3) Analizar un partido descontando bajas
  4) Evaluar una combinada (bet builder)
  5) Ver bajas / ausencias de un equipo
  6) Simular el torneo (clasificación y campeón)
  7) Registrar una apuesta de Betano
  8) Ver historial y CLV
  9) Ver códigos de equipos
 10) Ayuda — qué significa cada término (Elo, xG, EV, Over...)
  0) Salir
------------------------------------------------------------"""


def _pedir(texto: str) -> str:
    return input(texto).strip()


def ver_equipos(cfg) -> None:
    conn = connect(cfg.db_path)
    filas = conn.execute("SELECT fifa_code, nombre FROM equipos ORDER BY confederacion, nombre").fetchall()
    conn.close()
    print("\nCódigos de equipos (usa estos códigos de 3 letras):\n")
    for i, r in enumerate(filas):
        fin = "\n" if i % 3 == 2 else ""
        print(f"  {r['fifa_code']:4} {r['nombre']:20}", end=fin)
    print("\n")


def _accion(opcion: str, cfg) -> None:
    if opcion == "1":
        from scripts.actualizar import main as m
        m()
    elif opcion == "2":
        l, v = _pedir("Local (código): ").upper(), _pedir("Visitante (código): ").upper()
        from scripts.generar_reporte import main as m
        m(l, v)
    elif opcion == "3":
        l, v = _pedir("Local (código): ").upper(), _pedir("Visitante (código): ").upper()
        fl = _pedir(f"Bajas de {l} (nombres separados por coma, enter si ninguna): ")
        fv = _pedir(f"Bajas de {v} (nombres separados por coma, enter si ninguna): ")
        from scripts.impacto_bajas import main as m
        m(l, v, [x for x in fl.split(",") if x.strip()], [x for x in fv.split(",") if x.strip()])
    elif opcion == "4":
        print("Formato: EQUIPO-EQUIPO:mercado  (ej. ARG-AUT:1 ARG-AUT:under2.5)")
        print("Mercados: 1 X 2 1X 12 X2 over2.5 under2.5 btts nobtts ...")
        toks = _pedir("Selecciones (y opcional @cuota): ").split()
        from scripts.bet_builder import main as m
        m(toks)
    elif opcion == "5":
        from scripts.bajas import main as m
        m(_pedir("Equipo (código): ").upper())
    elif opcion == "6":
        n = _pedir("Iteraciones [10000]: ") or "10000"
        from scripts.simular_torneo import main as m
        m(int(n))
    elif opcion == "7":
        l, v = _pedir("Local (código): ").upper(), _pedir("Visitante (código): ").upper()
        s = _pedir("Tu apuesta (1=local / X=empate / 2=visita): ").upper()
        c = _pedir("Cuota de Betano: ")
        st = _pedir("Stake (enter para sugerencia Kelly): ")
        from scripts.registrar_apuesta import main as m
        m([l, v, s, c] + ([st] if st else []))
    elif opcion == "8":
        from scripts.clv import main as m
        m()
    elif opcion == "9":
        ver_equipos(cfg)
    elif opcion == "10":
        print(GLOSARIO)
    else:
        print("Opción no válida.")


def main() -> int:
    cfg = load_config()
    print("\nBienvenido. Escribe el número de la opción y pulsa Enter.")
    while True:
        print(MENU)
        opcion = _pedir("Opción> ")
        if opcion == "0":
            print("Hasta luego.")
            return 0
        print()
        try:
            _accion(opcion, cfg)
        except KeyboardInterrupt:
            print("\n(cancelado)")
        except Exception as exc:
            print(f"Error: {exc}")
        input("\n[Enter para volver al menú]")


if __name__ == "__main__":
    raise SystemExit(main())
