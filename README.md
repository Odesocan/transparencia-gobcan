# transparencia-gobcan

Herramienta interna del equipo técnico de **ODESOCAN · Observatorio de Derechos Sociales
de Canarias** para detectar y registrar de forma continuada la actividad ejecutiva y
parlamentaria del Gobierno de Canarias y del Parlamento de Canarias.

Sustituye el descubrimiento informal, irregular y parcial por una detección trazada y
actualizada, que alimenta el trabajo de fiscalización del observatorio.

---

## Qué hace y qué no hace

Captura las publicaciones de las dos fuentes, las normaliza contra un vocabulario cerrado
de áreas, deriva su ámbito territorial, valida la calidad de cada fila y carga el resultado
en Supabase. Sobre lo cargado aplica una capa semántica que decide qué merece notificarse
por correo.

**Almacena** título, entradilla de dos o tres líneas, metadatos y enlace.
**No almacena** el cuerpo completo de la noticia.

> Una precisión que conviene tener presente al leer los datos: las dos fuentes son portales
> de **comunicación institucional**, no portales de transparencia. Publican lo que cada
> gabinete decide contar, con el enfoque con que decide contarlo. La herramienta detecta
> actividad *comunicada*, no actividad ejecutiva completa. Que una medida no aparezca aquí
> no significa que no exista.

---

## Fuentes

