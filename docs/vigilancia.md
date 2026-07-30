# Vigilancia del pipeline

Qué mirar para saber si esto sigue funcionando, y qué ha fallado ya.

Durante las primeras semanas la revisión es **manual y deliberada**: primero hay
que ver qué se rompe de verdad, y luego automatizar contra eso. Automatizar
alertas antes de tener evidencia es fabricar trabajo y ruido.

> La lección de los dos primeros fallos: **todo en verde no significa que
> funcione**. El workflow decía «success» en cada ejecución, los logs no
> registraban ninguna anomalía, y el sistema llevaba un día sin avisar a nadie
> y borrando su propio estado cada noche. Se encontraron mirando números que no
> cuadraban, no porque saltara ninguna alarma.

---

## Las tres consultas

Se pegan en el editor SQL de Supabase. Con una vez por semana basta al
principio; si algo se rompe, se verá aquí antes que en ningún otro sitio.

### 1. ¿Salen los avisos?

Es la más útil de las tres, porque **mira el resultado y no el proceso**. Fue la
que destapó los dos primeros fallos.

```sql
SELECT COALESCE(fuente::text,'TOTAL') AS origen,
       count(*) AS entradas,
       count(*) FILTER (WHERE es_alerta) AS alertas,
       count(*) FILTER (WHERE es_alerta AND notificada_en IS NULL) AS pendientes
FROM transp_gobcan.entradas GROUP BY ROLLUP(fuente) ORDER BY 1;
```

**Pendientes debería ser 0 o un número muy pequeño** —lo publicado desde el
último envío—. Si crece, o el correo no está saliendo o algo está borrando el
sello de notificación. Las dos cosas ya han pasado.

### 2. ¿Cómo van las ejecuciones?

```sql
SELECT to_char(inicio,'DD/MM HH24:MI') AS cuando, fuente::text, modo,
       filas_leidas, filas_insertadas, filas_descartadas,
       round(100.0*COALESCE((entradillas_por_origen->>'sumario')::int,0)
             / NULLIF(filas_leidas-filas_descartadas,0), 0) AS pct_sumario,
       anomalias, exito
FROM transp_gobcan.logs_ejecucion
ORDER BY inicio DESC LIMIT 20;
```

| Señal | Qué significa |
|---|---|
| `exito` en falso | Lo evidente. El detalle está en la columna `errores` |
| `pct_sumario` por debajo de 30 | El gabinete cambió la plantilla editorial y la entradilla se está sacando del primer párrafo |
| `anomalias` no vacío | Casi siempre, una categoría nueva sin correspondencia en `config/areas.yaml` |
| `filas_descartadas` por encima del 5% | Cambió la estructura de la fuente |
| `filas_leidas` muy por debajo de lo normal | La paginación se corta antes de tiempo |

Referencias: el Gobierno publica unas 15 entradas útiles al día, y el Parlamento
unas 0,6 decisiones.

### 3. ¿Se sigue clasificando bien?

```sql
SELECT area_origen::text, count(*),
       round(100.0*count(*)/sum(count(*)) OVER (),1) AS pct
FROM transp_gobcan.entradas GROUP BY area_origen;

SELECT count(*) FILTER (WHERE area='sin_asignar') AS sin_area,
       round(100.0*count(*) FILTER (WHERE area='sin_asignar')/count(*),1) AS pct
FROM transp_gobcan.entradas;
```

`sin_asignar` estaba en el **0,8%** tras la carga inicial. Si sube por encima
del 5%, la fuente cambió de nomenclatura de consejerías y hay que añadir las
correspondencias a `config/areas.yaml`.

---

## Fallos que ya han ocurrido

Se documentan aquí porque los tres tienen la misma forma —**fallan en silencio,
sin que nada se ponga en rojo**— y porque el siguiente probablemente también.

### El aviso no se enviaba en las ejecuciones programadas

*29 de julio de 2026. Un día sin avisar a nadie.*

La condición del paso era `inputs.notificar != false`, que parece razonable. En
un evento `schedule` no existe `inputs`, y GitHub Actions **convierte a número
los dos lados** al comparar tipos distintos: `null` y `false` pasan a ser `0`,
así que la condición resultaba falsa y el paso aparecía como `skipped` en cada
ejecución. Solo funcionaba en las manuales, que es donde se probó.

La condición correcta pregunta primero por el tipo de evento:
`github.event_name != 'workflow_dispatch' || inputs.notificar`.

**Lección**: una condición de Actions que funciona en `workflow_dispatch` no
está probada hasta que se ve correr en `schedule`.

### El UPSERT borraba el sello de notificación

*29 de julio de 2026. Encontrado tirando del hilo de un recuento que no cuadraba.*

`notificada_en` estaba entre las columnas que el UPSERT sobrescribe. Es estado
**nuestro** de envío, no un dato de la fuente, así que cada recorrido nocturno
del Parlamento reescribía sus 679 iniciativas poniéndolo a null y borraba el
sello de 205 alertas.

No llegaron a reenviarse porque `ALERTAS_DESDE` las filtra por fecha —una
casualidad afortunada, no un diseño—. El daño real era que el recuento de
pendientes quedaba inservible para vigilar.

