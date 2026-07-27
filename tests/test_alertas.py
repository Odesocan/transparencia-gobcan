"""Contrato de la capa semántica de alertas.

Los casos vienen de la validación empírica sobre 1.000 entradas reales
(27/04-27/07 de 2026), incluidos los dos falsos positivos que obligaron a
rehacer el vocabulario.
"""

from __future__ import annotations

import pytest

pendiente = pytest.mark.xfail(raises=NotImplementedError, reason="Se implementa en el Hito 3")


@pendiente
@pytest.mark.parametrize(
    "titulo",
    [
        "Canarias aprueba la ley que agiliza las licencias urbanísticas y la construcción de viviendas",
        "Bienestar Social destina 3,5 millones de euros a subvenciones para personas mayores",
        "La Gerencia Sanitaria de Lanzarote saca a licitación las obras de ampliación del consultorio",
        "Canarias consolida la red integral de protección frente a violencias machistas",
    ],
)
def test_notifica_las_decisiones_sobre_materias_vigiladas(titulo):
    from transparencia_gobcan.alertas.clasificador import clasificar

    assert clasificar(_entrada(titulo)).es_alerta


@pendiente
@pytest.mark.parametrize(
    "titulo",
    [
        # Actividad asistencial ordinaria: no hay decisión política
        "La sección Dermatología del Hospital Molina Orosa incrementa un 24,5 por ciento las consultas",
        # Agenda cultural
        "El MUNA acoge ‘Arqueología de la Mirada’, una muestra sobre el legado fotográfico",
        # Falso positivo real de la v1: el municipio es el LUGAR, no quien decide.
        # Cotejar el topónimo a secas disparaba 154 alertas falsas de 292.
        "Obras Públicas informa de desvíos en la FV-20 en Puerto del Rosario",
    ],
)
def test_no_notifica_lo_que_no_es_una_decision(titulo):
    from transparencia_gobcan.alertas.clasificador import clasificar

    assert not clasificar(_entrada(titulo)).es_alerta


@pendiente
def test_una_mencion_propia_notifica_siempre():
    """Si nos citan, se avisa aunque no haya decisión ni materia."""
    from transparencia_gobcan.alertas.clasificador import clasificar

    entrada = clasificar(_entrada("El Gobierno se reúne con ODESOCAN y ACUFADE"))
    assert entrada.es_alerta
    assert entrada.motivo_alerta == "entidad_propia"


@pendiente
def test_detecta_violencia_de_genero_en_plural():
    """Regresión: la fuente escribe "violencias machistas", no "violencia machista"."""
    from transparencia_gobcan.alertas.clasificador import clasificar

    entrada = clasificar(
        _entrada("El Gobierno aprueba el plan contra las violencias machistas en Canarias")
    )
    assert "violencia_genero" in entrada.materias


def _entrada(titulo: str):
    """Construye una entrada mínima para probar solo la clasificación."""
    from datetime import date, datetime

    from transparencia_gobcan.modelos import Entrada, Fuente, OrigenEntradilla

    return Entrada(
        id_fuente="1", fuente=Fuente.GOBIERNO, fecha_ext=datetime.now(),
        fecha_real=date(2026, 7, 1), titulo=titulo,
        entrada="Entradilla de prueba con longitud suficiente para validar.",
        entrada_origen=OrigenEntradilla.SUMARIO,
        url="https://www3.gobiernodecanarias.org/noticias/x/", area="sanidad",
    )
