"""Carga de la configuración versionada.

Los vocabularios (áreas, territorio, alertas) y los parámetros de las fuentes
viven en `config/*.yaml`, no en constantes repartidas por el código. Así un
cambio de nomenclatura queda registrado en el historial de Git y se puede
revisar sin releer el pipeline entero.
"""

from __future__ import annotations

import functools
import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[2]
DIR_CONFIG = RAIZ / "config"

load_dotenv(RAIZ / ".env")


@functools.cache
def cargar(nombre: str) -> dict[str, Any]:
    """Lee un fichero de configuración YAML y lo devuelve como diccionario.

    El resultado se cachea: los vocabularios se consultan una vez por fila y no
    tiene sentido releer el disco cada vez.
    """
    ruta = DIR_CONFIG / f"{nombre}.yaml"
    if not ruta.exists():
        raise FileNotFoundError(f"No existe el fichero de configuración: {ruta}")
    with ruta.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def entorno(clave: str, por_defecto: str | None = None, obligatoria: bool = False) -> str | None:
    """Lee una variable de entorno.

    Con `obligatoria=True` falla en el arranque en lugar de dejar que el error
    aparezca a mitad de una carga, cuando ya se han tocado datos.
    """
    valor = os.getenv(clave, por_defecto)
    if obligatoria and not valor:
        raise RuntimeError(
            f"Falta la variable de entorno {clave}. "
            "Copia .env.example a .env y rellénala, o defínela como secreto en GitHub."
        )
    return valor
