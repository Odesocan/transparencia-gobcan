"""Registro de ejecuciones en la tabla de logs.

Pendiente de implementación en el Hito 3.
"""

from __future__ import annotations

from ..modelos import Fuente, RegistroEjecucion


def abrir_registro(fuente: Fuente, modo: str) -> RegistroEjecucion:
    """Crea un registro de ejecución al arrancar el pipeline."""
    raise NotImplementedError("Hito 3")


def cerrar_registro(registro: RegistroEjecucion) -> None:
    """Cierra el registro y lo escribe en `transp_gobcan.logs_ejecucion`.

    Se escribe también cuando la ejecución falla: un fallo sin registro es un
    fallo del que no se aprende nada.
    """
    raise NotImplementedError("Hito 3")
