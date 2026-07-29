# Puntos de rotura previsibles

Registro de las fragilidades conocidas de cada fuente, con lo que hay que hacer cuando se
rompan. Levantado durante el reconocimiento del 27 de julio de 2026 (ver
[`informe-hito1-reconocimiento-fuentes.html`](informe-hito1-reconocimiento-fuentes.html)).

Este documento es para quien mantenga el pipeline dentro de un año, que probablemente no
sea quien lo escribió.

---

## 1. Portal del Gobierno de Canarias

### 1.1 La API REST podría cerrarse

**Riesgo:** medio. **Impacto:** alto.

El portal es WordPress y expone `/noticias/wp-json/wp/v2/` sin autenticación. Es la vía
principal de extracción. Cerrar la API REST a peticiones anónimas es una medida de
seguridad habitual: podría hacerse en cualquier actualización sin previo aviso.

**Síntoma:** respuestas `401` o `403` donde antes había `200`.

**Qué hacer:** activar el plan B (`extraccion/gobcan_html.py`, `metodo_respaldo: html` en
`config/fuentes.yaml`). El contenido es server-side, así que basta `httpx` más
BeautifulSoup; Playwright solo haría falta si además añadieran una capa de JavaScript.
Antes de nada, comprobar si el feed RSS `/noticias/feed/` sigue abierto: no trae áreas,
pero sirve para no perder entradas mientras se adapta el extractor.

### 1.2 Selectores del HTML que cambian de comportamiento según la vista

**Riesgo:** alto si se usa el plan B. **Impacto:** silencioso, que es lo peor.

Verificado el 27/07/2026 sobre la portada y sobre `/category/consejerias/sanidad/`:

| Selector | Comportamiento | Fiabilidad |
|---|---|---|
| `article` | 19 nodos en portada, 10 en vista de categoría | Alta |
| `.article-title` | Título, estable en ambas vistas | Alta |
| `.article-excerpt` | **Solo existe en la portada.** En categoría devuelve vacío | Baja |
| `.article-date` | Solo se pinta en la primera entrada de cada grupo de fecha | Baja |
| `.article-cat` | Concatena las dos nomenclaturas con duplicados: «Hospitales, Hospitales, Sanidad, Sanidad» | Media |
| `article a` | **Trampa:** el primer enlace apunta a la categoría, no a la noticia. Usar `.article-title a` | Baja |

Paginación: `/category/{slug}/page/{n}/`, 10 entradas por página, `404` al pasarse del
final, que es la condición de parada.

### 1.3 Cambio de nomenclatura de consejerías

**Riesgo:** cierto, en cada cambio de gobierno. **Impacto:** parte la serie histórica.

Ya conviven dos generaciones: las consejerías de la XI legislatura cuelgan de la categoría
`Consejerías` (id 125) y las de la X siguen en las categorías raíz. Por eso
`config/areas.yaml` es una tabla de correspondencias con vigencia temporal, no una lista.

**Síntoma:** subida del porcentaje de entradas con área `sin_asignar` en la tabla de logs.

**Qué hacer:** añadir las correspondencias nuevas a `config/areas.yaml` con
`vigencia_desde`, **sin borrar las anteriores**. Borrarlas rompería retroactivamente las
consultas sobre el histórico.

### 1.4 El gabinete deja de usar el `<blockquote>` de sumario

**Riesgo:** bajo. **Impacto:** medio, degrada la calidad de la entradilla.

La entradilla buena sale del `<blockquote>` de apertura del cuerpo. Aparece en torno a la
mitad de las entradas. Si el gabinete cambia de plantilla, la cascada cae al segundo nivel
(primer párrafo) y las entradillas empeoran sin que nada falle.

**Síntoma:** caída del porcentaje de `entrada_origen = 'sumario'` en
`logs_ejecucion.entradillas_por_origen`.

**Qué hacer:** inspeccionar el HTML de varias entradas recientes y ajustar
`transformacion/entradilla.py`.

### 1.5 Categorías de ruido que cambian de identificador

**Riesgo:** bajo. **Impacto:** el volumen se triplica y las alertas se inundan.

