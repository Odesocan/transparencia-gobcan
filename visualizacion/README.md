# Interfaz de consulta

Buscador sobre las publicaciones capturadas del Gobierno y el Parlamento de
Canarias. Cubre el caso de uso 2 de la guía metodológica y lo amplía: búsqueda
por palabra clave, filtro temporal, filtro por ente —consejería en el Gobierno,
grupo parlamentario en el Parlamento—, filtro por área temática con etiquetas
que se solapan, y resultados paginados.

## Cómo se abre

En **local**, basta con abrir `index.html` en el navegador. No hace falta
servidor ni conexión: los ficheros van juntos y se leen desde disco.

```
index.html                la interfaz
datos.js                  el volcado, que regenera `transparencia exportar`
d3.v7.min.js              D3 servido en local, sin CDN
fuentes.css + fuentes/    las tipografías, también en local
```

En **producción** vive en GitHub Pages y se publica sola. El detalle está más
abajo, en «Cómo se publica».

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

## Qué se puede filtrar

| Filtro | Cómo se usa | De dónde sale el dato |
|---|---|---|
| **Fuente** | Conmutador Gobierno / Parlamento | `fuente` |
| **Palabra clave** | Todas las palabras deben aparecer | título y entradilla |
| **Periodo** | Atajos, fechas exactas, o directamente sobre el gráfico | `fecha_real` |
| **Ente** | Varias a la vez, con recuento | `area` o `grupo_parlamentario` |
| **Área temática** | Varias a la vez, con «cualquiera» o «todas» | `etiquetas`, derivadas al exportar |
| **Solo decisiones** | Conmutador | `es_alerta` |

## Por qué lee un fichero y no la base

La alternativa era que el navegador hablase directamente con Supabase, lo que
obligaría a exponer el schema por PostgREST y a escribir políticas de lectura
pública sobre una tabla que hoy solo toca la clave de servicio. Para esta
herramienta no compensa: un fichero estático se despliega igual en local que en
Pages o empotrado en la web, y no abre la base a nadie.

El volcado se regenera con:

```bash
transparencia exportar
```

`datos.js` **no está en el repositorio**: son 8 MB que cambian en cada ejecución
y lo engordarían muy rápido. Hay tres formas de conseguirlo:

- **En producción** no hace falta: el workflow de publicación lo regenera en
  cada despliegue.
- **En local**, ejecutando el comando de arriba con las credenciales en `.env`.
- **Desde GitHub**, descargando el artefacto `datos-interfaz` de la última
  ejecución en la pestaña Actions. Se conserva catorce días y no hace falta
  tener acceso a la base.

Pesa unos 8 MB porque lleva las 16.000 entradas con su entradilla. El formato es
columnar —una lista de campos y filas como arrays, con catálogos para las áreas,
los grupos, los territorios y las etiquetas— lo que lo deja en la mitad de lo
que ocuparía como lista de objetos. Servido con compresión son unos 2 MB.

Si algún día crece mucho, lo siguiente sería partirlo por año y cargar bajo
demanda. Hoy no hace falta.

## Cómo se publica

`.github/workflows/pages.yml` regenera el volcado contra la base y sube la
carpeta entera a GitHub Pages. Se dispara después de cada extracción que termine
bien —unas once veces al día entre semana—, en cada `push` a `main` que toque la
interfaz o el vocabulario, y a mano desde la pestaña Actions.

Antes de publicar comprueba tres cosas, porque las tres fallan **sin dar error**
y dejan una página que abre perfectamente y no sirve para nada:

- que la configuración sea coherente, con `transparencia validar-config`;
- que el volcado traiga más de mil filas, no un resultado a medias;
- que las etiquetas cubran al menos la mitad del archivo. Si la fuente cambia de
  vocabulario editorial, los patrones dejan de casar y el filtro por área se
  queda vacío sin que nada se rompa.

**La página es pública.** El repositorio lo es, la organización está en el plan
gratuito y GitHub Pages no ofrece sitios privados ahí. Lo que se publica son
títulos, entradillas y metadatos de dos portales de comunicación institucional
públicos, que conservan su carácter público, pero conviene saber que publicarlo
convierte una herramienta interna en un sitio abierto. Las credenciales no salen
del runner: lo que se sube es un fichero de datos ya cocinado.

## Decisiones de diseño que no son evidentes

**Las etiquetas temáticas no son las materias del clasificador de alertas.** Se
parecen y hacen cosas opuestas. El vocabulario de alertas decide qué se notifica
por correo y tiene que ser estrecho: está calibrado para 1,9 avisos al día y
cada término de más son correos de más. Este decide cómo se recorren 16.000
entradas y tiene que ser ancho, porque una entrada sin etiquetar es una entrada
invisible. Medido sobre el volcado de julio de 2026, el vocabulario de alertas
dejaba **8.855 entradas de 16.044 —el 55%— sin ninguna materia**: como taxonomía
de navegación era inservible. El vocabulario propio, en
`config/etiquetas_tematicas.yaml`, cubre el 81%.

**Las etiquetas se calculan al exportar, no al cargar.** Así ampliar el
vocabulario no obliga a recalcular la tabla entera ni cambia el volumen de
correo: se reexporta y la interfaz lo recoge. Cuesta un segundo sobre 16.000
textos.

