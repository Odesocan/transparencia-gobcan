-- ============================================================================
-- transparencia-gobcan · Migración 001
-- Crea el schema transp_gobcan con la tabla de entradas y la de logs.
--
-- PROPUESTA PENDIENTE DE VISTO BUENO. No se ha ejecutado en Supabase.
--
-- Decisiones que vienen del reconocimiento de las fuentes (Hito 1):
--   - Tabla desnormalizada, para consumo directo desde la interfaz sin joins.
--   - `hash_dedup` como clave de conflicto: da idempotencia al UPSERT.
--   - `area` nunca es NULL: hay un valor residual explícito, porque un NULL
--     silencioso deja el 14% de las entradas invisible a cualquier filtro.
--   - `territorio_origen` distingue dato publicado de inferencia nuestra.
--   - `entrada_origen` registra de qué nivel de la cascada salió la entradilla,
--     para detectar que el gabinete ha cambiado de práctica editorial.
--   - NO se almacena el cuerpo de la noticia. Solo título, entradilla y metadatos.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS transp_gobcan;

COMMENT ON SCHEMA transp_gobcan IS
    'Seguimiento de la actividad ejecutiva y parlamentaria de Canarias. ODESOCAN.';

-- ---------------------------------------------------------------------------
-- Tipos enumerados: acotan los valores posibles en la propia base de datos,
-- en lugar de confiar en que la capa de Python siempre acierte.
-- ---------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE transp_gobcan.fuente_t AS ENUM ('gobierno', 'parlamento');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE transp_gobcan.origen_territorio_t AS ENUM ('publicado', 'inferido', 'defecto');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    CREATE TYPE transp_gobcan.origen_entradilla_t AS ENUM ('sumario', 'parrafo', 'excerpt');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------------------------------------------------------------------------
-- Tabla principal
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transp_gobcan.entradas (
    -- Identificación
    hash_dedup          text PRIMARY KEY,
    id_fuente           text        NOT NULL,
    fuente              transp_gobcan.fuente_t NOT NULL,

    -- Fechas
    fecha_ext           timestamptz NOT NULL DEFAULT now(),
    fecha_real          date        NOT NULL,
    fecha_modificacion  timestamptz,

    -- Contenido. El cuerpo completo no se guarda, por decisión de alcance.
    titulo              text        NOT NULL CHECK (length(titulo) >= 5),
    entrada             text        NOT NULL CHECK (length(entrada) >= 20),
    entrada_origen      transp_gobcan.origen_entradilla_t NOT NULL,
    url                 text        NOT NULL,

    -- Clasificación
    area                text        NOT NULL,
    areas               text[]      NOT NULL DEFAULT '{}',
    territorio          text        NOT NULL DEFAULT 'Canarias',
    territorio_origen   transp_gobcan.origen_territorio_t NOT NULL DEFAULT 'defecto',

    -- Solo para entradas del Parlamento
    grupo_parlamentario text,
    tipo_iniciativa     text,
    situacion           text,

    -- Capa semántica de alertas
    es_alerta           boolean     NOT NULL DEFAULT false,
    motivo_alerta       text,
    materias            text[]      NOT NULL DEFAULT '{}',
    actos               text[]      NOT NULL DEFAULT '{}',
    notificada_en       timestamptz,

    -- Trazabilidad
    creado_en           timestamptz NOT NULL DEFAULT now(),
    actualizado_en      timestamptz NOT NULL DEFAULT now(),

    -- Una fecha anterior al arranque del observatorio indica fallo de parseo,
    -- no una noticia antigua legítima.
    CONSTRAINT fecha_en_rango CHECK (fecha_real >= DATE '2023-05-01'
                                     AND fecha_real <= CURRENT_DATE),
    CONSTRAINT id_unico_por_fuente UNIQUE (fuente, id_fuente)
);

COMMENT ON TABLE  transp_gobcan.entradas IS
    'Publicaciones capturadas del Gobierno y el Parlamento. No incluye el cuerpo de la noticia.';
COMMENT ON COLUMN transp_gobcan.entradas.hash_dedup IS
    'sha256(fuente:id_fuente) truncado. Clave de conflicto del UPSERT: da idempotencia.';
COMMENT ON COLUMN transp_gobcan.entradas.entrada IS
    'Entradilla de 2-3 líneas construida a partir del sumario editorial, no del excerpt de la fuente.';
COMMENT ON COLUMN transp_gobcan.entradas.entrada_origen IS
    'Nivel de la cascada del que salió la entradilla. Su distribución vigila la salud del extractor.';
COMMENT ON COLUMN transp_gobcan.entradas.territorio_origen IS
    'Distingue un territorio publicado por la fuente de una inferencia nuestra sobre el texto.';
COMMENT ON COLUMN transp_gobcan.entradas.area IS
    'Vocabulario cerrado de config/areas.yaml, alineado con cargos_publicos.cp_altos_cargos.area.';

-- Índices pensados para lo que la interfaz va a preguntar de verdad:
-- listado por fecha, filtro por área y por grupo, y buscador por palabra clave.
CREATE INDEX IF NOT EXISTS idx_entradas_fecha    ON transp_gobcan.entradas (fecha_real DESC);
CREATE INDEX IF NOT EXISTS idx_entradas_fuente   ON transp_gobcan.entradas (fuente, fecha_real DESC);
CREATE INDEX IF NOT EXISTS idx_entradas_area     ON transp_gobcan.entradas (area);
CREATE INDEX IF NOT EXISTS idx_entradas_grupo    ON transp_gobcan.entradas (grupo_parlamentario)
    WHERE grupo_parlamentario IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entradas_alerta   ON transp_gobcan.entradas (es_alerta, fecha_real DESC)
    WHERE es_alerta;
