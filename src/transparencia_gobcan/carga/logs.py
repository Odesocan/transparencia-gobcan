"""Registro de ejecuciones en la tabla de logs.

Se escribe también cuando la ejecución falla: un fallo sin registro es un fallo
del que no se aprende nada.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from ..config import entorno
from ..modelos import Fuente, RegistroEjecucion

log = logging.getLogger(__name__)


def abrir_registro(fuente: Fuente, modo: str) -> RegistroEjecucion:
    """Crea un registro de ejecución al arrancar el pipeline."""
    from .. import __version__

    return RegistroEjecucion(
        inicio=datetime.now(), fuente=fuente, modo=modo, version_extractor=__version__
    )


def cerrar_registro(registro: RegistroEjecucion) -> None:
    """Cierra el registro y lo escribe en `transp_gobcan.logs_ejecucion`."""
    from .supabase import conectar

    registro.fin = datetime.now()
    esquema = entorno("SUPABASE_SCHEMA", "transp_gobcan")

    with conectar() as conexion, conexion.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO {esquema}.logs_ejecucion
                (inicio, fin, fuente, modo, filas_leidas, filas_insertadas,
                 filas_actualizadas, filas_descartadas, descartes_por_motivo,
                 entradillas_por_origen, anomalias, errores, exito, version_extractor)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                registro.inicio, registro.fin, registro.fuente.value, registro.modo,
                registro.filas_leidas, registro.filas_insertadas,
                registro.filas_actualizadas, registro.filas_descartadas,
                json.dumps(registro.descartes_por_motivo, ensure_ascii=False),
                json.dumps(registro.entradillas_por_origen, ensure_ascii=False),
                registro.anomalias, registro.errores,
                registro.exito, registro.version_extractor,
            ),
        )
    log.info("Registro de ejecución guardado")
