-- Estructura de transición PostgreSQL. Algoritmos permanecen en Python.
-- Tablas de compatibilidad permiten consultas futuras desde Python.
CREATE TABLE IF NOT EXISTS fuente_registro (
    archivo TEXT NOT NULL, ordinal INTEGER NOT NULL, fila_json JSONB NOT NULL,
    PRIMARY KEY (archivo, ordinal)
);
CREATE TABLE IF NOT EXISTS programaciones (
    caso_id TEXT PRIMARY KEY, hospital TEXT NOT NULL, fecha DATE NOT NULL,
    inicio TIME NOT NULL, fila_json JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_prog_hospital_fecha ON programaciones(hospital,fecha,inicio);
CREATE TABLE IF NOT EXISTS pendientes (
    caso_id TEXT PRIMARY KEY, motivo TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS propuestas (
    caso_id TEXT PRIMARY KEY, destino TEXT NOT NULL, fila_json JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS eventos (
    paso INTEGER PRIMARY KEY, instante_virtual TIMESTAMP WITHOUT TIME ZONE NOT NULL,
    tipo TEXT NOT NULL, estado TEXT NOT NULL, detalle_json JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS configuracion (
    clave TEXT PRIMARY KEY, valor_json JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS programaciones_base (
    caso_id TEXT PRIMARY KEY, hospital TEXT NOT NULL, fecha DATE NOT NULL,
    inicio TIME NOT NULL, fila_json JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS pendientes_base (
    caso_id TEXT PRIMARY KEY, motivo TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS grafo_nodos (
    id_nodo TEXT PRIMARY KEY, tipo_nodo TEXT NOT NULL, datos_json JSONB NOT NULL
);
CREATE TABLE IF NOT EXISTS grafo_aristas (
    id_arista BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    origen_id TEXT NOT NULL REFERENCES grafo_nodos(id_nodo),
    destino_id TEXT NOT NULL REFERENCES grafo_nodos(id_nodo),
    relacion TEXT NOT NULL,
    tiempo_min NUMERIC NULL,
    UNIQUE (origen_id,destino_id,relacion)
);
CREATE INDEX IF NOT EXISTS ix_arista_origen_rel ON grafo_aristas(origen_id,relacion);
CREATE INDEX IF NOT EXISTS ix_arista_destino_rel ON grafo_aristas(destino_id,relacion);
