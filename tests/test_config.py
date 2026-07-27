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


# ---------------------------------------------------------------------------
# El vocabulario de clasificación por área es distinto del de alertas.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "area, termino",
    [
        ("sanidad", "atencion primaria en el area de salud"),
        ("educacion", "el profesorado y el alumnado de formacion profesional"),
        ("universidades", "patrimonio cultural y museos"),
        ("obras_publicas", "vivienda protegida y transporte"),
        ("bienestar_social", "accesibilidad universal y dependencia"),
        ("presidencia_aapp", "cabildos insulares y regimen local"),
        ("transicion_ecologica", "parque natural y energia renovable"),
        ("agricultura", "ganaderia y pesca"),
        ("turismo_empleo", "alojamientos turisticos y empleo"),
        ("hacienda", "presupuestos generales e impuestos"),
        ("economia", "industria y comercio de autonomos"),
        ("politica_territorial", "ordenacion del territorio y suelo rustico"),
    ],
)
def test_cada_area_encuentra_sus_terminos_caracteristicos(area, termino):
    """Regresión de un fallo que compila sin error y no encuentra nada.

    `naturales?` significa "naturale" más una "s" opcional, así que NO casa
    "natural": la forma correcta es `natural(es)?`. El patrón compilaba
    perfectamente y dejaba "Parque Natural de Jandía" sin clasificar. Había
    cinco patrones con ese mismo defecto. Es el mismo tipo de fallo que el del
    plural en "violencias machistas", y por eso ahora se vigila término a
    término en vez de comprobar solo que el patrón compila.
    """
    patron = re.compile(cargar("clasificacion_area")["areas"][area], re.VERBOSE)
    assert patron.search(termino), f"El área {area!r} no detecta {termino!r}"


@pytest.mark.parametrize(
    "area, singular, plural",
    [
        ("transicion_ecologica", "parque natural", "parques naturales"),
        ("transicion_ecologica", "energia renovable", "energias renovables"),
        ("politica_territorial", "plan insular", "planes insulares"),
        ("politica_territorial", "asentamiento rural", "asentamientos rurales"),
        ("presidencia_aapp", "cabildo insular", "cabildos insulares"),
        ("hacienda", "presupuesto general", "presupuestos generales"),
        ("educacion", "federacion deportiva", "federaciones deportivas"),
    ],
)
def test_los_patrones_casan_singular_y_plural(area, singular, plural):
    """Regresión: `naturales?` casa "naturale", no "natural".

    Este es el error que más caro sale: el patrón compila sin quejarse y no
    encuentra nada. Dejaba "Parque Natural de Jandía" sin clasificar, y había
    cinco patrones con el mismo defecto. La forma correcta es `natural(es)?`.
    Comprobar que el patrón compila no basta: hay que comprobar que encuentra.
    """
    patron = re.compile(cargar("clasificacion_area")["areas"][area], re.VERBOSE)
    assert patron.search(singular), f"{area}: no detecta el singular {singular!r}"
    assert patron.search(plural), f"{area}: no detecta el plural {plural!r}"
