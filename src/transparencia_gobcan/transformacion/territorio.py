"""Derivación del territorio a partir del texto.

La fuente no publica el territorio como campo. Sus etiquetas de isla cubren solo
el 4% de las entradas y sin normalizar. Derivarlo del título y la entradilla
funciona mucho mejor: sobre 400 entradas, el 47% menciona al menos una isla o
municipio.

Como es una inferencia y no un dato publicado, la función devuelve también su
procedencia. Nunca presentamos una inferencia como si viniera de la fuente.

Pendiente de implementación en el Hito 3.
"""

from __future__ import annotations

from ..modelos import OrigenTerritorio


def derivar_territorio(titulo: str, entradilla: str) -> tuple[str, OrigenTerritorio]:
    """Deduce el ámbito territorial del texto.

    Reglas, en orden:
        1. Ámbito autonómico explícito ("todo el archipiélago") -> "Canarias".
        2. Un solo municipio reconocido -> ese municipio.
        3. Una sola isla -> esa isla.
        4. Varias islas -> "Varias islas".
        5. Sin mención -> "Canarias" por defecto.

    El cotejo va siempre por coincidencia más larga primero, para que
    "San Bartolomé de Tirajana" no se resuelva como "San Bartolomé".
    """
    raise NotImplementedError("Hito 3")
