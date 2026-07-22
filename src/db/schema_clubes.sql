CREATE TABLE IF NOT EXISTS ligas (
    id INTEGER PRIMARY KEY,
    codigo TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    pais TEXT,
    understat TEXT,
    odds_api TEXT,
    fd_org TEXT
);

CREATE TABLE IF NOT EXISTS partidos_club (
    id INTEGER PRIMARY KEY,
    liga_id INTEGER NOT NULL REFERENCES ligas(id),
    temporada TEXT NOT NULL,
    fecha TEXT NOT NULL,
    local TEXT NOT NULL,
    visita TEXT NOT NULL,
    goles_local INTEGER,
    goles_visita INTEGER,
    tiros_local INTEGER,
    tiros_visita INTEGER,
    tiros_arco_local INTEGER,
    tiros_arco_visita INTEGER,
    corners_local INTEGER,
    corners_visita INTEGER,
    faltas_local INTEGER,
    faltas_visita INTEGER,
    amarillas_local INTEGER,
    amarillas_visita INTEGER,
    rojas_local INTEGER,
    rojas_visita INTEGER,
    ps_h REAL, ps_d REAL, ps_a REAL,
    psc_h REAL, psc_d REAL, psc_a REAL,
    p_over25 REAL, p_under25 REAL,
    pc_over25 REAL, pc_under25 REAL,
    ah_linea REAL,
    ahc_linea REAL, pcah_h REAL, pcah_a REAL,
    xg_local REAL,
    xg_visita REAL,
    UNIQUE (liga_id, temporada, local, visita)
);

CREATE INDEX IF NOT EXISTS idx_partidos_club_liga_fecha ON partidos_club (liga_id, fecha);

CREATE TABLE IF NOT EXISTS equipos_competicion (
    equipo_id INTEGER NOT NULL REFERENCES equipos(id),
    liga_id INTEGER NOT NULL REFERENCES ligas(id),
    PRIMARY KEY (equipo_id, liga_id)
);
