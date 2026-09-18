-- Versión 3: metadatos, catálogo/geometrías y resultados en SQL separados.
CREATE TABLE metadatos (
    clave TEXT PRIMARY KEY NOT NULL,
    valor INTEGER NOT NULL CHECK (typeof(valor) = 'integer' AND valor >= 0)
);
INSERT INTO metadatos (clave, valor) VALUES ('version_esquema', 3);
INSERT INTO metadatos (clave, valor) VALUES ('revision_global', 0);