**Lección**: distinguir en el modelo lo que viene de la fuente de lo que es
estado propio. Lo segundo no se sobrescribe nunca al reprocesar. Hoy eso es
`notificada_en`, `creado_en` y el identificador.

### GitHub no ejecutaba los cron programados, y ajustar horas lo empeoró

*30 de julio de 2026. Cuatro días de datos para entenderlo.*

El síntoma que lo destapó: «no me aparecen ejecuciones a primera hora». Medido,
el cumplimiento del cron era del 24%, y las 07:00-08:00 UTC eran **cero
absoluto**. El primer intento de arreglo fue mover los disparos de la mañana a
las 8:13 y 8:43 UTC, calculando bien la zona horaria pero **sin comprobar si esa
hora se cumplía**: es justo la peor. Empeoró la situación.

La solución no era ajustar el cron, era dejar de depender de él. Ver
[`programacion-fiable.md`](programacion-fiable.md).

**Lección**: cuando algo no se ejecuta, medir el cumplimiento POR HORA antes de
mover horarios. El agregado esconde que unas horas son 0% y otras 25%.

### El token de GitHub: ocho intentos por un 404 que no explicaba nada

*30 de julio de 2026.*

Montar el disparador exigía un token de GitHub, y costó ocho intentos porque
**GitHub responde 404 a cuatro causas distintas** sin distinguirlas: token mal
copiado, owner equivocado en la URL, token sin aprobar por la organización, y
token con el repositorio seleccionado pero sin permisos. La última era la real.

La prueba que lo resuelve —preguntarle al token qué repositorios ve— está en
[`programacion-fiable.md`](programacion-fiable.md), con la tabla de códigos.

**Lección**: ante un 404 de la API de GitHub, no deducir la causa. Preguntar al
token qué alcanza y comparar con lo esperado.

### El extractor de Parcan se comía 50 minutos en cada ejecución manual

*Menor, pero costó 690 peticiones innecesarias a una fuente pública.* La
condición del job lo disparaba en cualquier `workflow_dispatch`. Ahora tiene un
interruptor propio, desactivado por defecto.

---

## Cuándo se ejecuta de verdad

GitHub **no cumple los cron programados**. Medido sobre tres días con el cron
anterior, que pedía una ejecución cada 30 minutos:

| | |
|---|---|
| Pedidas | 25 al día laborable |
| Ejecutadas | 7-8, un **24%** |
| Separación real | mediana de 104 minutos, máxima de 197 |
| Primera del día | 10:33 hora canaria, hora y media tarde |

No es un fallo del proyecto: los trabajos programados tienen la prioridad más
baja de la cola y se descartan cuando hay carga. Las 07:00-09:00 UTC son hora
punta mundial, que es justo cuando peor se cumple.

**No se pierde ningún dato**: la ventana incremental es de 24 horas y el UPSERT
es idempotente, así que una sola ejecución al día dejaría la base completa. Lo
que se pierde es latencia en el aviso.

**Ya no dependemos de ese cron.** El reloj es `pg_cron` en Supabase, que llama a
la API de GitHub para lanzar el workflow por `workflow_dispatch` —que sí se
ejecuta siempre—. El detalle, la configuración del token y la guía de
diagnóstico están en [`programacion-fiable.md`](programacion-fiable.md).

El cron de GitHub se deja puesto como red de seguridad: si la base o el token
fallan, algo seguirá corriendo aunque con mala latencia.

### Cuarta consulta: ¿salen los disparos?

```sql
SELECT d.id, to_char(d.lanzado_en,'DD/MM HH24:MI') AS lanzado, r.status_code,
       left(COALESCE(r.content,''), 90) AS respuesta, d.error
FROM transp_gobcan.disparos d
LEFT JOIN net._http_response r ON r.id = d.peticion_id
ORDER BY d.id DESC LIMIT 15;
```

`status_code = 204` es lo correcto. Un **401** significa casi siempre que **el
token de GitHub ha caducado**, y eso para la automatización sin que nada avise.

> **Tarea con fecha: el 28 de septiembre de 2026.** Caduca el token de GitHub.
> Cuando lo haga, los disparos devolverán 401 y dejarán de llegar avisos, sin
> ningún error visible. Renovarlo y guardarlo con `vault.update_secret`.

---

## Lo que sabemos que habrá que hacer

No son fallos, son deudas conocidas:

- **`emergencia_social` solo ha disparado dos veces en tres años.** Sus términos
  no son los que usa el gabinete. Se afina contra el corpus con
  `clasificar --recalcular`, que reevalúa el histórico sin tocar la fuente.
- **Parcan reextrae 506 iniciativas ya cerradas** que no van a cambiar. Recorrer
  solo las abiertas más las nuevas bajaría el recorrido de 50 a unos 12 minutos.
- **La carga es todo o nada.** Se acumula en memoria y se escribe al final: si el
  UPSERT falla, se pierde la extracción entera. Ya pasó una vez, con 48 minutos
  de trabajo tirados. Cargar por lotes conforme se extrae lo resolvería.
- **`datos.js` no se publica en ningún sitio** salvo como artefacto del workflow.
  Si la interfaz va a vivir en la web, hay que decidir dónde se aloja.
