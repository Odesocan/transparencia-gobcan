"""Etiquetas temáticas de la interfaz de consulta.

Una entrada puede llevar varias y casi la mitad de las etiquetadas llevan más
de una: "cuatro millones para viviendas adaptadas a personas con discapacidad"
es vivienda Y discapacidad, y tiene que salir en los dos filtros. Por eso el
resultado es una lista y no un valor.

POR QUÉ NO SE REUTILIZAN LAS `materias` DEL CLASIFICADOR DE ALERTAS

Porque resuelven problemas opuestos. El vocabulario de alertas decide qué se
notifica por correo y está calibrado para 1,9 avisos al día: cada término de
más son correos de más. Este decide cómo se recorren 16.000 entradas, y ahí una
entrada sin etiquetar es una entrada invisible. Medido sobre el volcado del
27/07/2026, el vocabulario de alertas dejaba el 55% del archivo sin ninguna
materia; este cubre el 81%. El razonamiento largo está en
`config/etiquetas_tematicas.yaml`.

DÓNDE SE CALCULA, Y POR QUÉ AHÍ

En `transparencia exportar`, sobre el título y la entradilla que ya vienen de
la base, y no en el momento de la carga. Así ampliar el vocabulario no obliga a
recalcular la tabla entera ni toca el volumen de correo: se reexporta y la
interfaz lo recoge. El coste es recorrer 16.000 textos con 22 patrones, que en
la práctica es un segundo.
"""

from __future__ import annotations

import functools
import re
from typing import Any

from ..config import cargar
from .territorio import normalizar as _sin_tildes


def normalizar(texto: str) -> str:
    """Minúsculas, sin tildes y sin marcado, que es como están escritos los patrones."""
    return _sin_tildes(re.sub(r"<[^>]+>", " ", texto or ""))


@functools.lru_cache(maxsize=1)
def _vocabulario() -> list[tuple[str, Any]]:
    """Compila el vocabulario una sola vez por ejecución.

    Con re.VERBOSE, porque los patrones del YAML van en varias líneas. Eso
    implica que los espacios literales se ignoran y que el vocabulario escribe
    `\\s+` para los que cuentan. Ver la nota larga del fichero de configuración.
    """
    return [
        (e["clave"], re.compile(e["patron"], re.VERBOSE))
        for e in cargar("etiquetas_tematicas")["etiquetas"]
    ]


def catalogo() -> list[dict[str, str]]:
    """Las etiquetas con su nombre legible y su grupo, en el orden del fichero.

    La interfaz lo usa para pintar la nube de filtros, así que el orden del
    YAML es el orden en pantalla: se decide editando la configuración, no el
    código de la página.
    """
    cfg = cargar("etiquetas_tematicas")
    return [
        {"clave": e["clave"], "nombre": e["nombre"],
         "grupo": e["grupo"], "color": e["color"]}
        for e in cfg["etiquetas"]
    ]


def grupos() -> list[dict[str, str]]:
    """Los dos bloques en que se agrupan las etiquetas en la interfaz."""
    return [dict(g) for g in cargar("etiquetas_tematicas")["grupos"]]


def etiquetar(titulo: str, entradilla: str | None = None) -> list[str]:
    """Devuelve las etiquetas temáticas que casan con el texto.

    Se cotejan título y entradilla juntos porque el asunto de la nota suele
    estar en la entradilla y no en el titular: "Canarias refuerza la red" no
    dice de qué, y el cuerpo sí.
    """
    texto = normalizar(f"{titulo or ''} {entradilla or ''}")
    return [clave for clave, patron in _vocabulario() if patron.search(texto)]
