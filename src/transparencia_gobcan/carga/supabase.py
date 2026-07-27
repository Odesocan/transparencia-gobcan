"""Carga en Supabase.

La escritura es un UPSERT sobre `hash_dedup`, de forma que reejecutar la
extracción actualiza en vez de duplicar. Esa es la propiedad que hace el
pipeline idempotente y permite relanzarlo sin miedo tras un fallo.

Pendiente de implementación en el Hito 3.
"""

from __future__ import annotations

from ..modelos import Entrada, RegistroEjecucion


def upsert_entradas(entradas: list[Entrada], registro: RegistroEjecucion) -> RegistroEjecucion:
    """Inserta o actualiza un lote de entradas y devuelve el registro al día.

    Distingue inserciones de actualizaciones: en modo incremental, una
    actualización significa que la fuente editó una nota ya capturada, y eso
    es información en sí misma.
    """
    raise NotImplementedError("Hito 3")
