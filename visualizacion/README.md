# Interfaz de consulta

Buscador sobre las publicaciones capturadas del Gobierno y el Parlamento de
Canarias. Cubre el caso de uso 2 de la guía metodológica —búsqueda por fecha y
palabra clave, resultados paginados de diez en diez, conmutador entre Gobierno y
Parlamento— y lo amplía a una navegación facetada por todo lo que genera el
pipeline:

| Filtro | Gobierno | Parlamento |
|---|---|---|
| Palabra clave (todas las palabras, sin tildes) | ✓ | ✓ |
| Rango de fechas, o un mes con clic en el gráfico 1 | ✓ | ✓ |
| Solo decisiones (capa de alertas) | ✓ | ✓ |
| Área · consejería | ✓ | ✓ (por comisión) |
| Materia de derechos sociales | ✓ | ✓ |
| Isla y municipio | ✓ | ✓ |
| Grupo proponente | | ✓ |
| Tipo de iniciativa | | ✓ |
| Situación de la tramitación | | ✓ |

Cada opción muestra cuántas publicaciones quedarían al marcarla. El gráfico 2
reparte el resultado por área, grupo, materia o isla, y un clic en una barra
filtra por ella. Desde cada tarjeta se puede filtrar también por su área, su
grupo, su territorio, su tipo o sus materias.

El estado de los filtros vive en la URL (`#f=1&mat=vivienda&isla=Lanzarote`),
así que cualquier vista se comparte con su enlace. El resultado filtrado
completo se descarga en CSV.

## Dónde se ve

**En la web**, en GitHub Pages: <https://odesocan.github.io/transparencia-gobcan/>.
Se republica sola tras cada extracción correcta (ver más abajo).

**En local**, basta con abrir `index.html` en el navegador. No hace falta
servidor ni conexión: los ficheros van juntos y se leen desde disco.

```
index.html                la página: cabecera, tema y carga de scripts
app.js                    la aplicación en React, con los gráficos en D3
estilos.css               identidad ODESOCAN y modo oscuro, en variables CSS
datos.js                  el volcado, que regenera `transparencia exportar`
d3.v7.min.js              D3, servido en local, sin CDN
react-18.3.1.min.js       React (UMD), en local
react-dom-18.3.1.min.js   ReactDOM (UMD), en local
htm-3.1.1.min.js          plantillas tipo JSX sin compilación
fuentes.css, fuentes/     Space Grotesk e Inter, en local
```

Nada sale a internet, y eso importa por dos motivos distintos.

El primero es de velocidad: las tipografías venían de Google Fonts, y ese
`<link>` **bloquea el pintado**: hasta que Google responde, el navegador no
muestra nada.

El segundo es que **Chrome bloquea `fetch()` desde `file://`**. Al abrir la
página con doble clic, cualquier petición —aunque sea a un fichero de al lado—
falla con *«Cross origin requests are only supported for protocol schemes:
http, https…»*. Por eso el volcado es un `.js` que declara una variable global
en vez de un `.json` que haya que ir a buscar: los `<script src>` no están
sujetos a esa restricción. Por HTTP funciona exactamente igual, así que no hay
que mantener dos versiones.

## Por qué React sin compilación

React gobierna el estado y el DOM; D3 dibuja los dos gráficos dentro de un
contenedor que React le cede, así que ninguno pisa al otro.

