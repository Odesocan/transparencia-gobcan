"""Plan B: extracción del portal de Gobcan a partir del HTML.

Solo debe usarse si la API REST deja de responder o se cierra. El contenido es
server-side, así que en la mayoría de escenarios basta con `httpx` más
BeautifulSoup; Playwright queda reservado para el caso de que añadan una capa
de JavaScript o de verificación.

Puntos de rotura conocidos, verificados el 27/07/2026 (ver docs/puntos-de-rotura.md):
  - `.article-excerpt` solo existe en la portada, no en la vista de categoría.
  - `.article-date` solo se pinta en la primera entrada de cada grupo de fecha.
  - El primer <a> de cada artículo apunta a la categoría, no a la noticia.

Pendiente de implementación en el Hito 3.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


def descargar_categoria(slug: str, pagina_maxima: int | None = None) -> Iterator[dict[str, Any]]:
    """Recorre las páginas de una categoría hasta agotarlas.

    El portal responde 404 al pasarse de la última página, que es la condición
    de parada natural.
    """
    raise NotImplementedError("Hito 3")


def descargar_con_navegador(url: str) -> str:
    """Descarga una página con Playwright.

    Último recurso, solo si el HTML servido dejara de traer el contenido.
    Requiere el extra `respaldo`: `pip install -e ".[respaldo]"`.
    """
    raise NotImplementedError("Hito 3")
