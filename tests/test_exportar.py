"""Metadatos del volcado que consume la interfaz.

La interfaz agrupa los territorios por isla con el mapa que le da el volcado.
Si un municipio se quedara fuera, sus publicaciones desaparecerían del filtro
de isla sin que nada avisara.
"""

from __future__ import annotations

from transparencia_gobcan.carga.exportar import isla_de_territorio
from transparencia_gobcan.config import cargar


def test_cada_isla_y_municipio_tiene_isla():
    cfg = cargar("territorio")
    mapa = isla_de_territorio(cfg)
    for isla in cfg["islas"]:
        assert mapa[isla["nombre"]] == isla["nombre"]
        for municipio in isla.get("municipios") or []:
            assert mapa[municipio] == isla["nombre"]


def test_los_municipios_caen_en_su_isla():
    mapa = isla_de_territorio(cargar("territorio"))
    assert mapa["La Orotava"] == "Tenerife"
    assert mapa["Agüimes"] == "Gran Canaria"
    assert mapa["Valverde"] == "El Hierro"
    # Los valores autonómicos no son de ninguna isla: la interfaz los trata aparte
    assert "Canarias" not in mapa
    assert "Varias islas" not in mapa
