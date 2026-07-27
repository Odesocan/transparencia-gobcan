"""Carga en Supabase.

La escritura es un UPSERT sobre `hash_dedup`, de forma que reejecutar la
extracción actualiza en vez de duplicar. Esa es la propiedad que hace el
pipeline idempotente y permite relanzarlo sin miedo tras un fallo.

Se usa psycopg2 con `execute_values` en lugar del cliente REST, por coherencia
con el resto de proyectos de Canarias en Datos y porque en cargas por lotes es
bastante más rápido.
"""

from __future__ import annotations

import logging
from typing import Any

from ..config import entorno
from ..modelos import Entrada, RegistroEjecucion

log = logging.getLogger(__name__)

TAMANO_LOTE = 500

_COLUMNAS = [
    "hash_dedup", "id_fuente", "fuente", "fecha_ext", "fecha_real", "fecha_modificacion",
    "titulo", "entrada", "entrada_origen", "url", "area", "area_origen", "areas",
    "territorio", "territorio_origen", "grupo_parlamentario", "tipo_iniciativa", "situacion",
    "es_alerta", "motivo_alerta", "materias", "actos", "notificada_en",
]
# Todo salvo la clave y las marcas de creación: si la fuente corrige una nota,
# queremos el texto nuevo pero conservar cuándo la vimos por primera vez.
_ACTUALIZABLES = [c for c in _COLUMNAS if c not in ("hash_dedup", "id_fuente", "fuente")]


def conectar():
    """Abre conexión con la base de datos.

    Acepta las dos convenciones que conviven en Canarias en Datos: una cadena
    de conexión completa, o las variables sueltas CED_DB_*.
    """
    import psycopg2

    url = entorno("DATABASE_URL")
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=entorno("CED_DB_HOST", obligatoria=True),
        port=entorno("CED_DB_PORT", "5432"),
        dbname=entorno("CED_DB_NAME", "postgres"),
        user=entorno("CED_DB_USER", obligatoria=True),
        password=entorno("CED_DB_PASSWORD", obligatoria=True),
        sslmode=entorno("CED_DB_SSLMODE", "require"),
    )


def _fila(entrada: Entrada) -> tuple[Any, ...]:
    """Aplana una entrada al orden de columnas del INSERT."""
    d = entrada.model_dump()
    d["url"] = str(entrada.url)
    d["fuente"] = entrada.fuente.value
    d["entrada_origen"] = entrada.entrada_origen.value
    d["area_origen"] = entrada.area_origen.value
    d["territorio_origen"] = entrada.territorio_origen.value
    return tuple(d[c] for c in _COLUMNAS)


def upsert_entradas(entradas: list[Entrada], registro: RegistroEjecucion) -> RegistroEjecucion:
    """Inserta o actualiza un lote de entradas y devuelve el registro al día.

    Distingue inserciones de actualizaciones: en modo incremental, una
    actualización significa que la fuente editó una nota ya capturada, y eso es
    información en sí misma.
    """
    if not entradas:
        return registro

    from psycopg2.extras import execute_values

    esquema = entorno("SUPABASE_SCHEMA", "transp_gobcan")
    columnas = ", ".join(_COLUMNAS)
    asignaciones = ", ".join(f"{c} = EXCLUDED.{c}" for c in _ACTUALIZABLES)
    sentencia = f"""
        INSERT INTO {esquema}.entradas ({columnas})
        VALUES %s
        ON CONFLICT (hash_dedup) DO UPDATE SET {asignaciones}
        RETURNING (xmax = 0) AS insertada
    """

    with conectar() as conexion, conexion.cursor() as cursor:
        for inicio in range(0, len(entradas), TAMANO_LOTE):
            lote = entradas[inicio : inicio + TAMANO_LOTE]
            resultados = execute_values(
                cursor, sentencia, [_fila(e) for e in lote], page_size=TAMANO_LOTE, fetch=True
            )
            # xmax = 0 distingue la inserción de la actualización
            insertadas = sum(1 for (es_insercion,) in resultados if es_insercion)
            registro.filas_insertadas += insertadas
            registro.filas_actualizadas += len(resultados) - insertadas

    log.info(
        "Carga terminada: %d insertadas, %d actualizadas",
        registro.filas_insertadas, registro.filas_actualizadas,
    )
    return registro
