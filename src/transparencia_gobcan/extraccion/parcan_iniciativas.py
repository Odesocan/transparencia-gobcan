"""Extractor de la actividad legislativa del Parlamento de Canarias.

Por qué esta fuente y no `/noticias/`: el portal de noticias de Parcan publica
comunicación institucional de la Cámara —actos, homenajes, visitas—. De 231
noticias analizadas en 19 meses, solo 3 citaban un grupo parlamentario. El
buscador de iniciativas, en cambio, expone el proponente como campo propio.

Estructura de la fuente, verificada el 27/07/2026:

  - Búsqueda: POST a /iniciativas/index.py con LEGIS, TIPO, PROPONENTE,
    SITUACION, EXTRACTO y rango. Devuelve todos los resultados de golpe, sin
    paginación: 482 proposiciones no de ley en pleno llegan en una respuesta
    de 276 KB.
  - Cada resultado va entre `<!-- RESULT ITEM START -->` y su cierre. Alguien
    los puso a propósito y son un ancla más estable que las clases CSS.
  - Código de iniciativa parlante y estable: 11L/PNLP-0001.
  - La ficha /iniciativas/tramites.py?id_iniciativa=<codigo> trae el bloque de
    metadatos —comisión dictaminante, fecha de alta, proponentes, a instancias
    de, situación— y la cronología completa de trámites, donde aparece el
    resultado del debate ("Debate en Pleno/aprobada").

Su robots.txt declara Crawl-delay: 3 y prohíbe /api/ y /api2/. Se respetan las
dos cosas: no se usan sus endpoints internos y se espera entre peticiones.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from typing import Any

import httpx
from bs4 import BeautifulSoup
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from ..config import cargar

log = logging.getLogger(__name__)

AGENTE = (
    "ODESOCAN-transparencia-gobcan/0.1 "
    "(+https://odesocan.org; investigacion@odesocan.org)"
)

# Meses en español abreviados. Se mapean a mano a propósito: resolverlo con
# locale funciona en un portátil español y falla en el runner de GitHub Actions,
# que arranca en inglés y puede no tener el locale instalado.
MESES = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

_RX_FECHA = re.compile(r"(\d{1,2})/([a-záéíóú]{3})/(\d{4})", re.I)
_RX_RESULTADO = re.compile(
    r"debate\s+en\s+(?:pleno|comisi[oó]n)\s*/\s*(aprobad[oa]|rechazad[oa]|"
    r"deca[ií]d[oa]|retirad[oa]|no\s+aprobad[oa])",
    re.I,
)


def _cfg() -> dict:
    return cargar("fuentes")["fuentes"]["parcan_iniciativas"]


def _pausa() -> float:
    """Crawl-delay declarado en su robots.txt. No se baja de ahí."""
    return float(_cfg()["condiciones_uso"]["crawl_delay_s"])


def _cliente() -> httpx.Client:
    return httpx.Client(headers={"User-Agent": AGENTE}, timeout=120, follow_redirects=True)


@retry(
    retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=5, min=5, max=40),
    reraise=True,
)
def _pedir(cliente: httpx.Client, metodo: str, url: str, datos: dict | None = None) -> httpx.Response:
    respuesta = cliente.post(url, data=datos) if metodo == "POST" else cliente.get(url)
    respuesta.raise_for_status()
    return respuesta


def parsear_fecha(texto: str) -> tuple[int, int, int] | None:
    """Convierte '31/oct/2023' en (2023, 10, 31). Devuelve None si no encaja."""
    m = _RX_FECHA.search(texto or "")
    if not m:
        return None
    dia, mes_txt, anio = m.groups()
    mes = MESES.get(mes_txt[:3].lower())
    if not mes:
        return None
    return int(anio), mes, int(dia)


def buscar_iniciativas(
    legislatura: str, tipo: str, cliente: httpx.Client | None = None
) -> list[dict[str, Any]]:
    """Lanza una búsqueda y devuelve los resultados del listado.

    El listado ya trae código, extracto, fecha de creación y situación. El
    proponente NO está aquí: hace falta la ficha de cada iniciativa.
    """
    cfg = _cfg()["formulario"]
    datos = {**cfg["campos"], "LEGIS": legislatura, "TIPO": tipo, "BUSCAR": "Buscar"}

    propio = cliente is None
    cliente = cliente or _cliente()
    try:
        time.sleep(_pausa())
        respuesta = _pedir(cliente, "POST", cfg["endpoint"], datos)
    finally:
        if propio:
            cliente.close()

    filas = re.findall(
        r"<!-- RESULT ITEM START -->(.*?)<!-- RESULT ITEM END -->", respuesta.text, re.S
    )
    log.info("Tipo %s: %d iniciativas", tipo, len(filas))

    resultados: list[dict[str, Any]] = []
    for bruto in filas:
        sopa = BeautifulSoup(bruto, "lxml")
        enlace = sopa.find("a")
        if not enlace:
            continue
        celdas = sopa.find_all("td")
        marca_fecha = sopa.find("em", class_="fecha_iniciativa")
        imagen = sopa.find("img")

        extracto = celdas[1].get_text(" ", strip=True) if len(celdas) > 1 else ""
        if marca_fecha:
            extracto = extracto.replace(marca_fecha.get_text(" ", strip=True), "").strip()

        resultados.append({
            "codigo": enlace.get_text(strip=True),
            "extracto": " ".join(extracto.split()),
            "fecha_creacion": parsear_fecha(marca_fecha.get_text() if marca_fecha else ""),
            "situacion_listado": (imagen.get("title") or imagen.get("alt")) if imagen else None,
            "tipo": tipo,
        })
    return resultados


def descargar_ficha(codigo: str, cliente: httpx.Client | None = None) -> dict[str, Any]:
    """Descarga la ficha de trámites de una iniciativa.

    Es donde están el proponente, la persona a cuya instancia se presenta, la
    comisión dictaminante y la cronología con el resultado del debate.
    """
    url = _cfg()["formulario"]["endpoint_ficha"].format(codigo=codigo)
    propio = cliente is None
    cliente = cliente or _cliente()
    try:
        time.sleep(_pausa())
        respuesta = _pedir(cliente, "GET", url)
    finally:
        if propio:
            cliente.close()

    sopa = BeautifulSoup(respuesta.text, "lxml")
    for etiqueta in sopa(["script", "style", "nav", "header", "footer"]):
        etiqueta.decompose()
    texto = sopa.get_text("\n", strip=True)
    lineas = [linea.strip() for linea in texto.split("\n") if linea.strip()]

    # El bloque de metadatos es una sucesión de etiqueta/valor en líneas
    # consecutivas, sin marcado propio que permita seleccionarlo directamente.
    etiquetas = {
        "Comisión dictaminante": "comision",
        "Fecha de alta": "fecha_alta",
        "Proponentes": "proponentes",
        "A instancias de": "a_instancias_de",
        "Situación": "situacion",
    }
    ficha: dict[str, Any] = {"codigo": codigo, "url": url}
    for i, linea in enumerate(lineas):
        clave = etiquetas.get(linea)
        if clave and clave not in ficha and i + 1 < len(lineas):
            ficha[clave] = lineas[i + 1]

    resultado = _RX_RESULTADO.search(texto)
    ficha["resultado"] = resultado.group(1).lower() if resultado else None
    return ficha


def recorrer(legislatura: str = "11", anillo: str = "decisiones") -> Iterator[dict[str, Any]]:
    """Recorre un anillo completo de tipos y devuelve iniciativas con su ficha.

    Los anillos existen para no pagar 4.900 peticiones por el control ordinario:
    `decisiones` son las ~679 que llevan una decisión política detrás; `control`
    añade interpelaciones y comparecencias. Las preguntas quedan fuera.
    """
    tipos = _cfg()[f"tipos_anillo_{anillo}"]

    with _cliente() as cliente:
        for tipo in tipos:
            for entrada in buscar_iniciativas(legislatura, tipo, cliente):
                try:
                    entrada.update(descargar_ficha(entrada["codigo"], cliente))
                except Exception as e:  # noqa: BLE001
                    # Una ficha caída no debe tumbar el recorrido entero: se
                    # devuelve lo que trae el listado y se anota el fallo.
                    log.warning("Ficha %s no disponible: %s", entrada["codigo"], e)
                    entrada["error_ficha"] = f"{type(e).__name__}: {e}"
                yield entrada
