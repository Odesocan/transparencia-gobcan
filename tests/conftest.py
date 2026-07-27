"""Configuración compartida de las pruebas.

Los fixtures son respuestas reales capturadas durante el reconocimiento de las
fuentes (Hito 1), no datos inventados. Así las pruebas cubren las rarezas que
las fuentes tienen de verdad —entradillas truncadas, categorías duplicadas de
dos legislaturas, fechas con mes abreviado en español— y no solo el caso ideal.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

DIR_FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def posts_gobcan() -> list[dict]:
    """25 entradas reales de la API de Gobcan, con título, entradilla y cuerpo."""
    with (DIR_FIXTURES / "gobcan_posts.json").open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def categorias_gobcan() -> list[dict]:
    """Las 168 categorías del portal, con las dos generaciones de nomenclatura."""
    with (DIR_FIXTURES / "gobcan_categorias.json").open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def listado_parcan() -> str:
    """HTML real de un listado mensual de noticias del Parlamento."""
    return (DIR_FIXTURES / "parcan_listado_mes.html").read_text(encoding="utf-8")
