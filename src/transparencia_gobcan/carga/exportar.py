"""Volcado de los datos para la interfaz de consulta.

La interfaz es estática: no habla con Supabase, lee un fichero. Así no hay que
abrir la base al navegador —lo que obligaría a exponer el schema y a escribir
políticas de lectura pública— y el mismo fichero sirve en local y empotrado en
un bloque de Divi.

El formato es columnar: en vez de 16.000 objetos con las mismas claves
repetidas, se guarda una lista de campos y una lista de filas como arrays. Las
áreas, los grupos y los territorios se sustituyen por su índice en un catálogo.
Suena a microoptimización, pero baja el fichero de 11,6 MB a menos de la mitad,
y eso es la diferencia entre que la interfaz abra al instante o tarde un segundo
largo en un portátil normal.
"""

from __future__ import annotations

import json
import logging
import pathlib
from typing import Any

from ..config import entorno

log = logging.getLogger(__name__)

# Orden de los campos en cada fila. La interfaz lo lee de `campos`, así que
# añadir uno nuevo al final no rompe nada.
CAMPOS = [
    "fecha", "fuente", "titulo", "entrada", "url",
    "area", "territorio", "grupo", "tipo", "situacion", "alerta", "materias",
]


def exportar(destino: pathlib.Path) -> dict[str, Any]:
    """Vuelca las entradas a un JSON compacto y devuelve un resumen."""
    from .supabase import conectar

    esquema = entorno("SUPABASE_SCHEMA", "transp_gobcan")
    with conectar() as conexion, conexion.cursor() as cursor:
        cursor.execute(
            f"""SELECT fecha_real::text, fuente::text, titulo, entrada, url,
                       area, territorio, grupo_parlamentario, tipo_iniciativa,
                       situacion, es_alerta, materias
                  FROM {esquema}.entradas
                 ORDER BY fecha_real DESC, fuente"""
        )
        crudas = cursor.fetchall()

    # Catálogos: los valores que se repiten miles de veces se guardan una vez
    catalogos: dict[str, list[str]] = {"area": [], "territorio": [], "grupo": [],
                                       "tipo": [], "situacion": [], "materias": []}
    indices: dict[str, dict[str, int]] = {k: {} for k in catalogos}

    def idx(campo: str, valor: str | None) -> int | None:
        if valor is None:
            return None
        tabla, catalogo = indices[campo], catalogos[campo]
        if valor not in tabla:
            tabla[valor] = len(catalogo)
            catalogo.append(valor)
        return tabla[valor]

    filas: list[list[Any]] = []
    for (fecha, fuente, titulo, entrada, url, area, territorio,
         grupo, tipo, situacion, alerta, materias) in crudas:
        filas.append([
            fecha,
            0 if fuente == "gobierno" else 1,
            titulo,
            entrada,
            url,
            idx("area", area),
            idx("territorio", territorio),
            idx("grupo", grupo),
            idx("tipo", tipo),
            idx("situacion", situacion),
            1 if alerta else 0,
            [idx("materias", m) for m in (materias or [])],
        ])

    # Actividad mensual, precalculada: la interfaz no tiene que recorrer 16.000
    # filas para pintar el gráfico cada vez que se cambia un filtro.
    meses: dict[str, list[int]] = {}
    for f in filas:
        clave = f[0][:7]
        meses.setdefault(clave, [0, 0])[f[1]] += 1

    from .. import __version__
    from ..config import cargar

    nombres_area = {a["clave"]: a["nombre"] for a in cargar("areas")["areas"]}

    datos = {
        "version": __version__,
        "campos": CAMPOS,
        "catalogos": catalogos,
        "nombres_area": nombres_area,
        "actividad": [{"mes": m, "gobierno": v[0], "parlamento": v[1]}
                      for m, v in sorted(meses.items())],
        "filas": filas,
    }

    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(datos, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    peso = destino.stat().st_size

    resumen = {
        "entradas": len(filas),
        "peso_mb": round(peso / 1024 / 1024, 2),
        "desde": filas[-1][0] if filas else None,
        "hasta": filas[0][0] if filas else None,
        "meses": len(meses),
    }
    log.info("Exportadas %d entradas a %s (%.1f MB)", len(filas), destino, peso / 1024 / 1024)
    return resumen
