"""Extractor principal del portal de noticias del Gobierno de Canarias.

El portal es una instalación de WordPress que expone su API REST pública sin
autenticación, así que no hace falta scraping: una petición HTTP devuelve los
datos ya estructurados. Ver `gobcan_html.py` para el plan B con navegador.

Medido el 27/07/2026: 12 peticiones consecutivas sin pausa, todas 200, con una
latencia media de 0,57 s. No se detectó limitación de tasa, pero se mantiene una
pausa corta entre páginas por cortesía con una fuente pública.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import httpx
from tenacity import RetryCallState, retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import cargar

log = logging.getLogger(__name__)

# Identificamos al agente: la fuente es pública, pero conviene que sepan quién
# consulta y a dónde escribir si algo molesta.
AGENTE = (
    "ODESOCAN-transparencia-gobcan/0.1 "
    "(+https://odesocan.org; investigacion@odesocan.org)"
)
PAUSA_ENTRE_PAGINAS_S = 0.3

# Cuánto cuerpo se enseña en el mensaje de error. Suficiente para reconocer una
# página de mantenimiento o un aviso de PHP, sin volcar 200 KB al log de Actions.
MUESTRA_CUERPO = 200


class RespuestaIlegible(Exception):
    """Un `200 OK` cuyo cuerpo no es la lista JSON que la API promete.

    Ocurrido el 11/08/2026: la primera petición de categorías devolvió 200 con
    el cuerpo vacío y la ejecución entera se cayó con un `JSONDecodeError` a
    secas, sin reintentar y sin decir qué había respondido la fuente.

    Tiene clase propia por las dos cosas: para que el reintento la cubra —un
    cuerpo vacío con código 200 es un tropiezo pasajero del servidor, no un
    dato— y para que el mensaje diga qué llegó de verdad.
    """


def _cfg() -> dict:
    return cargar("fuentes")["fuentes"]["gobcan"]


def _cliente() -> httpx.Client:
    api = _cfg()["api"]
    return httpx.Client(
        headers={"User-Agent": AGENTE, "Accept": "application/json"},
        timeout=api["tiempo_espera_s"],
        follow_redirects=True,
    )


def _leer_lista(respuesta: httpx.Response) -> list[dict[str, Any]]:
    """Convierte la respuesta en la lista de registros, o explica por qué no puede.

    La API siempre devuelve una lista en el camino feliz. Cualquier otra cosa
    con código 200 —cuerpo vacío, HTML de una página de error, un objeto de
    error de WordPress— es una respuesta que no sirve, y conviene distinguirla
    de la lista vacía legítima que marca el final de la paginación.
    """
    try:
        datos = respuesta.json()
    except ValueError as e:
        cuerpo = respuesta.text
        detalle = (
            "cuerpo vacío" if not cuerpo.strip()
            else f"empieza por {cuerpo[:MUESTRA_CUERPO]!r}"
        )
        raise RespuestaIlegible(
            f"{respuesta.status_code} en {respuesta.url} con "
            f"Content-Type {respuesta.headers.get('content-type', '(ninguno)')!r} "
            f"y {len(respuesta.content)} bytes: {detalle}"
        ) from e

    if not isinstance(datos, list):
        raise RespuestaIlegible(
            f"{respuesta.status_code} en {respuesta.url}: se esperaba una lista y "
            f"ha llegado {type(datos).__name__}: {str(datos)[:MUESTRA_CUERPO]}"
        )
    return datos


def _avisar_reintento(estado: RetryCallState) -> None:
    """Deja constancia de cada reintento: si no, un fallo pasajero es invisible."""
    error = estado.outcome.exception() if estado.outcome else None
    log.warning(
        "La fuente ha fallado (intento %d): %s: %s. Reintentando en %.0f s",
        estado.attempt_number,
        type(error).__name__,
        error,
        estado.next_action.sleep if estado.next_action else 0,
    )


@retry(
    retry=retry_if_exception_type(
        (httpx.TransportError, httpx.HTTPStatusError, RespuestaIlegible)
    ),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, min=5, max=30),
    before_sleep=_avisar_reintento,
    reraise=True,
)
def _pedir(cliente: httpx.Client, url: str, parametros: dict) -> tuple[httpx.Response, list | None]:
    """Lanza una petición con reintentos y devuelve la respuesta ya interpretada.

    El JSON se lee aquí dentro a propósito. Hacerlo fuera dejaba el `.json()`
    fuera del alcance del reintento: un `200` con el cuerpo vacío —que pasa, y
    ha pasado— tumbaba la ejecución entera en la primera petición en lugar de
    reintentarse como el fallo pasajero que es.

    Pasarse de la última página devuelve 400 o 404: es la condición de parada
    normal de la paginación, no un error, así que no se reintenta ni se lee el
    cuerpo. Se devuelve `None` para que quien llama lo distinga de una página
    legítimamente vacía.
    """
    respuesta = cliente.get(url, params=parametros)
    if respuesta.status_code in (400, 404):
        return respuesta, None
    respuesta.raise_for_status()
    return respuesta, _leer_lista(respuesta)


def descargar_categorias() -> dict[int, dict[str, Any]]:
    """Descarga la taxonomía completa de categorías del portal.

    Devuelve un mapa id -> {"nombre", "parent"}. El `parent` importa: sin él no
    se puede distinguir una subcategoría esperada (Hospitales, cuelga de
    Sanidad) de una consejería nueva que sí habría que añadir a la
    configuración, y la detección de anomalías se llena de falsos positivos.
    """
    api = _cfg()["api"]
    catalogo: dict[int, dict[str, Any]] = {}
    with _cliente() as cliente:
        pagina = 1
        while True:
            _, datos = _pedir(
                cliente,
                api["endpoint_categorias"],
                {"per_page": 100, "page": pagina, "_fields": "id,name,slug,parent,count"},
            )
            if not datos:
                break
            catalogo.update(
                {c["id"]: {"nombre": c["name"], "parent": c.get("parent", 0)} for c in datos}
            )
            if len(datos) < 100:
                break
            pagina += 1
            time.sleep(PAUSA_ENTRE_PAGINAS_S)

    # Sin catálogo no se puede asignar área ni detectar categorías nuevas: la
    # extracción seguiría adelante y dejaría todo en `sin_asignar` sin que nada
    # se pusiera en rojo. Mejor parar; la siguiente ejecución reintenta y el
    # UPSERT es idempotente, así que no se pierde nada.
    if not catalogo:
        raise RespuestaIlegible(
            "La fuente ha devuelto un catálogo de categorías vacío. Son 168 y no "
            "pueden desaparecer: revisa si la API REST sigue abierta "
            "(ver docs/puntos-de-rotura.md, 1.1)."
        )

    log.info("Categorías descargadas: %d", len(catalogo))
    return catalogo


def descargar_entradas(
    desde: datetime | None = None,
    hasta: datetime | None = None,
    incremental: bool = True,
) -> Iterator[dict[str, Any]]:
    """Recorre las entradas del portal y las va devolviendo de una en una.

    Args:
        desde: límite inferior. En modo incremental se aplica sobre la fecha de
            modificación, para recoger también entradas editadas tras publicarse.
        hasta: límite superior, para acotar la carga histórica por tramos.
        incremental: si es True usa `modified_after`; si no, `after`/`before`.

    Devuelve los registros crudos de la API. La normalización es cosa de la capa
    de transformación.
    """
    api = _cfg()["api"]
    excluidas = [str(c["id"]) for c in cargar("areas")["categorias_excluidas"]]

    parametros: dict[str, Any] = {
        "per_page": api["por_pagina"],
        "orderby": "date",
        "order": "desc",
        "_fields": ",".join(api["campos"]),
        # Excluimos el 112 y los avisos en origen: son el 31% de lo publicado y
        # no son actividad ejecutiva. Así ni siquiera se descargan.
        "categories_exclude": ",".join(excluidas),
    }
    if desde:
        clave = api["parametro_incremental"] if incremental else "after"
        parametros[clave] = desde.strftime("%Y-%m-%dT%H:%M:%S")
    if hasta:
        parametros["before"] = hasta.strftime("%Y-%m-%dT%H:%M:%S")

    with _cliente() as cliente:
        pagina, total_declarado = 1, None
        while True:
            respuesta, datos = _pedir(cliente, api["endpoint_posts"], {**parametros, "page": pagina})
            if not datos:
                break

            if total_declarado is None:
                total_declarado = respuesta.headers.get("X-WP-Total")
                log.info("La fuente declara %s entradas para esta consulta", total_declarado)

            yield from datos

            if len(datos) < api["por_pagina"]:
                break
            pagina += 1
            time.sleep(PAUSA_ENTRE_PAGINAS_S)
