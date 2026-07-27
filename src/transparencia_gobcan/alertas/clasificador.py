"""Capa semántica: decide qué entradas merecen notificación.

No todo lo capturado se notifica. Interesan las decisiones del ejecutivo y del
legislativo sobre iniciativas políticas, y las menciones a entidades que
seguimos. El vocabulario vive en `config/alertas.yaml`.

Medido sobre 1.000 entradas reales (27/04-27/07 de 2026): reduce de 11,0 a
1,7 entradas al día, un 16% del total.

Dos lecciones del ajuste, que conviene no perder:

  - La fuente alterna singular y plural, y publica "violencias machistas", no
    "violencia machista". Cotejar la forma exacta dejaba fuera las 354 entradas
    sobre violencia de género publicadas desde mayo de 2023. Por eso el
    vocabulario usa raíces con variantes, no palabras cerradas.

  - Un municipio en el texto suele ser el LUGAR donde ocurre algo, no la
    institución que decide. Cotejar el topónimo a secas disparaba 154 alertas
    falsas de 292. Los cabildos y ayuntamientos solo cuentan cuando aparecen
    como institución actuante, y aun así necesitan una materia.

"""

from __future__ import annotations

import functools
import re
import unicodedata

from ..config import cargar
from ..modelos import Entrada


def normalizar(texto: str) -> str:
    """Pasa a minúsculas y quita tildes, para que el cotejo no dependa de la acentuación."""
    texto = re.sub(r"<[^>]+>", " ", texto or "")
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return " ".join(texto.lower().split())


@functools.lru_cache(maxsize=1)
def _patrones() -> dict:
    """Compila el vocabulario una sola vez por ejecución.

    Se compila con re.VERBOSE porque los patrones del YAML van en varias líneas.
    Eso implica que los espacios literales se ignoran: el vocabulario escribe
    `\\s+` para los espacios con significado. Ver la nota en config/alertas.yaml.
    """
    cfg = cargar("alertas")
    return {
        "actos": {k: re.compile(v, re.VERBOSE) for k, v in cfg["actos"].items()},
        "materias": {k: re.compile(v, re.VERBOSE) for k, v in cfg["materias"].items()},
        "propias": re.compile(cfg["entidades"]["propias"], re.VERBOSE),
        "cabildos": re.compile(cfg["entidades"]["cabildos"], re.VERBOSE),
        "ayuntamientos": re.compile(cfg["entidades"]["ayuntamientos"], re.VERBOSE),
    }


def clasificar(entrada: Entrada) -> Entrada:
    """Marca la entrada con su motivo de alerta, materias y actos detectados.

    Reglas de disparo, en orden:
        1. Mención propia (ODESOCAN, ACUFADE, AFFA) -> alerta siempre.
        2. Acto de decisión + materia vigilada -> alerta.
        3. Cabildo o ayuntamiento actuante + materia -> alerta.
    """
    p = _patrones()
    texto = normalizar(f"{entrada.titulo} {entrada.entrada}")

    actos = [k for k, rx in p["actos"].items() if rx.search(texto)]
    materias = [k for k, rx in p["materias"].items() if rx.search(texto)]
    institucion = bool(p["cabildos"].search(texto) or p["ayuntamientos"].search(texto))

    if p["propias"].search(texto):
        motivo = "entidad_propia"
    elif actos and materias:
        motivo = "decision_con_materia"
    elif institucion and materias:
        motivo = "institucion_con_materia"
    else:
        motivo = None

    entrada.actos = actos
    entrada.materias = materias
    entrada.es_alerta = motivo is not None
    entrada.motivo_alerta = motivo
    return entrada
