
CREATE TABLE resultados_actuales (
    tramo_id TEXT PRIMARY KEY NOT NULL REFERENCES tramos(id),
    presion_promedio_bar_abs REAL NOT NULL CHECK (presion_promedio_bar_abs > 0),
    linepack_sm3 REAL NOT NULL CHECK (linepack_sm3 >= 0),
    geometria_version INTEGER NOT NULL CHECK (geometria_version > 0),
    catalogo_revision INTEGER NOT NULL CHECK (catalogo_revision > 0),
    calculado_en TEXT NOT NULL,
    actualizacion_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0)
);
CREATE INDEX actuales_revision ON resultados_actuales(revision);
CREATE TABLE predicciones_linepack (
    tramo_id TEXT PRIMARY KEY NOT NULL REFERENCES tramos(id),
    presiones_json TEXT NOT NULL,
    linepacks_json TEXT NOT NULL,
    firma_presiones_json TEXT NOT NULL,
    geometria_version INTEGER NOT NULL CHECK (geometria_version > 0),
    catalogo_revision INTEGER NOT NULL CHECK (catalogo_revision > 0),
    calculado_en TEXT NOT NULL,
    actualizacion_id TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision > 0)
);
CREATE INDEX predicciones_revision ON predicciones_linepack(revision);
CREATE TABLE estado_adquisicion (
    tramo_id TEXT NOT NULL REFERENCES tramos(id),
    ciclo TEXT NOT NULL CHECK (ciclo IN ('actual', 'predictivo')),
    ultimo_intento_en TEXT NOT NULL,
    ultima_lectura_valida_en TEXT,
    estado TEXT NOT NULL CHECK (estado IN ('valido', 'error_lectura', 'error_calculo')),
    detalle TEXT,
    resultado_revision INTEGER,
    revision INTEGER NOT NULL CHECK (revision > 0),
    PRIMARY KEY (tramo_id, ciclo)
);
CREATE INDEX adquisicion_revision ON estado_adquisicion(revision);
