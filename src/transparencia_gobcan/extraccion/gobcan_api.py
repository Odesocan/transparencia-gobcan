"""Extractor principal del portal de noticias del Gobierno de Canarias.

El portal es una instalación de WordPress que expone su API REST pública sin
autenticación, así que no hace falta scraping: una petición HTTP devuelve los
datos ya estructurados. Ver `gobcan_html.py` para el plan B con navegador.

Pendiente de implementación en el Hito 3.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any


def descargar_categorias() -> list[dict[str, Any]]:
    """Descarga la taxonomía completa de categorías del portal.

    Se usa para detectar categorías nuevas: si aparece una consejería que no
    está en `config/areas.yaml`, hay que anotarlo como anomalía en vez de
    dejar la entrada sin área en silencio.
    """
    raise NotImplementedError("Hito 3")


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

    Devuelve los registros crudos de la API. La normalización es cosa de la
    capa de transformación.
    """
    raise NotImplementedError("Hito 3")
