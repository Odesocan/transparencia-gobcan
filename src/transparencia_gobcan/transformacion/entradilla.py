"""Construcción de la entradilla.

El campo `excerpt` de la API no sirve: WordPress lo autogenera cortando a unas
55 palabras, lo que concatena el sumario editorial con el arranque del cuerpo y
trunca a mitad de palabra. En una muestra de 25 entradas, 18 llegaban cortadas.

La entradilla buena es el <blockquote> con el que abre el cuerpo, donde el
gabinete coloca los dos o tres destacados de la nota. Aparece en torno a la
mitad de las entradas; las que no lo tienen son casi siempre partes del 112 y
avisos, que ya se excluyen en origen.

Sobre no almacenar el cuerpo: extraer el sumario obliga a DESCARGAR el campo
`content`, pero no a guardarlo. Se procesa aquí, en memoria, y se descarta. En
Supabase solo se persiste la entradilla resultante.

Pendiente de implementación en el Hito 3.
"""

from __future__ import annotations

from ..modelos import OrigenEntradilla

LONGITUD_OBJETIVO = 400  # dos o tres líneas


def extraer_entradilla(contenido_html: str, excerpt_html: str = "") -> tuple[str, OrigenEntradilla]:
    """Devuelve la entradilla y el nivel de la cascada del que salió.

    Cascada:
        1. Sumario del <blockquote> de apertura.
        2. Primer párrafo del cuerpo, cortado por frase completa.
        3. `excerpt` de la fuente, saneado.

    El nivel se devuelve para registrarlo en los logs: una caída brusca del
    nivel 1 avisa de que el gabinete cambió de práctica editorial.
    """
    raise NotImplementedError("Hito 3")


def cortar_por_frase(texto: str, maximo: int = LONGITUD_OBJETIVO) -> str:
    """Recorta un texto sin partir palabras ni dejar frases a medias."""
    raise NotImplementedError("Hito 3")
