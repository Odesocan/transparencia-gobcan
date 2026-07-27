"""Normalización de áreas contra el vocabulario cerrado.

La fuente cambia de nomenclatura cada legislatura: conviven las consejerías de
la XI (hijas de la categoría «Consejerías») con las de la X en las categorías
raíz. Por eso `config/areas.yaml` no es una lista plana sino una tabla de
correspondencias con vigencia temporal. Sin eso, la serie histórica se parte en
2023 y las consultas por área devuelven resultados incompletos sin avisar.

Pendiente de implementación en el Hito 3.
"""

from __future__ import annotations

from datetime import date


def normalizar_area(ids_categoria: list[int], fecha: date) -> tuple[str, list[str]]:
    """Traduce las categorías de la fuente al vocabulario cerrado.

    Args:
        ids_categoria: identificadores de categoría que trae la entrada.
        fecha: fecha de publicación, necesaria para resolver qué nomenclatura
            estaba vigente.

    Returns:
        El área principal y la lista de áreas o subáreas secundarias. El área
        principal nunca es nula: si no hay correspondencia se devuelve el valor
        residual `sin_asignar`, que es visible al filtrar y se vigila en logs.
    """
    raise NotImplementedError("Hito 3")


def detectar_categorias_nuevas(ids_vistos: set[int]) -> set[int]:
    """Devuelve las categorías de la fuente que no están en la configuración.

    Una consejería nueva o renombrada debe provocar una anomalía en los logs,
    no una entrada silenciosamente sin área.
    """
    raise NotImplementedError("Hito 3")
