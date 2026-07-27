"""Validación del modelo de datos."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from pydantic import ValidationError

from transparencia_gobcan.modelos import (
    Entrada,
    Fuente,
    MotivoDescarte,
    OrigenEntradilla,
    RegistroEjecucion,
)


def _entrada_valida(**cambios) -> Entrada:
    base = dict(
        id_fuente="196122",
        fuente=Fuente.GOBIERNO,
        fecha_ext=datetime.now(),
        fecha_real=date(2026, 7, 27),
        titulo="La sección Dermatología del Hospital Molina Orosa incrementa las consultas",
        entrada="La incorporación de dos consultas de enfermería contribuye a optimizar la atención.",
        entrada_origen=OrigenEntradilla.SUMARIO,
        url="https://www3.gobiernodecanarias.org/noticias/ejemplo/",
        area="sanidad",
    )
    return Entrada(**{**base, **cambios})


def test_el_hash_se_calcula_solo_y_es_estable():
    """La idempotencia depende de que el hash no cambie entre ejecuciones."""
    a, b = _entrada_valida(), _entrada_valida()
    assert a.hash_dedup and a.hash_dedup == b.hash_dedup


def test_el_hash_no_depende_del_titulo():
    """Si la fuente corrige una errata, la entrada debe actualizarse, no duplicarse."""
    a = _entrada_valida()
    b = _entrada_valida(titulo="La sección Dermatología del Hospital Molina Orosa: título corregido")
    assert a.hash_dedup == b.hash_dedup


def test_rechaza_fecha_futura():
    with pytest.raises(ValidationError):
        _entrada_valida(fecha_real=date.today() + timedelta(days=1))


def test_rechaza_fecha_anterior_al_periodo():
    """Una fecha de 1998 no es una noticia antigua: es un parseo roto."""
    with pytest.raises(ValidationError):
        _entrada_valida(fecha_real=date(1998, 1, 1))


def test_rechaza_entradilla_vacia():
    with pytest.raises(ValidationError):
        _entrada_valida(entrada="")


def test_normaliza_los_espacios_del_html():
    entrada = _entrada_valida(titulo="Título   con\n\nespacios   sobrantes del HTML")
    assert entrada.titulo == "Título con espacios sobrantes del HTML"


def test_el_registro_guarda_el_motivo_del_descarte():
    """La tabla de logs existe para aprender: el recuento sin motivo no enseña nada."""
    reg = RegistroEjecucion(inicio=datetime.now(), fuente=Fuente.GOBIERNO, modo="incremental")
    reg.anotar_descarte(MotivoDescarte.ENTRADILLA_VACIA, "id 196122")
    reg.anotar_descarte(MotivoDescarte.ENTRADILLA_VACIA)
    reg.anotar_descarte(MotivoDescarte.FECHA_FUERA_RANGO)

    assert reg.filas_descartadas == 3
    assert reg.descartes_por_motivo == {"entradilla_vacia": 2, "fecha_fuera_rango": 1}
    assert "entradilla_vacia: id 196122" in reg.anomalias
