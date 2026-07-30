-- ============================================================================
-- transparencia-gobcan · Migración 004
-- Programador fiable: pg_cron dispara el workflow de GitHub por API.
--
-- POR QUÉ EXISTE ESTO. GitHub descarta los cron programados. Medido sobre
-- cuatro días, el cumplimiento por hora iba del 0% al 25%, y las 07:00-08:00
-- UTC —la primera hora de la mañana canaria— eran CERO absoluto: ni una
-- ejecución en cuatro días. Los trabajos `schedule` tienen la prioridad más
-- baja de la cola de GitHub y se descartan cuando hay carga.
--
-- `workflow_dispatch`, en cambio, se ejecuta siempre y al instante. pg_cron sí
-- cumple horarios, porque corre dentro de la base y no compite con nadie. Así
-- que pg_cron pasa a ser el reloj y GitHub solo ejecuta.
--
-- El cron de GitHub se deja puesto como red de seguridad: si la base o el
-- token fallan, algo seguirá corriendo aunque sea con mala latencia.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;

-- OJO CON EL OWNER: es Odesocan, no Cristianodesocan. Este último es un nombre
-- anterior de la cuenta que GitHub redirige. La CLI de `gh` sigue el redirect y
-- funciona, pero la API NO lo sigue en POST y responde 404. Costó un rato.
CREATE OR REPLACE FUNCTION transp_gobcan.disparar_extraccion(
    con_parlamento boolean DEFAULT false
)
RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = transp_gobcan, extensions, vault, public
AS $$
DECLARE
    token text;
    peticion bigint;
BEGIN
    SELECT decrypted_secret INTO token
      FROM vault.decrypted_secrets WHERE name = 'github_token_actions';

    IF token IS NULL THEN
        RAISE EXCEPTION 'Falta el secreto github_token_actions en Vault';
    END IF;

    SELECT net.http_post(
        url := 'https://api.github.com/repos/Odesocan/transparencia-gobcan'
               || '/actions/workflows/extraccion.yml/dispatches',
        headers := jsonb_build_object(
            'Authorization', 'Bearer ' || token,
            'Accept', 'application/vnd.github+json',
            'X-GitHub-Api-Version', '2022-11-28',
            'Content-Type', 'application/json',
            'User-Agent', 'transparencia-gobcan-pgcron'
        ),
        body := jsonb_build_object(
            'ref', 'main',
            'inputs', jsonb_build_object(
                'modo', 'incremental',
                'notificar', 'true',
                'parlamento', CASE WHEN con_parlamento THEN 'true' ELSE 'false' END
            )
        )
    ) INTO peticion;

    RETURN peticion;
END $$;

-- Sin este registro, un disparo que falle sería otra vez invisible: pg_cron no
-- avisa de nada y GitHub tampoco, porque para él la petición nunca llegó.
CREATE TABLE IF NOT EXISTS transp_gobcan.disparos (
    id             bigserial PRIMARY KEY,
    lanzado_en     timestamptz NOT NULL DEFAULT now(),
    peticion_id    bigint,
    con_parlamento boolean NOT NULL DEFAULT false,
    error          text
);

CREATE OR REPLACE FUNCTION transp_gobcan.disparar_y_registrar(
    con_parlamento boolean DEFAULT false
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = transp_gobcan, extensions, vault, public
AS $$
DECLARE
    peticion bigint;
BEGIN
    peticion := transp_gobcan.disparar_extraccion(con_parlamento);
    INSERT INTO transp_gobcan.disparos (peticion_id, con_parlamento)
    VALUES (peticion, con_parlamento);
EXCEPTION WHEN OTHERS THEN
    INSERT INTO transp_gobcan.disparos (con_parlamento, error) VALUES (con_parlamento, SQLERRM);
END $$;

-- pg_cron corre en UTC, igual que el cron de GitHub. Pero aquí sí se puede
-- resolver el cambio de hora: en vez de fijar horas UTC que se desplazan en
-- octubre, se programa una franja amplia y la función comprueba la hora canaria
-- REAL antes de disparar. El horario efectivo es siempre el mismo y desaparece
-- la tarea de reajustar el cron dos veces al año.
CREATE OR REPLACE FUNCTION transp_gobcan.disparar_si_toca(
    con_parlamento boolean DEFAULT false,
    hora_desde int DEFAULT 9,
    hora_hasta int DEFAULT 20
)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = transp_gobcan, extensions, vault, public
AS $$
DECLARE
    hora_canaria int;
BEGIN
    hora_canaria := EXTRACT(HOUR FROM (now() AT TIME ZONE 'Atlantic/Canary'));
    IF hora_canaria < hora_desde OR hora_canaria > hora_hasta THEN
        RETURN;
    END IF;
    PERFORM transp_gobcan.disparar_y_registrar(con_parlamento);
END $$;

ALTER TABLE transp_gobcan.disparos ENABLE ROW LEVEL SECURITY;

-- Fuera cualquier programación anterior, para no duplicar disparos
SELECT cron.unschedule(jobname) FROM cron.job WHERE jobname LIKE 'transparencia-%';

SELECT cron.schedule('transparencia-jornada', '30 7-20 * * 1-5',
    $$SELECT transp_gobcan.disparar_si_toca(false, 9, 20)$$);

SELECT cron.schedule('transparencia-cierre', '0 21,22 * * *',
    $$SELECT transp_gobcan.disparar_si_toca(true, 22, 22)$$);

-- ---------------------------------------------------------------------------
-- REQUISITO PREVIO, que no puede ir en SQL: el token de GitHub en Vault.
--
--   SELECT vault.create_secret('github_pat_...', 'github_token_actions',
--                              'Token para que pg_cron dispare el workflow');
--
-- Cómo debe estar configurado el token, y cómo diagnosticarlo cuando falla,
-- en docs/programacion-fiable.md. Léelo antes de pelearte con los 404.
-- ---------------------------------------------------------------------------

SELECT jobname, schedule, active FROM cron.job WHERE jobname LIKE 'transparencia-%';
