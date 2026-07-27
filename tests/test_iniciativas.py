"""Transformación de iniciativas parlamentarias.

Los casos son iniciativas reales de la XI legislatura, capturadas al probar el
extractor contra el buscador del Parlamento.
"""

from __future__ import annotations

import pytest

from transparencia_gobcan.extraccion.parcan_iniciativas import parsear_fecha
from transparencia_gobcan.modelos import OrigenArea
from transparencia_gobcan.transformacion.iniciativas import (
    componer_titulo,
    derivar_area,
    normalizar_grupo,
)


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("(Creada el 31/oct/2023)", (2023, 10, 31)),
        ("2/ago/2023", (2023, 8, 2)),
        ("9/abr/2024", (2024, 4, 9)),
        ("sin fecha", None),
    ],
)
def test_parsea_el_mes_abreviado_en_espanol(texto, esperado):
    """Regresión: resolverlo con locale falla en el runner de GitHub Actions.

    El runner arranca en inglés y puede no tener es_ES instalado, así que los
    meses van mapeados a mano.
    """
    assert parsear_fecha(texto) == esperado


def test_la_comision_dictaminante_da_un_area_publicada():
    """Es un dato de la Cámara, no una deducción nuestra."""
    area, origen = derivar_area("Presupuestos y Hacienda", "De Presupuestos Generales para 2024.")
    assert area == "hacienda"
    assert origen == OrigenArea.PUBLICADO


def test_las_comisiones_no_sectoriales_no_designan_area():
    """Reglamento o Cabildos Insulares no son un área de gobierno."""
    area, origen = derivar_area("Reglamento", "De modificación del Reglamento de la Cámara.")
    assert origen != OrigenArea.PUBLICADO


def test_sin_comision_el_area_se_deduce_y_se_marca():
    area, origen = derivar_area(None, "Medidas urgentes en materia de vivienda protegida")
    assert area == "obras_publicas"
    assert origen == OrigenArea.INFERIDO_TEXTO


@pytest.mark.parametrize(
    "extracto, esperado",
    [
        # Estos tres los clasificaba mal el vocabulario de alertas, que solo
        # cubre derechos sociales. El de clasificación por área cubre todo el
        # espectro de la acción de gobierno, que es otra pregunta distinta.
        ("De modificación de la Ley 5/1986 del impuesto especial", "hacienda"),
        ("Por la que se modifica la Ley de regulación del sector eléctrico canario",
         "transicion_ecologica"),
        ("Sobre la ordenación del suelo rústico y el planeamiento insular",
         "politica_territorial"),
    ],
)
def test_el_vocabulario_de_area_cubre_lo_que_el_de_alertas_no(extracto, esperado):
    area, origen = derivar_area(None, extracto)
    assert area == esperado
    assert origen == OrigenArea.INFERIDO_TEXTO


def test_sin_ninguna_senal_queda_en_el_area_residual():
    """Los términos genéricos no bastan: Canarias o Gobierno aparecen en todo."""
    area, origen = derivar_area(None, "De modificación del artículo 3 de la ley de Canarias")
    assert area == "sin_asignar"
    assert origen == OrigenArea.POR_DEFECTO


def test_solo_los_grupos_van_a_grupo_parlamentario():
    """Los proyectos de ley los presenta el Gobierno y figuran como órgano.

    Meter "Pleno del Parlamento" en grupo_parlamentario falsearía el filtro
    por grupo de la interfaz.
    """
    assert normalizar_grupo("Pleno del Parlamento") is None
    assert normalizar_grupo("Gobierno de Canarias") is None
    assert normalizar_grupo("GP Socialista Canario") == "GP Socialista Canario"


def test_reconoce_las_iniciativas_conjuntas():
    grupos = normalizar_grupo("GP Socialista Canario, GP Nacionalista Canario (CCa)")
    assert "GP Socialista Canario" in grupos
    assert "GP Nacionalista Canario (CCa)" in grupos


def test_el_titulo_nombra_el_tipo_en_lenguaje_llano():
    """Los códigos son opacos fuera del Parlamento."""
    titulo = componer_titulo("PNLP", "Eliminación de la tasa de reposición de efectivos")
    assert titulo.startswith("Proposición no de ley en pleno:")


def test_el_titulo_recorta_sin_partir_palabras():
    titulo = componer_titulo("PL", "palabra " * 60)
    assert len(titulo) < 200
    assert not titulo.endswith("palab…")


def test_un_proyecto_de_ley_es_una_decision_por_su_tipo():
    """Regresión: la ley de Presupuestos no disparaba alerta.

    En Gobcan el acto de decisión está en el texto de la nota; en el Parlamento
    lo aporta el tipo de iniciativa, y el extracto no repite el verbo.
    """
    from datetime import date, datetime

    from transparencia_gobcan.alertas.clasificador import clasificar
    from transparencia_gobcan.modelos import Entrada, Fuente, OrigenEntradilla

    entrada = Entrada(
        id_fuente="11L/PL-0009", fuente=Fuente.PARLAMENTO, fecha_ext=datetime.now(),
        fecha_real=date(2025, 3, 1),
        titulo="Proyecto de ley: De medidas en materia de vivienda protegida",
        entrada="De medidas urgentes en materia de vivienda protegida.",
        entrada_origen=OrigenEntradilla.SUMARIO,
        url="https://www.parcan.es/iniciativas/tramites.py?id_iniciativa=11L/PL-0009",
        area="obras_publicas", tipo_iniciativa="PL",
    )
    resultado = clasificar(entrada)
    assert "iniciativa_parlamentaria" in resultado.actos
    assert resultado.es_alerta
