# Interfaz de consulta

Buscador sobre las publicaciones capturadas del Gobierno y el Parlamento de
Canarias. Cubre el caso de uso 2 de la guía metodológica: búsqueda por fecha y
palabra clave, resultados paginados de diez en diez, conmutador entre Gobierno y
Parlamento, y filtro por área en el primero y por grupo parlamentario en el
segundo.

## Cómo se abre

Basta con abrir `index.html` en el navegador. No hace falta servidor ni conexión:
los tres ficheros van juntos y se leen desde disco.

```
index.html      la interfaz
datos.js        el volcado, que regenera `transparencia exportar`
d3.v7.min.js    D3 servido en local, sin CDN
fuentes.css     las tipografías, también en local
fuentes/        los .woff2 de Space Grotesk e Inter
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

Pesa unos 8 MB porque lleva las 16.000 entradas con su entradilla. El formato es
columnar —una lista de campos y filas como arrays, con catálogos para las áreas,
los grupos y los territorios— lo que lo deja en la mitad de lo que ocuparía como
lista de objetos. Servido con compresión son unos 2 MB.

Si algún día crece mucho, lo siguiente sería partirlo por año y cargar bajo
demanda. Hoy no hace falta.

## Decisiones de diseño que no son evidentes

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

## Empotrarlo en la web

Para llevarlo a un bloque de código de Divi hay que servir `datos.json` y
`d3.v7.min.js` desde una URL accesible —por ejemplo la carpeta de medios de
WordPress— y ajustar las dos rutas del final de `index.html`. El resto del
fichero se pega tal cual dentro del bloque.

Conviene comprobar antes que el servidor entrega el JSON con compresión: sin
ella son 8 MB por visita.
