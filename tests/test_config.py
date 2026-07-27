"""Coherencia de los ficheros de configuración.

Estas pruebas no dependen del Hito 3: la configuración ya existe y puede
romperse sola. Un error de dedo en `areas.yaml` no debe descubrirse a mitad de
una carga histórica.
"""

from __future__ import annotations

import re

import pytest

from transparencia_gobcan.config import cargar


def test_las_correspondencias_apuntan_a_areas_existentes():
    """Ninguna correspondencia puede señalar a una clave de área inventada."""
    cfg = cargar("areas")
    claves = {a["clave"] for a in cfg["areas"]}
    for c in cfg["correspondencias_gobcan"]:
        assert c["area"] in claves, f"La categoría {c['id']} apunta al área inexistente {c['area']!r}"


def test_no_hay_correspondencias_duplicadas():
    """Un mismo id de categoría con dos áreas haría el resultado impredecible."""
    cfg = cargar("areas")
    vistos: dict[int, str] = {}
    for c in cfg["correspondencias_gobcan"]:
        # Un id puede repetirse solo si las vigencias no se solapan
        clave = (c["id"], c.get("vigencia_desde"), c.get("vigencia_hasta"))
        assert clave not in vistos, f"Correspondencia duplicada para el id {c['id']}"
        vistos[clave] = c["area"]


def test_existe_un_area_residual():
    """Sin valor residual, las entradas sin consejería quedarían invisibles al filtrar."""
    cfg = cargar("areas")
    residuales = [a for a in cfg["areas"] if a.get("tipo") == "residual"]
    assert residuales, "Hace falta un área residual explícita; NULL no vale"


def test_los_patrones_de_alertas_compilan():
    """Un patrón mal escrito debe fallar aquí, no en producción."""
    cfg = cargar("alertas")
    for grupo in ("actos", "materias"):
        for nombre, patron in cfg[grupo].items():
            try:
                re.compile(patron, re.VERBOSE)
            except re.error as e:
                pytest.fail(f"El patrón {grupo}.{nombre} no compila: {e}")


def test_el_vocabulario_de_violencia_de_genero_cubre_el_plural():
    """Regresión: la fuente publica "violencias machistas", en plural.

    Cotejar solo el singular dejaba fuera las 354 entradas sobre violencia de
    género publicadas desde mayo de 2023. Es el fallo que más cerca estuvo de
    pasar inadvertido, así que queda fijado como prueba.
    """
    patron = re.compile(cargar("alertas")["materias"]["violencia_genero"], re.VERBOSE)
    for texto in [
        "canarias consolida la red integral de proteccion frente a violencias machistas",
        "campana para prevenir la violencia sexual infantil",
        "medidas contra la violencia de genero",
        "protocolos para prevenir y detectar el maltrato",
    ]:
        assert patron.search(texto), f"No detecta: {texto!r}"


def test_los_88_municipios_estan_completos():
    """Canarias tiene 88 municipios; si falta alguno, su territorio se perdería."""
    cfg = cargar("territorio")
    total = sum(len(i["municipios"]) for i in cfg["islas"] if i["clave"] != "la_graciosa")
    assert total == 88, f"Se esperaban 88 municipios y hay {total}"


def test_no_hay_municipios_repetidos_entre_islas():
    """Un municipio en dos islas haría ambigua la derivación del territorio."""
    cfg = cargar("territorio")
    vistos: dict[str, str] = {}
    for isla in cfg["islas"]:
        for m in isla["municipios"]:
            assert m not in vistos, f"{m} aparece en {vistos.get(m)} y en {isla['nombre']}"
            vistos[m] = isla["nombre"]