CREATE INDEX IF NOT EXISTS idx_entradas_materias ON transp_gobcan.entradas USING gin (materias);

-- Búsqueda por palabra clave en español sobre título y entradilla.
CREATE INDEX IF NOT EXISTS idx_entradas_texto ON transp_gobcan.entradas
    USING gin (to_tsvector('spanish', titulo || ' ' || entrada));

-- ---------------------------------------------------------------------------
-- Tabla de logs de ejecución
--
-- Existe para aprender de los fallos del extractor. Por eso guarda el motivo de
-- cada descarte y las anomalías detectadas, no solo el recuento de filas.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS transp_gobcan.logs_ejecucion (
    id                    bigserial PRIMARY KEY,
    inicio                timestamptz NOT NULL,
    fin                   timestamptz,
    duracion_s            numeric GENERATED ALWAYS AS
                              (EXTRACT(EPOCH FROM (fin - inicio))) STORED,
    fuente                transp_gobcan.fuente_t NOT NULL,
    modo                  text NOT NULL CHECK (modo IN ('historico','incremental','respaldo')),

    filas_leidas          integer NOT NULL DEFAULT 0,
    filas_insertadas      integer NOT NULL DEFAULT 0,
    filas_actualizadas    integer NOT NULL DEFAULT 0,
    filas_descartadas     integer NOT NULL DEFAULT 0,

    -- El detalle es lo valioso: {"entradilla_vacia": 3, "fecha_fuera_rango": 1}
    descartes_por_motivo  jsonb NOT NULL DEFAULT '{}'::jsonb,
    -- Distribución de la cascada: {"sumario": 12, "parrafo": 3}
    entradillas_por_origen jsonb NOT NULL DEFAULT '{}'::jsonb,

    anomalias             text[] NOT NULL DEFAULT '{}',
    errores               text[] NOT NULL DEFAULT '{}',
    exito                 boolean NOT NULL DEFAULT true,
    version_extractor     text
);

COMMENT ON TABLE  transp_gobcan.logs_ejecucion IS
    'Una fila por ejecución del pipeline. Registra el motivo de los descartes para aprender de los fallos.';
COMMENT ON COLUMN transp_gobcan.logs_ejecucion.descartes_por_motivo IS
    'Recuento por motivo de descarte, no total agregado.';
COMMENT ON COLUMN transp_gobcan.logs_ejecucion.anomalias IS
    'Señales de degradación silenciosa: categorías nuevas, caída de sumarios, volumen anómalo.';

CREATE INDEX IF NOT EXISTS idx_logs_inicio ON transp_gobcan.logs_ejecucion (inicio DESC);
CREATE INDEX IF NOT EXISTS idx_logs_fallos ON transp_gobcan.logs_ejecucion (inicio DESC)
    WHERE NOT exito;

-- ---------------------------------------------------------------------------
-- Mantener actualizado_en al día
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION transp_gobcan.tocar_actualizado_en()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    NEW.actualizado_en = now();
    RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_entradas_actualizado ON transp_gobcan.entradas;
CREATE TRIGGER trg_entradas_actualizado
    BEFORE UPDATE ON transp_gobcan.entradas
    FOR EACH ROW EXECUTE FUNCTION transp_gobcan.tocar_actualizado_en();

-- ---------------------------------------------------------------------------
-- Seguridad
--
-- La herramienta es interna del equipo técnico. Se activa RLS sin políticas de
-- lectura pública: solo la clave de servicio escribe y lee (service_role tiene
-- BYPASSRLS en Supabase). Cuando se decida abrir la interfaz al público, se
-- añadirá una política de lectura en una migración propia.
-- ---------------------------------------------------------------------------
ALTER TABLE transp_gobcan.entradas       ENABLE ROW LEVEL SECURITY;
ALTER TABLE transp_gobcan.logs_ejecucion ENABLE ROW LEVEL SECURITY;

-- ---------------------------------------------------------------------------
-- Permisos de rol (específico de Supabase)
--
-- Los roles anon / authenticated / service_role solo existen en Supabase. Se
-- comprueba su existencia para que esta migración siga siendo ejecutable en un
-- PostgreSQL limpio, que es donde se prueba antes de aplicarla.
--
-- Se concede solo a service_role: la herramienta es interna y escribe con la
-- clave de servicio. A anon y authenticated no se les da nada todavía.
-- ---------------------------------------------------------------------------
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'service_role') THEN
        GRANT USAGE ON SCHEMA transp_gobcan TO service_role;
        GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA transp_gobcan TO service_role;
        GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA transp_gobcan TO service_role;
        -- Que lo creado en el futuro herede los permisos sin repetir el GRANT
        ALTER DEFAULT PRIVILEGES IN SCHEMA transp_gobcan
            GRANT ALL PRIVILEGES ON TABLES TO service_role;
        ALTER DEFAULT PRIVILEGES IN SCHEMA transp_gobcan
            GRANT ALL PRIVILEGES ON SEQUENCES TO service_role;
    END IF;
END $$;

-- ---------------------------------------------------------------------------
-- Comprobación final: deja constancia de lo creado en la salida del editor SQL.
-- ---------------------------------------------------------------------------
SELECT table_name AS tabla,
       (SELECT count(*) FROM information_schema.columns c
         WHERE c.table_schema = 'transp_gobcan' AND c.table_name = t.table_name) AS columnas
FROM information_schema.tables t
WHERE table_schema = 'transp_gobcan'
ORDER BY table_name;
