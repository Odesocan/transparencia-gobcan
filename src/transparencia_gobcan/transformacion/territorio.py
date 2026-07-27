"""Derivación del territorio a partir del texto.

La fuente no publica el territorio como campo. Sus etiquetas de isla cubren solo
el 4% de las entradas y sin normalizar. Derivarlo del título y la entradilla
funciona mucho mejor: sobre 400 entradas, el 47% menciona al menos una isla o
municipio.

Como es una inferencia y no un dato publicado, la función devuelve también su
procedencia. Nunca presentamos una inferencia como si viniera de la fuente.
"""

from __future__ import annotations

import functools
import re
import unicodedata

from ..config import cargar
from ..modelos import OrigenTerritorio


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para que el cotejo no dependa de la acentuación."""
    texto = unicodedata.normalize("NFD", texto or "")
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return " ".join(texto.lower().split())


@functools.lru_cache(maxsize=1)
def _indice() -> dict:
    """Prepara los patrones territoriales una sola vez por ejecución.

    Los términos se ordenan de más largo a más corto para que "San Bartolomé de
    Tirajana" gane a "San Bartolomé", que es un municipio distinto en Lanzarote.
    """
    cfg = cargar("territorio")

    municipios: list[tuple[str, str, str]] = []  # (normalizado, nombre, isla)
    islas: list[tuple[str, str]] = []            # (normalizado, nombre)

    for isla in cfg["islas"]:
        islas.append((normalizar(isla["nombre"]), isla["nombre"]))
        for m in isla["municipios"]:
            municipios.append((normalizar(m), m, isla["nombre"]))
        for alias, canonico in (isla.get("alias") or {}).items():
            municipios.append((normalizar(alias), canonico, isla["nombre"]))

    municipios.sort(key=lambda x: -len(x[0]))
    islas.sort(key=lambda x: -len(x[0]))

    return {
        "municipios": [(re.compile(rf"(?<![\w]){re.escape(n)}(?![\w])"), nom, isla)
                       for n, nom, isla in municipios],
        "islas": [(re.compile(rf"(?<![\w]){re.escape(n)}(?![\w])"), nom) for n, nom in islas],
        "autonomico": [re.compile(re.escape(normalizar(t))) for t in cfg["ambito_autonomico"]],
        # Se aplican antes de buscar municipios: anulan la coincidencia
        "desambiguacion": [
            re.compile(patron)
            for patrones in (cfg.get("desambiguacion") or {}).values()
            for patron in patrones
        ],
        "por_defecto": cfg["territorio_por_defecto"],
        "multiple": cfg["territorio_multiple"],
    }


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
    idx = _indice()
    texto = normalizar(f"{titulo} {entradilla}")

    # Se borran primero los usos no territoriales de topónimos ambiguos: el
    # Hospital La Candelaria está en Santa Cruz, y Candelaria Delgado es una
    # persona. Sin esto, 4 de cada 5 coincidencias de "Candelaria" eran falsas.
    for rx in idx["desambiguacion"]:
        texto = rx.sub(" ", texto)

    # 1. Ámbito autonómico declarado: manda sobre cualquier mención suelta
    if any(rx.search(texto) for rx in idx["autonomico"]):
        return idx["por_defecto"], OrigenTerritorio.INFERIDO_TEXTO

    # Se consumen las coincidencias encontradas para que el municipio más largo
    # bloquee al corto y no se cuente dos veces el mismo tramo de texto
    restante = texto
    municipios: list[tuple[str, str]] = []
    for rx, nombre, isla in idx["municipios"]:
        if rx.search(restante):
            municipios.append((nombre, isla))
            restante = rx.sub(" ", restante)

    islas = {nombre for rx, nombre in idx["islas"] if rx.search(texto)}
    # Un municipio implica su isla aunque no se nombre
    islas |= {isla for _, isla in municipios}

    # 2. Un único municipio y una única isla: el municipio es más preciso
    if len(municipios) == 1 and len(islas) == 1:
        return municipios[0][0], OrigenTerritorio.INFERIDO_TEXTO

    # 3 y 4. Resolvemos por isla
    if len(islas) == 1:
        return next(iter(islas)), OrigenTerritorio.INFERIDO_TEXTO
    if len(islas) > 1:
        return idx["multiple"], OrigenTerritorio.INFERIDO_TEXTO

    # 5. Sin mención concreta: una medida sin territorio explícito es autonómica
    return idx["por_defecto"], OrigenTerritorio.POR_DEFECTO
