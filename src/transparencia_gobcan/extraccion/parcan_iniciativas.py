"""Extractor de la actividad legislativa del Parlamento de Canarias.

Fuera del alcance de la sesión actual. Se deja el contrato escrito porque el
reconocimiento (Hito 1) ya determinó la fuente correcta y su estructura.

Por qué esta fuente y no `/noticias/`: el portal de noticias de Parcan publica
comunicación institucional de la Cámara —actos, homenajes, visitas—. De 231
noticias analizadas en 19 meses, solo 3 citaban un grupo parlamentario. El
buscador de iniciativas, en cambio, expone el proponente como campo propio.

Estructura de la fuente:
  - Búsqueda: POST a /iniciativas/index.py con LEGIS, TIPO, PROPONENTE, SITUACION.
  - El listado delimita cada resultado con <!-- RESULT ITEM START -->, que es un
    ancla más estable que las clases CSS.
  - Código de iniciativa parlante y estable: 11L/PNLP-0001.
  - Ficha con proponente, situación y cronología completa de trámites en
    /iniciativas/tramites.py?id_iniciativa={codigo}.

Su robots.txt declara Crawl-delay: 3 y prohíbe /api/ y /api2/. Ambas cosas se
respetan: no se usan sus endpoints internos y se espera entre peticiones.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


def buscar_iniciativas(legislatura: str, tipo: str) -> Iterator[dict[str, Any]]:
    """Lanza una búsqueda y devuelve los resultados del listado."""
    raise NotImplementedError("Fuera del alcance de la sesión actual")


def descargar_ficha(codigo: str) -> dict[str, Any]:
    """Descarga la ficha de trámites de una iniciativa.

    Es donde están el proponente, la persona a cuya instancia se presenta, la
    situación y la cronología con el resultado del debate.
    """
    raise NotImplementedError("Fuera del alcance de la sesión actual")