No hay Vite ni Babel porque la página se tiene que poder abrir con doble clic, y
**Chrome bloquea los módulos ES desde `file://`** igual que bloquea `fetch()`.
Un build con `<script type="module">` rompería justo el uso principal. Por eso
React va en su versión UMD, que declara variables globales, y las plantillas se
escriben con [htm](https://github.com/developit/htm), que da una sintaxis casi
idéntica a JSX interpretada en el navegador (1 kB). Se queda en React 18 porque
React 19 ya no publica la versión UMD.

## Por qué lee un fichero y no la base

La alternativa era que el navegador hablase directamente con Supabase, lo que
obligaría a exponer el schema por PostgREST y a escribir políticas de lectura
pública sobre una tabla que hoy solo toca la clave de servicio. Para una
herramienta interna no compensa: un fichero estático se despliega igual en local
que empotrado en la web, y no abre la base a nadie.

El volcado se regenera con:

```bash
transparencia exportar
```

`datos.js` **no está en el repositorio**: son 8 MB que cambian en cada ejecución
y lo engordarían muy rápido. Hay tres formas de conseguirlo:

- **En local**, ejecutando el comando de arriba con las credenciales en `.env`.
- **Desde GitHub**, descargando el artefacto `datos-interfaz` de la última
  ejecución en la pestaña Actions. Se conserva catorce días y no hace falta
  tener acceso a la base.
- **Desde la web**: <https://odesocan.github.io/transparencia-gobcan/datos.js>.

Además del contenido, el volcado lleva lo que la interfaz necesita para
presentarlo: los nombres de las áreas y de los tipos de iniciativa, el mapa de
cada municipio a su isla y la hora de generación. Todo sale de `config/` y del
código del pipeline, así que no hay una segunda copia en la interfaz que pueda
desincronizarse.

Pesa unos 8 MB porque lleva las 16.000 entradas con su entradilla. El formato es
columnar —una lista de campos y filas como arrays, con catálogos para las áreas,
los grupos y los territorios— lo que lo deja en la mitad de lo que ocuparía como
lista de objetos. Servido con compresión son unos 2 MB.

La página pide `datos.js` después de pintar la cabecera, no con un `<script>`
fijo en el HTML: mientras llegan los 2 MB se ve un indicador de carga en vez de
una pantalla en blanco.

Si algún día crece mucho, lo siguiente sería partirlo por año y cargar bajo
demanda. Hoy no hace falta.

## Publicación en GitHub Pages

La publica `.github/workflows/pages.yml`, que regenera el volcado desde la base
y sube la carpeta con él dentro. El volcado nunca pasa por git. Se ejecuta:

- al terminar **bien** cada extracción, así que la web va como mucho una hora
  y media por detrás de la base en horario de oficina;
- al cambiar la interfaz o el exportador en `main`;
- a mano, desde la pestaña Actions.

**Activación, una sola vez**: Settings → Pages → Build and deployment →
Source: **GitHub Actions**. El `GITHUB_TOKEN` del workflow no tiene permiso
para activarlo por sí mismo, y sin ese paso el despliegue falla con un 404.

Conviene tener presente que **Pages es público**: cualquiera con el enlace ve la
interfaz y puede descargar `datos.js`. No expone nada que no lo esté ya —título,
entradilla y enlace de publicaciones institucionales públicas, más nuestras
clasificaciones—, pero deja de ser una herramienta solo interna.

## Decisiones de diseño que no son evidentes

**Los recuentos de cada filtro excluyen su propio filtro.** Es la convención de
la búsqueda facetada: al marcar «Sanidad» se siguen viendo las demás áreas con
su cifra, y se puede añadir otra. Las fechas se tratan igual, así que al elegir
un mes el gráfico 1 sigue mostrando los demás, apagados, y se puede saltar de
uno a otro. Se calcula todo en una sola pasada: una fila que solo falla en una
faceta suma únicamente para esa.

**Los filtros usan claves estables, no índices.** El volcado sustituye áreas y
tipos por su índice en un catálogo, pero ese índice cambia en cada volcado. La
URL guarda la clave (`obras_publicas`, `PNLP`), de modo que un enlace compartido
sigue funcionando al día siguiente.

**Las iniciativas conjuntas cuentan para cada grupo.** El Parlamento publica las
firmadas por varios grupos como una sola cadena; se separan al cargar, y filtrar
por un grupo incluye también lo que firmó con otros.

**El territorio se agrupa por isla.** El campo mezcla niveles —«Canarias», una
isla o un municipio—, así que filtrar por «Tenerife» a secas dejaría fuera lo de
La Orotava. El gráfico por isla no incluye lo autonómico: es más de la mitad de
todo y aplastaría la escala del resto; la nota al pie da la cifra.

**El gráfico se recalcula sobre el resultado filtrado.** No es un adorno: el
Gobierno publica unas veintitrés veces más que el Parlamento, y en un eje
compartido la serie del Parlamento sería una línea invisible. Al filtrar por
fuente el eje se reescala y pasa a leerse bien. Es la forma de resolver el
problema de escala sin recurrir a un doble eje, que deforma las proporciones.

**El eje escribe el año en la primera etiqueta de cada año.** La serie arranca en
mayo de 2023 y se etiqueta un mes de cada tres, así que los eneros nunca caen en
un múltiplo de tres: sin esto el eje decía «may ago nov feb may…» y no había
manera de saber de qué año era cada barra.

**El texto de búsqueda se normaliza una sola vez, al cargar.** Quitar tildes y
pasar a minúscula 16.000 títulos y entradillas en cada pulsación costaba 27 ms
por tecla; hecho de antemano, cada búsqueda son 9.

**El buscador exige todas las palabras.** Buscar «vivienda lanzarote» devuelve lo
que trata de ambas cosas, no todo lo de vivienda más todo lo de Lanzarote.

**El conmutador de tema recuerda la elección.** Mientras no se toque el botón
manda la preferencia del sistema; en cuanto se pulsa, gana lo elegido y se
guarda entre visitas. El atributo se fija en un script del `<head>`, antes del
primer pintado: si se pusiera más tarde, la página aparecería un instante en
claro y saltaría a oscuro.

**El modo oscuro tiene pasos propios, no es una inversión.** Sobre fondo oscuro
la banda de luminosidad válida es más estrecha y el teal corporativo se sale por
arriba, así que baja a `#00A896`. Los dos pares están verificados con el
validador de paleta: separación para daltonismo ΔE 20,2 en deuteranopia y
contraste por encima de 3:1 contra la superficie.

Todo el tema vive en variables CSS y el gráfico lee de ellas sus colores, así
que no hay dos definiciones que puedan desincronizarse.

**El conmutador es Gobierno o Parlamento, sin opción «Todo».** Además de ser lo
pedido, resuelve un problema de escala: el Gobierno publica veintitrés veces más
que el Parlamento y, juntos en un mismo eje, la serie del Parlamento quedaba en
una franja de un píxel. Con una sola fuente activa el gráfico tiene una serie,
el eje se ajusta a ella y la leyenda sobra, porque el título nombra la fuente.

## Empotrarlo en la web de ODESOCAN

Lo más sencillo es un `<iframe>` que apunte a la versión de GitHub Pages: se
actualiza sola y no hay que copiar nada a WordPress.

```html
<iframe src="https://odesocan.github.io/transparencia-gobcan/"
        style="width:100%;height:1400px;border:0" loading="lazy"
        title="Actividad ejecutiva y parlamentaria de Canarias"></iframe>
```

GitHub Pages ya entrega `datos.js` comprimido: unos 2 MB por visita en lugar
de 8.
