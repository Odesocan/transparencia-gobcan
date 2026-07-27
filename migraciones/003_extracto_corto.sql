-- ============================================================================
-- transparencia-gobcan · Migración 003
-- Relaja la longitud mínima de `entrada` de 20 a 5 caracteres.
--
-- El umbral de 20 se puso pensando en las notas de prensa de Gobcan, donde una
-- entradilla más corta que eso indicaba un fallo de extracción. Para el
-- Parlamento no vale: el extracto de una iniciativa puede ser legítimamente
-- muy breve porque nombra el asunto y poco más.
--
-- De las 679 iniciativas del anillo de decisiones, 13 quedan por debajo de 20
-- caracteres y una por debajo de 10:
--     11L/PNLC-0026  "La DANA."            (8)
--     11L/PNLP-0296  "La obesidad."        (12)
--     11L/PNLP-0084  "Salud Mental."       (13)
--     11L/PNLP-0182  "La corrupción."      (14)
--
-- Son datos correctos, no basura: rechazarlos habría dejado fuera iniciativas
-- reales sobre obesidad, salud mental o corrupción. El umbral de 5 sigue
-- detectando lo que la restricción buscaba —campos vacíos o de un carácter—
-- sin descartar extractos breves pero válidos.
-- ============================================================================

ALTER TABLE transp_gobcan.entradas
    DROP CONSTRAINT IF EXISTS entradas_entrada_check;

ALTER TABLE transp_gobcan.entradas
    ADD CONSTRAINT entradas_entrada_check CHECK (length(entrada) >= 5);

-- Comprobación
SELECT conname AS restriccion, pg_get_constraintdef(oid) AS definicion
FROM pg_constraint
WHERE conrelid = 'transp_gobcan.entradas'::regclass
  AND conname LIKE '%entrada%';