| Fuente | Método | Volumen real | Estado |
|---|---|---|---|
| [Portal de Noticias del Gobierno de Canarias](https://www3.gobiernodecanarias.org/noticias/) | API REST de WordPress | ~15,6 entradas/día | Activa |
| [Consulta de iniciativas del Parlamento](https://www.parcan.es/iniciativas/) | Formulario POST + ficha de trámites | ~0,6 decisiones/día | Pendiente |
| [Noticias del Parlamento](https://www.parcan.es/noticias/) | HTML por año y mes | ~0,4 entradas/día | Secundaria |

El portal del Gobierno **no requiere scraping**: es una instalación de WordPress que expone
su API REST pública sin autenticación, con 41.223 entradas históricas, filtrado por fecha y
consejería y captura incremental mediante `modified_after`. Playwright queda como plan B
documentado en `src/transparencia_gobcan/extraccion/gobcan_html.py`, por si la API se cierra.

Para la actividad legislativa se usa el buscador de iniciativas, no el portal de noticias:
de 231 noticias analizadas del Parlamento en 19 meses, solo 3 citaban un grupo parlamentario.
El detalle está en [`docs/puntos-de-rotura.md`](docs/puntos-de-rotura.md).

Ambas fuentes son públicas. Se respetan sus `robots.txt`: en Parcan, `Crawl-delay: 3` y la
prohibición de sus endpoints `/api/`.

---

## Frecuencia de actualización

Cada **hora a y media, de 9:30 a 20:30 de lunes a viernes**, más un cierre a las 22:00 que
además recorre el Parlamento. Todo en hora canaria.

No es "tiempo real", y es deliberado: el portal publica en horario de oficina —el 86% de las
entradas entre las 09:00 y las 15:00, con el máximo a las 13:00— así que ejecutar de noche o
cada cinco minutos sería gasto sin retorno.

**El reloj no es el cron de GitHub, es `pg_cron` en Supabase.** Medido sobre cuatro días,
GitHub solo ejecutaba el 24% de los cron programados, y en la primera hora de la mañana
ninguno. La base llama a la API de GitHub para lanzar el workflow por `workflow_dispatch`,
que sí se ejecuta siempre. El detalle y la guía de diagnóstico están en
[`docs/programacion-fiable.md`](docs/programacion-fiable.md).

La carga histórica arranca en **mayo de 2023**, inicio de la XI legislatura y del propio
observatorio.

---

## Estructura

```
config/                 Vocabularios y parámetros versionados (no hay constantes en el código)
  areas.yaml              Áreas, correspondencias por legislatura y grupos parlamentarios
  alertas.yaml            Capa semántica: actos, materias y entidades
  territorio.yaml         Las 8 islas y los 88 municipios
  fuentes.yaml            Endpoints, selectores, cadencia y condiciones de uso
src/transparencia_gobcan/
  extraccion/             Obtención de datos crudos
  transformacion/         Normalización, derivación y validación
  carga/                  Escritura en Supabase y registro de ejecuciones
  alertas/                Clasificación semántica
  modelos.py              Modelo de datos (pydantic)
  cli.py                  Punto de entrada único
migraciones/            SQL versionado del schema transp_gobcan
tests/                  Pruebas, con fixtures capturados de las fuentes reales
visualizacion/          Interfaz de consulta en D3
docs/                   Reconocimiento, puntos de rotura, vigilancia y programación
```

La separación entre extracción, transformación, carga y visualización es explícita: cada
capa se puede sustituir sin tocar las demás. Si la API de Gobcan se cierra, solo cambia
`extraccion/`.

---

## Modelo de datos

Schema `transp_gobcan` en Supabase, con dos tablas desnormalizadas para consumo directo
desde la interfaz:

- **`entradas`** — una fila por publicación. `hash_dedup` es la clave de conflicto del
  `UPSERT`, lo que hace el pipeline idempotente: reejecutarlo actualiza, nunca duplica.
- **`logs_ejecucion`** — una fila por ejecución. Guarda el **motivo** de cada descarte y
  las anomalías detectadas, no solo el recuento de filas: la tabla existe para aprender de
  los fallos del extractor.

Tres campos merecen explicación porque no son evidentes:

- `area` **nunca es nulo**. Hay un valor residual explícito (`sin_asignar`) porque el 14%
  de las entradas útiles no trae consejería, y un `NULL` silencioso las dejaría invisibles
  ante cualquier filtro.
- `territorio_origen` distingue un territorio publicado por la fuente de una inferencia
  nuestra sobre el texto. Una inferencia no puede presentarse como si fuera un dato.
- `entrada_origen` registra de qué nivel de la cascada salió la entradilla. Su distribución
  avisa de que el gabinete ha cambiado de práctica editorial antes de que se note en los datos.

La nomenclatura de áreas sigue la de las secciones presupuestarias / consejerías, la misma
que la herramienta de cargos políticos (`cargos_publicos.cp_altos_cargos.area`). No se usa
clasificación libre: el vocabulario está cerrado en `config/areas.yaml`, con vigencia
temporal, porque la fuente cambia de nomenclatura cada legislatura.

---

## Puesta en marcha

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env    # y rellenar las credenciales
```

Las credenciales de Supabase y de correo van en `.env` en local y en GitHub Secrets en
producción. **Nunca en el repositorio.**

El plan B con navegador solo se instala si hace falta:

```bash
pip install -e ".[respaldo]" && playwright install chromium
```

### Si el proyecto vive en una carpeta sincronizada con iCloud

En macOS, iCloud Drive marca los ficheros `.pth` del entorno virtual con el
atributo `hidden`, y Python 3.11 y posteriores **ignoran deliberadamente** los
`.pth` ocultos. El resultado es un `ModuleNotFoundError: No module named
'transparencia_gobcan'` justo después de una instalación que ha ido bien.

No afecta a GitHub Actions ni a ningún entorno que no esté sincronizado. En
local, lo más limpio es crear el entorno virtual fuera de la carpeta
sincronizada:

```bash
python3 -m venv ~/.venvs/transparencia-gobcan && source ~/.venvs/transparencia-gobcan/bin/activate
```

Si prefieres mantenerlo dentro, se puede ejecutar así, que no depende del `.pth`:

```bash
PYTHONPATH=src python -m transparencia_gobcan.cli extraer --simular
```

---

## Ejecución

```bash
transparencia validar-config                          # coherencia de los vocabularios
transparencia probar-conexion                         # las credenciales llegan a la base
transparencia extraer --modo incremental              # pasada normal del Gobierno
transparencia extraer --modo historico --desde 2023-05-01
transparencia extraer --simular                       # extrae y valida, sin cargar
transparencia extraer --fuente parcan                 # iniciativas del Parlamento
transparencia extraer --fuente parcan --desde-cache   # reintenta solo la carga
transparencia clasificar --recalcular                 # tras ampliar config/alertas.yaml
transparencia notificar --simular                     # genera el aviso a fichero
transparencia notificar                               # envía el aviso por correo
transparencia notificar --marcar-historico            # sella lo viejo sin enviar
```

### Alertas por correo

Se avisa de las decisiones detectadas, no de todo lo capturado: unas dos al día
según lo medido sobre tres años. El correo lleva el título, quién impulsa la
medida —la consejería en el Gobierno, el grupo proponente en el Parlamento—, un
resumen breve y las áreas afectadas.

El envío usa el SMTP de Google Workspace, que es quien gestiona el correo de
`odesocan.org`. Hace falta una **contraseña de aplicación**, no la de la cuenta:
se genera en <https://myaccount.google.com/apppasswords> y requiere tener la
verificación en dos pasos activada.

`notificada_en` se sella tras cada envío, así que reejecutar el comando no
repite avisos. Antes del primer envío en producción conviene ejecutar
`notificar --marcar-historico`, que sella todo lo anterior a `ALERTAS_DESDE`
sin mandar nada: si no, el primer correo intentaría notificar tres años de
golpe.

Sobre permisos: no es comunicación comercial sino interna, entre buzones del
propio dominio y con contenido público, así que no requiere consentimiento
previo. Sí conviene avisar al equipo y ofrecer forma de darse de baja, que el
pie del correo indica.

Pruebas:

```bash
pytest
```

Los fixtures son respuestas reales capturadas de las fuentes, no datos inventados, para que
las pruebas cubran las rarezas que las fuentes tienen de verdad.

---

## Mantenimiento

El pipeline se rompe cuando la fuente cambia, y la fuente cambia. Lo previsible está
documentado en [`docs/puntos-de-rotura.md`](docs/puntos-de-rotura.md).

**Cómo se programa la ejecución y por qué no con el cron de GitHub**, en
[`docs/programacion-fiable.md`](docs/programacion-fiable.md). Incluye la guía de
diagnóstico del token, que ahorra horas.

**Qué mirar cada semana, y qué ha fallado ya**, en
[`docs/vigilancia.md`](docs/vigilancia.md). Los fallos que hemos tenido hasta ahora
comparten una característica incómoda: el workflow decía «success», los logs no
registraban ninguna anomalía, y aun así el sistema no hacía su trabajo. Merece la
pena leerlo antes de fiarse del verde.

Las señales de que el extractor se está degradando **sin fallar** se vigilan desde la tabla
de logs: caída del porcentaje de entradillas obtenidas del sumario, subida de las entradas
con área `sin_asignar`, volumen diario muy por debajo de las ~15 entradas esperadas, o
categorías nuevas sin correspondencia en la configuración. Un extractor roto rara vez lanza
una excepción: sigue devolviendo filas, solo que peores.

---

## Licencia y créditos

ODESOCAN · Observatorio de Derechos Sociales de Canarias
Calle los Dragos, 45, 3ª planta · 35118 Agüimes, Las Palmas
[info@odesocan.org](mailto:info@odesocan.org)

Código bajo GPL-3.0-or-later. Los datos proceden de fuentes públicas de la Administración
autonómica y conservan su carácter público.
