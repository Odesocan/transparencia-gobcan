"""Comportamiento del extractor ante respuestas raras de la fuente.

Todas estas pruebas salen de un fallo real, no de imaginar desgracias: el
11/08/2026 la primera petición de categorías devolvió `200 OK` con el cuerpo
vacío y la ejecución se cayó entera con un `JSONDecodeError` a secas.

La fuente es un WordPress detrás de Apache y PHP, y responde `200` incluso
cuando no tiene nada que decir. Distinguir «lista vacía, se acabó la
paginación» de «cuerpo vacío, la fuente ha tropezado» es lo que aquí se fija.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from tenacity import wait_none

from transparencia_gobcan.extraccion import gobcan_api
from transparencia_gobcan.extraccion.gobcan_api import (
    RespuestaIlegible,
    descargar_categorias,
    descargar_entradas,
)

CATEGORIAS = gobcan_api._cfg()["api"]["endpoint_categorias"]
POSTS = gobcan_api._cfg()["api"]["endpoint_posts"]


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    """Los reintentos esperan entre 5 y 30 s de verdad. En pruebas, cero."""
    monkeypatch.setattr(gobcan_api._pedir.retry, "wait", wait_none())
    monkeypatch.setattr(gobcan_api, "PAUSA_ENTRE_PAGINAS_S", 0)


def _pagina(categorias: list[dict]) -> httpx.Response:
    return httpx.Response(200, json=categorias)


@respx.mock
def test_un_200_con_el_cuerpo_vacio_se_reintenta():
    """El fallo del 11/08/2026: pasajero, así que la segunda vez ha de salir bien."""
    ruta = respx.get(url__startswith=CATEGORIAS).mock(
        side_effect=[
            httpx.Response(200, text="", headers={"content-type": "application/json"}),
            _pagina([{"id": 22, "name": "Sanidad", "parent": 0}]),
        ]
    )

    catalogo = descargar_categorias()

    assert ruta.call_count == 2, "No ha reintentado: el cuerpo vacío tumbaría la ejecución"
    assert catalogo == {22: {"nombre": "Sanidad", "parent": 0}}


@respx.mock
def test_si_el_cuerpo_vacio_persiste_el_error_dice_qué_llegó():
    """Un `JSONDecodeError: line 1 column 1 (char 0)` no permite diagnosticar nada."""
    respx.get(url__startswith=CATEGORIAS).mock(
        return_value=httpx.Response(200, text="", headers={"content-type": "application/json"})
    )

    with pytest.raises(RespuestaIlegible) as fallo:
        descargar_categorias()

    mensaje = str(fallo.value)
    assert "cuerpo vacío" in mensaje
    assert "200" in mensaje and "0 bytes" in mensaje


@respx.mock
def test_una_pagina_de_error_en_html_no_pasa_por_json():
    """Si cierran la API, lo normal es que devuelvan HTML, no un 401 limpio."""
    respx.get(url__startswith=CATEGORIAS).mock(
        return_value=httpx.Response(
            200, text="<!DOCTYPE html><html><body>Mantenimiento</body></html>",
            headers={"content-type": "text/html"},
        )
    )

    with pytest.raises(RespuestaIlegible) as fallo:
        descargar_categorias()

    assert "text/html" in str(fallo.value)
    assert "DOCTYPE" in str(fallo.value)


@respx.mock
def test_un_objeto_de_error_de_wordpress_no_se_confunde_con_datos():
    """WordPress contesta con un objeto `{code, message}`, y un dict no se itera igual."""
    respx.get(url__startswith=CATEGORIAS).mock(
        return_value=httpx.Response(
            200, json={"code": "rest_forbidden", "message": "Lo siento, no tienes permiso"}
        )
    )

    with pytest.raises(RespuestaIlegible) as fallo:
        descargar_categorias()

    assert "se esperaba una lista" in str(fallo.value)
    assert "rest_forbidden" in str(fallo.value)


@respx.mock
def test_un_catalogo_vacio_no_pasa_por_bueno():
    """Son 168 categorías: cero no es un dato, es un fallo que dejaría todo sin área."""
    respx.get(url__startswith=CATEGORIAS).mock(return_value=_pagina([]))

    with pytest.raises(RespuestaIlegible, match="catálogo"):
        descargar_categorias()


@respx.mock
def test_pasarse_de_la_ultima_pagina_sigue_siendo_parada_normal():
    """El 400 del final de la paginación no es un error y no debe reintentarse."""
    ruta = respx.get(url__startswith=CATEGORIAS).mock(
        side_effect=[
            _pagina([{"id": i, "name": f"Área {i}", "parent": 0} for i in range(100)]),
            httpx.Response(400, json={"code": "rest_post_invalid_page_number"}),
        ]
    )

    catalogo = descargar_categorias()

    assert len(catalogo) == 100
    assert ruta.call_count == 2, "El 400 del final no debe reintentarse tres veces"


@respx.mock
def test_una_pagina_de_entradas_vacia_cierra_el_recorrido():
    """La lista vacía sí es final legítimo: no puede confundirse con el cuerpo vacío."""
    respx.get(url__startswith=POSTS).mock(
        side_effect=[
            _pagina([{"id": 1, "title": {"rendered": "Una noticia"}}]),
            _pagina([]),
        ]
    )

    entradas = list(descargar_entradas())

    assert [e["id"] for e in entradas] == [1]


@respx.mock
def test_las_entradas_tambien_reintentan_el_cuerpo_vacio():
    """El mismo tropiezo a mitad de paginación no puede tirar lo ya descargado.

    La primera página va llena a propósito: el recorrido se corta en cuanto una
    página no trae `por_pagina` registros, así que solo una llena obliga a pedir
    la siguiente, que es donde se simula el tropiezo.
    """
    por_pagina = gobcan_api._cfg()["api"]["por_pagina"]
    respx.get(url__startswith=POSTS).mock(
        side_effect=[
            _pagina([{"id": i} for i in range(por_pagina)]),
            httpx.Response(200, text=""),
            _pagina([{"id": 1000}]),
        ]
    )

    entradas = list(descargar_entradas())

    assert len(entradas) == por_pagina + 1
    assert entradas[-1]["id"] == 1000, "Se ha perdido la página siguiente al tropiezo"
