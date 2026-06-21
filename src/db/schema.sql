CREATE TABLE IF NOT EXISTS equipos (
    id INTEGER PRIMARY KEY,
    fifa_code TEXT UNIQUE,
    nombre TEXT NOT NULL,
    confederacion TEXT,
    api_football_id INTEGER UNIQUE,
    sofascore_id INTEGER,
    fbref_id TEXT,
    eloratings_name TEXT,
    odds_api_name TEXT,
    football_data_id INTEGER UNIQUE,
    football_data_name TEXT,
    elo REAL,
    valor_plantilla REAL,
    transfermarkt_id INTEGER,
    fuerza_ataque REAL,
    fuerza_defensa REAL,
    estilo TEXT,
    tecnico TEXT,
    actualizado TEXT
);

CREATE TABLE IF NOT EXISTS jugadores (
    id INTEGER PRIMARY KEY,
    api_football_id INTEGER UNIQUE,
    equipo_id INTEGER REFERENCES equipos(id),
    nombre TEXT NOT NULL,
    posicion TEXT,
    club TEXT,
    minutos INTEGER,
    xg90 REAL,
    xa90 REAL,
    estado TEXT,
    actualizado TEXT
);

CREATE TABLE IF NOT EXISTS partidos (
    id INTEGER PRIMARY KEY,
    api_football_id INTEGER UNIQUE,
    football_data_id INTEGER UNIQUE,
    fecha TEXT,
    equipo_local_id INTEGER REFERENCES equipos(id),
    equipo_visita_id INTEGER REFERENCES equipos(id),
    fase TEXT,
    grupo TEXT,
    estadio TEXT,
    ciudad TEXT,
    altitud REAL,
    clima_json TEXT,
    arbitro TEXT,
    estado TEXT,
    actualizado TEXT
);

CREATE TABLE IF NOT EXISTS cuotas (
    id INTEGER PRIMARY KEY,
    partido_id INTEGER REFERENCES partidos(id),
    casa TEXT,
    mercado TEXT,
    seleccion TEXT,
    cuota REAL,
    capturado TEXT
);

CREATE TABLE IF NOT EXISTS predicciones (
    id INTEGER PRIMARY KEY,
    partido_id INTEGER REFERENCES partidos(id),
    mercado TEXT,
    seleccion TEXT,
    prob_modelo REAL,
    prob_min REAL,
    prob_max REAL,
    ev REAL,
    confianza TEXT,
    generado TEXT
);

CREATE TABLE IF NOT EXISTS resultados (
    id INTEGER PRIMARY KEY,
    partido_id INTEGER UNIQUE REFERENCES partidos(id),
    goles_local INTEGER,
    goles_visita INTEGER,
    corners_local INTEGER,
    corners_visita INTEGER,
    tarjetas_local INTEGER,
    tarjetas_visita INTEGER,
    finalizado TEXT
);

CREATE TABLE IF NOT EXISTS apuestas (
    id INTEGER PRIMARY KEY,
    partido_id INTEGER REFERENCES partidos(id),
    mercado TEXT,
    seleccion TEXT,
    cuota_betano REAL,
    cuota_cierre REAL,
    stake REAL,
    prob_modelo REAL,
    ev REAL,
    clv REAL,
    resultado TEXT,
    ganancia REAL,
    fecha TEXT
);

CREATE TABLE IF NOT EXISTS historico (
    api_fixture_id INTEGER PRIMARY KEY,
    fecha TEXT,
    liga TEXT,
    liga_id INTEGER,
    season INTEGER,
    home_api_id INTEGER,
    home_name TEXT,
    away_api_id INTEGER,
    away_name TEXT,
    goles_home INTEGER,
    goles_away INTEGER
);

CREATE INDEX IF NOT EXISTS idx_historico_fecha ON historico(fecha);

CREATE TABLE IF NOT EXISTS standings (
    id INTEGER PRIMARY KEY,
    grupo TEXT,
    equipo_id INTEGER REFERENCES equipos(id),
    posicion INTEGER,
    jugados INTEGER,
    ganados INTEGER,
    empatados INTEGER,
    perdidos INTEGER,
    goles_favor INTEGER,
    goles_contra INTEGER,
    diferencia INTEGER,
    puntos INTEGER,
    actualizado TEXT,
    UNIQUE(grupo, equipo_id)
);

CREATE INDEX IF NOT EXISTS idx_cuotas_partido ON cuotas(partido_id);
CREATE INDEX IF NOT EXISTS idx_predicciones_partido ON predicciones(partido_id);
CREATE INDEX IF NOT EXISTS idx_partidos_fecha ON partidos(fecha);
