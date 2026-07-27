"""Contrato de la capa de transformación.

Las pruebas están escritas contra los casos reales encontrados en el
reconocimiento. Están marcadas como pendientes: se implementan en el Hito 3 y
entonces pasan a verde solas, sin tener que reescribirlas.
"""

from __future__ import annotations

from datetime import date

import pytest

pendiente = pytest.mark.xfail(raises=NotImplementedError, reason="Se implementa en el Hito 3")


# --------------------------------------------------------------------------
# Entradilla
# --------------------------------------------------------------------------
@pendiente
def test_prefiere_el_sumario_del_blockquote():
    """El caso bueno: el gabinete pone los destacados en un <blockquote> inicial."""
    from transparencia_gobcan.modelos import OrigenEntradilla
    from transparencia_gobcan.transformacion.entradilla import extraer_entradilla

    html = (
        "<blockquote><p>La incorporación de dos consultas de enfermería contribuye a "
        "optimizar la atención de los pacientes</p></blockquote>"
        "<p>La sección de Dermatología del Hospital Universitario Doctor José Molina...</p>"
    )
    texto, origen = extraer_entradilla(html)
    assert origen == OrigenEntradilla.SUMARIO
    assert texto.startswith("La incorporación de dos consultas")
    assert "Hospital Universitario Doctor" not in texto  # no arrastra el cuerpo


@pendiente
def test_cae_al_primer_parrafo_si_no_hay_sumario():
    """Sin blockquote, se usa el primer párrafo cortado por frase completa."""
    from transparencia_gobcan.modelos import OrigenEntradilla
    from transparencia_gobcan.transformacion.entradilla import extraer_entradilla

    html = "<p>El Gobierno de Canarias finaliza la prealerta por vientos. Esta decisión se toma...</p>"
    texto, origen = extraer_entradilla(html)
    assert origen == OrigenEntradilla.PRIMER_PARRAFO
    assert texto.endswith((".", "…"))  # nunca a mitad de palabra


@pendiente
def test_no_devuelve_entradilla_truncada_a_media_palabra():
    """Regresión del defecto del campo `excerpt` de la fuente.

    18 de 25 entradas de la muestra llegaban cortadas así: "...indagador de lo
    guanche, espectador de su tiempo” La Dirección General de Cultura y Patrimoni"
    """
    from transparencia_gobcan.transformacion.entradilla import extraer_entradilla

    html = "<p>" + ("palabra " * 200) + "</p>"
    texto, _ = extraer_entradilla(html)
    assert not texto.endswith("palabr")
    assert texto.rstrip("… ").endswith(("palabra", "."))


# --------------------------------------------------------------------------
# Áreas
# --------------------------------------------------------------------------
@pendiente
def test_traduce_la_consejeria_de_la_legislatura_actual():
    from transparencia_gobcan.transformacion.areas import normalizar_area

    area, _ = normalizar_area([15300, 14, 163], date(2026, 7, 27))
    assert area == "sanidad"


@pendiente
def test_traduce_la_nomenclatura_anterior_para_entradas_de_2023():
    """Las entradas de mayo-julio de 2023 aún usan las categorías de la X legislatura."""
    from transparencia_gobcan.transformacion.areas import normalizar_area

    area, _ = normalizar_area([4984], date(2023, 6, 15))
    assert area == "bienestar_social"


@pendiente
def test_las_categorias_editoriales_no_son_area():
    """Portada tiene 20.220 entradas: tratarla como área contaminaría toda agregación."""
    from transparencia_gobcan.transformacion.areas import normalizar_area

    area, secundarias = normalizar_area([14, 164, 163], date(2026, 7, 27))
    assert area == "sin_asignar"
    assert "portada" not in [s.lower() for s in secundarias]


@pendiente
def test_area_nunca_es_nula():
    """Un NULL silencioso deja el 14% de las entradas invisible al filtrar por área."""
    from transparencia_gobcan.transformacion.areas import normalizar_area

    area, _ = normalizar_area([], date(2026, 7, 27))
    assert area == "sin_asignar"


# --------------------------------------------------------------------------
# Territorio
# --------------------------------------------------------------------------
@pendiente
@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("El Hospital Universitario de La Palma adapta un aseo", "La Palma"),
        ("Obras en el puerto de Puerto del Rosario", "Puerto del Rosario"),
        ("Nueva conducción de agua en La Graciosa", "La Graciosa"),
        ("El Gobierno invierte en Tenerife y Gran Canaria", "Varias islas"),
        ("El Gobierno aprueba el decreto de vivienda", "Canarias"),
    ],
)
def test_deriva_el_territorio_del_texto(texto, esperado):
    from transparencia_gobcan.transformacion.territorio import derivar_territorio

    territorio, _ = derivar_territorio(texto, "")
    assert territorio == esperado


@pendiente
def test_prefiere_la_coincidencia_mas_larga():
    """"San Bartolomé de Tirajana" no puede resolverse como "San Bartolomé" (Lanzarote)."""
    from transparencia_gobcan.transformacion.territorio import derivar_territorio

    territorio, _ = derivar_territorio("Obras en San Bartolomé de Tirajana", "")
    assert territorio == "San Bartolomé de Tirajana"


@pendiente
def test_marca_el_territorio_por_defecto_como_inferencia():
    """Una inferencia nuestra nunca puede presentarse como un dato de la fuente."""
    from transparencia_gobcan.modelos import OrigenTerritorio
    from transparencia_gobcan.transformacion.territorio import derivar_territorio

    _, origen = derivar_territorio("El Gobierno aprueba el decreto", "")
    assert origen == OrigenTerritorio.POR_DEFECTO
