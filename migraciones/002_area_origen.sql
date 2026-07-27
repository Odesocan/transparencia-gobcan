-- ============================================================================
-- transparencia-gobcan · Migración 002
-- Añade `area_origen`, análogo a `territorio_origen`.
--
-- PROPUESTA PENDIENTE DE VISTO BUENO. No se ha ejecutado.
--
-- Por qué hace falta ahora y no antes: en Gobcan el área viene dada por el
-- filtro de la fuente, así que siempre es un dato publicado. En el Parlamento
-- no. Solo las iniciativas que pasan por comisión traen comisión dictaminante,
-- que sí es un dato publicado; las proposiciones no de ley en pleno —que son
-- la mayoría— no la tienen, y su área hay que deducirla del extracto.
--
-- Mezclar las dos cosas en la misma columna sin distinguirlas presentaría una
-- deducción nuestra como si fuera un dato de la Cámara. Es el mismo criterio
-- que ya se aplicó a `territorio_origen`.
--
-- La migración es aditiva: no toca datos existentes ni rompe consultas. Las
-- 15.365 entradas ya cargadas quedan marcadas como 'publicado', que es lo que
-- son: su área sale de la categoría que asigna el propio portal.
-- ============================================================================

DO $$ BEGIN
    CREATE TYPE transp_gobcan.origen_area_t AS ENUM ('publicado', 'inferido', 'defecto');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

ALTER TABLE transp_gobcan.entradas
    ADD COLUMN IF NOT EXISTS area_origen transp_gobcan.origen_area_t
    NOT NULL DEFAULT 'publicado';

COMMENT ON COLUMN transp_gobcan.entradas.area_origen IS
    'Distingue un área publicada por la fuente (categoría de Gobcan, comisión '
    'dictaminante de Parcan) de una deducida por nosotras a partir del texto.';

-- Las entradas del Parlamento sin comisión llevarán 'inferido'; conviene poder
-- filtrarlas rápido para revisarlas a mano cuando haga falta.
CREATE INDEX IF NOT EXISTS idx_entradas_area_origen
    ON transp_gobcan.entradas (area_origen)
    WHERE area_origen <> 'publicado';

-- Comprobación
SELECT area_origen, count(*) AS entradas
FROM transp_gobcan.entradas
GROUP BY area_origen ORDER BY 1;
