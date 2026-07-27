"""Normalización de áreas contra el vocabulario cerrado.

La fuente cambia de nomenclatura cada legislatura: conviven las consejerías de
la XI (hijas de la categoría «Consejerías») con las de la X en las categorías
raíz. Por eso `config/areas.yaml` no es una lista plana sino una tabla de
correspondencias con vigencia temporal. Sin eso, la serie histórica se parte en
2023 y las consultas por área devuelven resultados incompletos sin avisar.

Sobre el campo `areas`: como consejerías secundarias estaría vacío en el 99,6%
de los casos (de 562 entradas útiles medidas, 481 tienen exactamente una
consejería y solo 2 tienen dos). Donde sí hay riqueza es en las subcategorías
—Actualidad Sanitaria, Hospitales, Hemodonación, Cultura—, así que es eso lo
que recoge. Queda pendiente de tu confirmación.
"""

from __future__ import annotations

import functools
from datetime import date

from ..config import cargar

# Prioridad al resolver el área principal cuando una entrada trae varias
# categorías: una consejería manda sobre Presidencia, y Presidencia sobre el
# Consejo de Gobierno, que es el órgano donde se formalizan los acuerdos.
_PRIORIDAD_TIPO = {"consejeria": 0, "presidencia": 1, "organo": 2, "residual": 9}

AREA_RESIDUAL = "sin_asignar"


@functools.lru_cache(maxsize=1)
def _indice() -> dict:
    """Prepara los índices del vocabulario una sola vez por ejecución."""
    cfg = cargar("areas")
    areas = {a["clave"]: a for a in cfg["areas"]}
    return {
        "areas": areas,
        "correspondencias": cfg["correspondencias_gobcan"],
        "no_area": {c["id"] for c in cfg["categorias_no_area"]},
        "excluidas": {c["id"]: c for c in cfg["categorias_excluidas"]},
        # Todos los ids que la configuración conoce, sea como área o como ruido
        "conocidas": (
            {c["id"] for c in cfg["correspondencias_gobcan"]}
            | {c["id"] for c in cfg["categorias_no_area"]}
            | {c["id"] for c in cfg["categorias_excluidas"]}
        ),
    }


def _vigente(correspondencia: dict, fecha: date) -> bool:
    """Comprueba si una correspondencia estaba vigente en la fecha dada."""
    desde = correspondencia.get("vigencia_desde")
    hasta = correspondencia.get("vigencia_hasta")
    if desde and fecha < desde:
        return False
    if hasta and fecha > hasta:
        return False
    return True


def normalizar_area(
    ids_categoria: list[int],
    fecha: date,
    catalogo: dict[int, dict] | None = None,
) -> tuple[str, list[str]]:
    """Traduce las categorías de la fuente al vocabulario cerrado.

    Args:
        ids_categoria: identificadores de categoría que trae la entrada.
        fecha: fecha de publicación, necesaria para resolver qué nomenclatura
            estaba vigente.
        catalogo: mapa id -> {"nombre", "parent"} descargado de la fuente. Sirve
            para nombrar las subcategorías del campo `areas`.

    Returns:
        El área principal y la lista de subáreas. El área principal nunca es
        nula: si no hay correspondencia se devuelve el valor residual
        `sin_asignar`, que sí es visible al filtrar y se vigila en logs.
    """
    idx = _indice()
    ids = set(ids_categoria or [])

    # --- Área principal ---
    candidatas = [
        c for c in idx["correspondencias"] if c["id"] in ids and _vigente(c, fecha)
    ]
    principal = AREA_RESIDUAL
    if candidatas:
        candidatas.sort(
            key=lambda c: _PRIORIDAD_TIPO.get(
                idx["areas"].get(c["area"], {}).get("tipo", "residual"), 9
            )
        )
        principal = candidatas[0]["area"]

    # --- Subáreas: lo que no es consejería, ni ruido editorial, ni exclusión ---
    ids_correspondidas = {c["id"] for c in candidatas}
    secundarias: list[str] = []
    for cid in sorted(ids - ids_correspondidas - idx["no_area"] - set(idx["excluidas"])):
        ficha = (catalogo or {}).get(cid)
        if ficha and ficha.get("nombre"):
            secundarias.append(ficha["nombre"])

    # Sin duplicados y conservando el orden, que la fuente repite subcategorías
    # homónimas de las dos legislaturas («Hospitales, Hospitales»)
    vistas: set[str] = set()
    unicas = [s for s in secundarias if not (s.lower() in vistas or vistas.add(s.lower()))]

    return principal, unicas


def esta_excluida(ids_categoria: list[int]) -> dict | None:
    """Devuelve la categoría de exclusión que aplica, si la entrada trae alguna.

    Se usa como red de seguridad: la exclusión principal se hace en origen con
    `categories_exclude`, pero si la fuente cambiara los identificadores
    conviene descartar aquí y dejar constancia del motivo en los logs.
    """
    excluidas = _indice()["excluidas"]
    for cid in ids_categoria or []:
        if cid in excluidas:
            return excluidas[cid]
    return None


def detectar_categorias_nuevas(
    ids_vistos: set[int], catalogo: dict[int, dict] | None = None
) -> set[int]:
    """Devuelve las categorías que la configuración no sabe encuadrar.

    Una consejería nueva o renombrada debe provocar una anomalía en los logs,
    no una entrada silenciosamente sin área. Pero una SUBcategoría nueva no es
    una anomalía: el portal crea etiquetas como Hospitales o Hemodonación
    continuamente, y todas cuelgan de una consejería que sí conocemos.

    Por eso se recorre la cadena de ascendientes: si algún antepasado está en la
    configuración, la categoría queda encuadrada y no se avisa. Sin esto, una
    ejecución normal declaraba 43 anomalías falsas y las de verdad se perdían
    entre el ruido.
    """
    conocidas = _indice()["conocidas"]
    catalogo = catalogo or {}
    huerfanas: set[int] = set()

    for cid in set(ids_vistos):
        actual, visitados = cid, set()
        while actual and actual not in visitados:
            if actual in conocidas:
                break
            visitados.add(actual)
            actual = (catalogo.get(actual) or {}).get("parent", 0)
        else:
            huerfanas.add(cid)
            continue
        if actual not in conocidas:
            huerfanas.add(cid)

    return huerfanas
