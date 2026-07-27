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
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import cargar

log = logging.getLogger(__name__)

# Identificamos al agente: la fuente es pública, pero conviene que sepan quién
# consulta y a dónde escribir si algo molesta.
AGENTE = (
    "ODESOCAN-transparencia-gobcan/0.1 "
    "(+https://odesocan.org; investigacion@odesocan.org)"
)
PAUSA_ENTRE_PAGINAS_S = 0.3


def _cfg() -> dict:
    return cargar("fuentes")["fuentes"]["gobcan"]


def _cliente() -> httpx.Client:
    api = _cfg()["api"]
    return httpx.Client(
        headers={"User-Agent": AGENTE, "Accept": "application/json"},
        timeout=api["tiempo_espera_s"],
        follow_redirects=True,
    )


@retry(
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, min=5, max=30),
    reraise=True,
)
def _pedir(cliente: httpx.Client, url: str, parametros: dict) -> httpx.Response:
    """Lanza una petición con reintentos y espera progresiva.

    Pasarse de la última página devuelve 400 o 404: es la condición de parada
    normal de la paginación, no un error, así que no se reintenta.
    """
    respuesta = cliente.get(url, params=parametros)
    if respuesta.status_code in (400, 404):
        return respuesta
    respuesta.raise_for_status()
    return respuesta


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
            respuesta = _pedir(
                cliente,
                api["endpoint_categorias"],
                {"per_page": 100, "page": pagina, "_fields": "id,name,slug,parent,count"},
            )
            if respuesta.status_code in (400, 404):
                break
            datos = respuesta.json()
            if not datos:
                break
            catalogo.update(
                {c["id"]: {"nombre": c["name"], "parent": c.get("parent", 0)} for c in datos}
            )
            if len(datos) < 100:
                break
            pagina += 1
            time.sleep(PAUSA_ENTRE_PAGINAS_S)
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
            respuesta = _pedir(cliente, api["endpoint_posts"], {**parametros, "page": pagina})
            if respuesta.status_code in (400, 404):
                break

            datos = respuesta.json()
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