Se excluyen en origen `Incidentes 112` (id 44) y `Alertas` (id 24), que son el 31% de lo
publicado y no son actividad ejecutiva. Si esos ids cambian, vuelven a entrar.

**Síntoma:** salto del volumen diario de ~15 a ~17 y aparición de titulares de sucesos.

---

## 2. Parlamento de Canarias

### 2.1 `/noticias/` no sirve para seguimiento legislativo

Esto no es una rotura futura: es una limitación presente, y la razón de que la fuente
principal de actividad parlamentaria sea `/iniciativas/`.

De **231 noticias** analizadas entre enero de 2025 y julio de 2026, solo **3 mencionan un
grupo parlamentario** (1,3%). Las ocho noticias muestreadas individualmente tenían el mismo
valor en el campo *Fuente*: «Presidencia», el gabinete de comunicación de la Cámara. El
contenido son iluminaciones de fachada por días conmemorativos, homenajes, visitas
institucionales y videopodcasts.

Consecuencia: desde esta URL no son alcanzables el filtro por grupo proponente ni el caso
de uso de votaciones. Se conserva como fuente secundaria de actos institucionales.

### 2.2 Formato de fecha con mes abreviado en español

**Riesgo:** cierto si se usa `strptime` con el locale del sistema. **Impacto:** alto.

Parcan escribe las fechas como `24/jul/2026`. Resolverlo con `locale.setlocale(LC_TIME,
'es_ES')` funciona en un portátil español y **falla en el runner de GitHub Actions**, que
arranca en inglés y puede no tener el locale instalado.

**Qué hacer:** mapeo explícito de los doce meses en el código. Nunca depender del locale.

### 2.3 El buscador de iniciativas es un formulario POST, no una API

**Riesgo:** medio. **Impacto:** alto.

`/iniciativas/index.py` acepta `POST` con `LEGIS`, `TIPO`, `PROPONENTE`, `SITUACION` y
`rango`. No es un contrato público: los nombres de campo pueden cambiar en cualquier
rediseño.

A favor: el listado delimita cada resultado con comentarios HTML explícitos
(`<!-- RESULT ITEM START -->`), que alguien puso a propósito y son un ancla más estable que
las clases CSS. Y el código de iniciativa (`11L/PNLP-0001`) es parlante y estable, lo que da
una clave de deduplicación fiable.

**Cuidado con el volumen:** 7.627 iniciativas en la XI legislatura, de las que 4.927 son
preguntas orales y escritas. El anillo de decisiones (PL, PPL, DL, DLG, PNLP, PNLC, M, CG)
son 679, y solo esas necesitan visita a la ficha de trámites. A 3 segundos por petición son
unos 34 minutos de carga histórica, una sola vez.

### 2.4 `robots.txt` con `Crawl-delay: 3`

No es una rotura, es una condición de uso que hay que respetar. Su `robots.txt` también
prohíbe `/api/` y `/api2/`: **no se usan**, aunque técnicamente respondan. El sitemap que
declara devuelve `404`.

---

## 3. Señales de degradación silenciosa

> Las consultas concretas para revisarlas, y el registro de los fallos que ya
> han ocurrido, están en [`vigilancia.md`](vigilancia.md).

Un extractor roto rara vez lanza una excepción: sigue devolviendo filas, solo que peores.
Estas son las señales que hay que vigilar desde `transp_gobcan.logs_ejecucion`, y que
`transformacion/validacion.py` debe convertir en anomalías registradas:

| Señal | Umbral orientativo | Qué suele significar |
|---|---|---|
| Volumen diario | por debajo de 8 en día laborable | La paginación se corta antes de tiempo |
| `entrada_origen = 'sumario'` | por debajo del 30% | Cambió la plantilla editorial |
| `area = 'sin_asignar'` | por encima del 20% | Cambió la nomenclatura de consejerías |
| Categorías sin correspondencia | cualquiera | Consejería nueva o renombrada |
| Entradillas descartadas por vacías | por encima del 5% | Cambió la estructura del cuerpo |

Los umbrales son orientativos y conviene revisarlos con unos meses de histórico: se han
fijado sobre una ventana de tres meses, que no cubre agosto ni el periodo de presupuestos.