**Una entrada lleva varias etiquetas a la vez, y eso es el punto.** «Cuatro
millones para viviendas adaptadas a personas con discapacidad» es vivienda Y
discapacidad, y sale en los dos filtros. Por eso el campo es una lista, los
marcadores son una nube y no un desplegable —un desplegable sugeriría que hay
que elegir uno— y hay un conmutador entre «cualquiera» y «todas».

**Los recuentos de la nube se calculan sobre lo ya filtrado por lo demás.** Si
dijeran el total del archivo, mentirían. Y en modo «todas» se calculan sobre el
resultado, no ignorando lo marcado: de lo contrario un área diría 229 cuando
cruzarla con las otras deja tres, y el número invitaría a un callejón sin salida.

**Las nueve áreas de contexto van en gris y plegadas.** Están porque sin ellas el
39% del archivo no se podía recorrer, no porque tengan el mismo peso que las que
el observatorio vigila. El color queda para los derechos sociales, así que la
jerarquía se lee sin tener que leer los nombres.

**Los grupos parlamentarios se parten al cargar.** La fuente los entrega como una
cadena con todos los proponentes: «GP Socialista Canario, GP Popular, …». Como
catálogo eran 12 combinaciones y no 7 grupos, así que filtrar por «GP Popular»
dejaba fuera todo lo que el PP firma con otro. Una vez partidos, el filtro
devuelve las 109 iniciativas que el PP ha firmado, no solo las que llevan su
nombre a solas.

**El gráfico es un control, no solo una salida.** Pulsar un mes lo acota;
arrastrar selecciona un tramo. Es la forma más directa de filtrar por fecha,
porque se elige mirando dónde hay actividad en vez de teclear dos fechas a
ciegas. El pincel va encima de las barras y les tapa el puntero, así que el
resaltado y el tooltip se calculan desde su propia capa: una sola superficie
atiende pasar por encima, pulsar y arrastrar.

**El gráfico se recalcula sobre el resultado filtrado.** No es un adorno: el
Gobierno publica unas veintitrés veces más que el Parlamento, y en un eje
compartido la serie del Parlamento sería una línea invisible. Al filtrar por
fuente el eje se reescala y pasa a leerse bien. Es la forma de resolver el
problema de escala sin recurrir a un doble eje, que deforma las proporciones.

**El eje escribe el año en la primera etiqueta de cada año.** La serie arranca en
mayo de 2023 y se etiqueta un mes de cada tres, así que los eneros nunca caen en
un múltiplo de tres: sin esto el eje decía «may ago nov feb may…» y no había
manera de saber de qué año era cada barra.

**Los filtros viajan en la dirección.** Una consulta se puede pegar en un correo
o citar en un informe, y quien la abra ve exactamente lo mismo. En una
herramienta de fiscalización eso no es comodidad: es que el dato sea verificable
por otra persona. También se atiende el `hashchange`, porque pegar un enlace en
una pestaña ya abierta no recarga la página.

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

**Las ocho familias de color de las etiquetas están verificadas a 4,5:1**, el
mínimo de WCAG AA para texto pequeño, sobre su propio fondo y en los dos temas.
El teal corporativo no llegaba —3,0:1 sobre `#E0FAF7`— así que el distintivo usa
`#007A6E` solo para el texto.

Todo el tema vive en variables CSS y el gráfico lee de ellas sus colores, así
que no hay dos definiciones que puedan desincronizarse.

**El conmutador es Gobierno o Parlamento, sin opción «Todo».** Además de ser lo
pedido, resuelve un problema de escala: el Gobierno publica veintitrés veces más
que el Parlamento y, juntos en un mismo eje, la serie del Parlamento quedaba en
una franja de un píxel. Con una sola fuente activa el gráfico tiene una serie, el
eje se ajusta a ella y la leyenda sobra, porque el título nombra la fuente.

## Ampliar el vocabulario de áreas

Se edita `config/etiquetas_tematicas.yaml` y se reexporta. No hace falta tocar
esta página: el volcado lleva el catálogo con su nombre, su grupo y su familia de
color, y la nube se pinta con lo que venga.

Tres avisos, los tres aprendidos aquí:

1. Los patrones se compilan con `re.VERBOSE`, así que **los espacios literales se
   ignoran**. Escribir `salud mental` en vez de `salud\s+mental` da un patrón que
   compila sin error y no encuentra nada.
2. El plural va como `natural(es)?`, nunca como `naturales?`, que significa
   «naturale» más una «s» opcional y no casa el singular.
3. **Comprobar que el patrón compila no basta.** Hay que mirar qué literal
   dispara y cuántas veces, sobre el corpus real. Tres patrones que parecían
   correctos casaban «Comunidad Autónoma» 326 veces en empleo, «Hospital
   Universitario» 388 veces en educación y «Unidad de Continuidad de Cuidados» en
   dependencia. `tests/test_config.py` los vigila término a término, y también
   los falsos amigos.

## Empotrarlo en otra web

Para llevarlo a un bloque de código de Divi hay que servir `datos.js`,
`d3.v7.min.js` y las tipografías desde una URL accesible —por ejemplo la carpeta
de medios de WordPress— y ajustar las rutas del final de `index.html`. El resto
del fichero se pega tal cual dentro del bloque.

Conviene comprobar antes que el servidor entrega el volcado con compresión: sin
ella son 8 MB por visita.
