from __future__ import annotations

import unicodedata

from src.clients.football_data import FootballData
from src.scrapers.transfermarkt import Transfermarkt

K = 0.6


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t or "").encode("ascii", "ignore").decode().strip().lower()


def _clasif(pos: str) -> str:
    if any(d in pos for d in ("Goalkeeper", "Back", "Defensive Midfield")):
        return "def"
    if any(o in pos for o in ("Winger", "Forward", "Striker", "Attacking Midfield")):
        return "of"
    return "mix"


def detectar_ausencias(cfg, transfermarkt_id, football_data_id) -> list[tuple[str, float]]:
    if not transfermarkt_id or not football_data_id:
        return []
    kader = Transfermarkt(cfg.cache_dir).kader(transfermarkt_id)
    fd = FootballData(cfg.football_data_key, cfg.cache_dir / "football_data").equipo(football_data_id)
    convocados = [_norm(p.get("name", "")) for p in fd.get("squad", [])]
    ausentes = []
    for nombre, _pos, valor in kader:
        if not valor:
            continue
        apellido = _norm(nombre).split()[-1] if nombre else ""
        if apellido and not any(apellido in c for c in convocados):
            ausentes.append((nombre, valor))
    ausentes.sort(key=lambda x: -x[1])
    return ausentes


def multiplicadores(cfg, transfermarkt_id, valor_total, fuera: list[str]) -> tuple[float, float]:
    if not fuera or not transfermarkt_id or not valor_total:
        return 1.0, 1.0
    objetivo = [_norm(x) for x in fuera if x]
    ofensivo = defensivo = 0.0
    for nombre, pos, valor in Transfermarkt(cfg.cache_dir).kader(transfermarkt_id):
        if not valor or not any(o == _norm(nombre).split()[-1] or o in _norm(nombre) for o in objetivo):
            continue
        clase = _clasif(pos)
        if clase == "of":
            ofensivo += valor
        elif clase == "def":
            defensivo += valor
        else:
            ofensivo += valor / 2
            defensivo += valor / 2
    return max(1.0 - K * (ofensivo / valor_total), 0.4), min(1.0 + K * (defensivo / valor_total), 1.6)
