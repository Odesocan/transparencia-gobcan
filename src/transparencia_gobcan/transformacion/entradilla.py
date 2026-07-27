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
"""

from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup

from ..modelos import OrigenEntradilla

LONGITUD_OBJETIVO = 400  # dos o tres líneas
LONGITUD_MINIMA = 20     # por debajo, la entradilla no aporta nada

# Marca de truncado que deja WordPress al autogenerar el excerpt
_MARCAS_TRUNCADO = re.compile(r"(\[&hellip;\]|\[…\]|\[\.\.\.\])\s*$")


def limpiar_html(fragmento: str) -> str:
    """Convierte un fragmento HTML en texto plano con el espaciado normalizado."""
    if not fragmento:
        return ""
    texto = BeautifulSoup(fragmento, "lxml").get_text(" ")
    texto = html.unescape(texto)
    # El espacio duro de la fuente no lo colapsa split() por sí solo
    texto = texto.replace("\xa0", " ")
    return " ".join(texto.split())


def cortar_por_frase(texto: str, maximo: int = LONGITUD_OBJETIVO) -> str:
    """Recorta un texto sin partir palabras ni dejar frases a medias.

    Prefiere cerrar en el último final de frase que quepa. Si no hay ninguno
    utilizable, corta por palabra completa y marca el recorte con puntos
    suspensivos, para que quien lea sepa que el texto continúa.
    """
    texto = (texto or "").strip()
    if len(texto) <= maximo:
        return texto

    recorte = texto[:maximo]
    finales = [m.end() for m in re.finditer(r"[.!?][\"'”’]?(?=\s|$)", recorte)]
    if finales and finales[-1] >= maximo * 0.5:
        return recorte[: finales[-1]].strip()

    corte = recorte.rsplit(" ", 1)[0].rstrip(" ,;:-–—")
    return f"{corte}…"


def _extraer_sumario(sopa: BeautifulSoup) -> str:
    """Devuelve el sumario editorial del <blockquote> de apertura, si lo hay.

    Solo cuenta si la cita abre el cuerpo: más abajo suele ser una cita textual
    de una persona, no el sumario de la nota.
    """
    cita = sopa.find("blockquote")
    if cita is None:
        return ""

    previo = "".join(cita.find_all_previous(string=True))
    if len(" ".join(previo.split())) > 40:
        return ""

    parrafos = [limpiar_html(str(p)) for p in cita.find_all("p")]
    parrafos = [p for p in parrafos if p]
    if not parrafos:
        parrafos = [limpiar_html(str(cita))]

    # Los destacados son frases independientes: se unen con punto y espacio
    unido = ". ".join(p.rstrip(" .") for p in parrafos if p)
    return f"{unido}." if unido and not unido.endswith(".") else unido


def _extraer_primer_parrafo(sopa: BeautifulSoup) -> str:
    """Devuelve el primer párrafo con contenido real del cuerpo."""
    for p in sopa.find_all("p"):
        texto = limpiar_html(str(p))
        if len(texto) >= LONGITUD_MINIMA:
            return texto
    return ""


def extraer_entradilla(contenido_html: str, excerpt_html: str = "") -> tuple[str, OrigenEntradilla]:
    """Devuelve la entradilla y el nivel de la cascada del que salió.

    Cascada:
        1. Sumario del <blockquote> de apertura.
        2. Primer párrafo del cuerpo, cortado por frase completa.
        3. `excerpt` de la fuente, saneado.

    El nivel se devuelve para registrarlo en los logs: una caída brusca del
    nivel 1 avisa de que el gabinete cambió de práctica editorial.
    """
    sopa = BeautifulSoup(contenido_html or "", "lxml")

    sumario = _extraer_sumario(sopa)
    if len(sumario) >= LONGITUD_MINIMA:
        return cortar_por_frase(sumario), OrigenEntradilla.SUMARIO

    parrafo = _extraer_primer_parrafo(sopa)
    if len(parrafo) >= LONGITUD_MINIMA:
        return cortar_por_frase(parrafo), OrigenEntradilla.PRIMER_PARRAFO

    respaldo = _MARCAS_TRUNCADO.sub("", limpiar_html(excerpt_html)).strip()
    return cortar_por_frase(respaldo), OrigenEntradilla.EXCERPT
