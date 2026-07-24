CREATE TABLE IF NOT EXISTS combinadas (
    id INTEGER PRIMARY KEY,
    cuota_total REAL NOT NULL,
    stake REAL NOT NULL,
    fecha TEXT NOT NULL,
    resultado TEXT,
    ganancia REAL
);

CREATE TABLE IF NOT EXISTS apuestas (
    id INTEGER PRIMARY KEY,
    partido_id INTEGER,
    equipo_local_nombre TEXT,
    equipo_visita_nombre TEXT,
    equipo_local_fifa TEXT,
    equipo_visita_fifa TEXT,
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
    fecha TEXT,
    combinada_id INTEGER REFERENCES combinadas(id)
);
