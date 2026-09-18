
CREATE TABLE tramos (
    id TEXT PRIMARY KEY NOT NULL CHECK (length(trim(id)) > 0),
    base_tag TEXT NOT NULL CHECK (length(trim(base_tag)) > 0),
    base_tag_clave TEXT NOT NULL,
    presion_ingreso_tag TEXT NOT NULL,
    presion_egreso_tag TEXT NOT NULL,
    activo INTEGER NOT NULL CHECK (activo IN (0, 1)),
    revision INTEGER NOT NULL CHECK (typeof(revision) = 'integer' AND revision > 0)
);
CREATE UNIQUE INDEX tramos_base_activa ON tramos(base_tag_clave) WHERE activo=1;
CREATE INDEX tramos_revision ON tramos(revision);

-- Sin FK al catálogo: se permiten geometrías de tramos todavía no importados.
CREATE TABLE geometrias (
    tramo_id TEXT PRIMARY KEY NOT NULL CHECK (length(trim(tramo_id)) > 0),
    diametro_exterior_pulgadas REAL NOT NULL CHECK (diametro_exterior_pulgadas > 0),
    espesor_milimetros REAL NOT NULL CHECK (espesor_milimetros > 0),
    longitud_metros REAL NOT NULL CHECK (longitud_metros > 0),
    activa INTEGER NOT NULL CHECK (activa IN (0, 1)),
    version INTEGER NOT NULL CHECK (typeof(version) = 'integer' AND version > 0),
    actualizada_en TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (typeof(revision) = 'integer' AND revision > 0),
    CHECK (diametro_exterior_pulgadas * 0.0254 - 2 * espesor_milimetros / 1000 > 0)
);
CREATE INDEX geometrias_revision ON geometrias(revision);
