"""Contrato de la capa semántica de alertas.

Los casos vienen de la validación empírica sobre 1.000 entradas reales
(27/04-27/07 de 2026), incluidos los dos falsos positivos que obligaron a
rehacer el vocabulario.
"""

from __future__ import annotations

import pytest

pendiente = pytest.mark.xfail(raises=NotImplementedError, reason="Se implementa en el Hito 3")


@pytest.mark.parametrize(
    "titulo, entradilla",
    [
        ("Canarias aprueba la ley que agiliza las licencias urbanísticas y la construcción de viviendas", ""),
        ("Bienestar Social destina 3,5 millones de euros a subvenciones para personas mayores", ""),
        ("La Gerencia Sanitaria de Lanzarote saca a licitación las obras de ampliación del consultorio", ""),
        # Este dispara por la entradilla, no por el titular: el acto está en
        # "Pacto de Estado". Se conserva el texto real de la fuente porque el
        # clasificador lee título Y entradilla, y probarlo solo con el título
        # daría una idea equivocada de lo que detecta.
        (
            "Canarias consolida la red integral de protección frente a violencias machistas",
            "Candelaria Delgado y Ana Padrón hacen balance del trabajo del Instituto Canario de "
            "Igualdad destacando los cinco Centros de Crisis 24 horas y la justificación de los "
            "fondos del Pacto de Estado",
        ),
    ],
)
def test_notifica_las_decisiones_sobre_materias_vigiladas(titulo, entradilla):
    from transparencia_gobcan.alertas.clasificador import clasificar

    assert clasificar(_entrada(titulo, entradilla)).es_alerta


def test_el_titular_solo_no_basta_si_no_hay_acto():
    """Documenta un límite real: sin acto de decisión, la materia sola no dispara.

    "consolida la red de protección" es una acción de gobierno, pero añadir
    verbos genéricos (consolida, refuerza, impulsa, amplía) al vocabulario sube
    el volumen un 37% metiendo actividad asistencial ordinaria: "realiza 7.000
    ecografías", "amplía el horario del punto de donación". Medido sobre 1.000
    entradas reales. Se prefiere perder este caso a ganar ese ruido.
    """
    from transparencia_gobcan.alertas.clasificador import clasificar

    entrada = clasificar(
        _entrada("Canarias consolida la red integral de protección frente a violencias machistas")
    )
    assert entrada.materias == ["violencia_genero"]
    assert not entrada.actos
    assert not entrada.es_alerta


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


def test_una_mencion_propia_notifica_siempre():
    """Si nos citan, se avisa aunque no haya decisión ni materia."""
    from transparencia_gobcan.alertas.clasificador import clasificar

    entrada = clasificar(_entrada("El Gobierno se reúne con ODESOCAN y ACUFADE"))
    assert entrada.es_alerta
    assert entrada.motivo_alerta == "entidad_propia"


def test_detecta_violencia_de_genero_en_plural():
    """Regresión: la fuente escribe "violencias machistas", no "violencia machista"."""
    from transparencia_gobcan.alertas.clasificador import clasificar

    entrada = clasificar(
        _entrada("El Gobierno aprueba el plan contra las violencias machistas en Canarias")
    )
    assert "violencia_genero" in entrada.materias


def _entrada(titulo: str, entradilla: str = ""):
    """Construye una entrada mínima para probar solo la clasificación."""
    from datetime import date, datetime

    from transparencia_gobcan.modelos import Entrada, Fuente, OrigenEntradilla

    return Entrada(
        id_fuente="1", fuente=Fuente.GOBIERNO, fecha_ext=datetime.now(),
        fecha_real=date(2026, 7, 1), titulo=titulo,
        entrada=entradilla or "Entradilla de prueba con longitud suficiente para validar.",
        entrada_origen=OrigenEntradilla.SUMARIO,
        url="https://www3.gobiernodecanarias.org/noticias/x/", area="sanidad",
    )


# ---------------------------------------------------------------------------
# Composición del correo
# ---------------------------------------------------------------------------
def test_la_fecha_del_asunto_va_en_espanol():
    """Regresión: strftime('%B') da "July" en el runner de GitHub Actions.

    Es el mismo motivo por el que las fechas de Parcan se parsean a mano: el
    runner arranca en inglés y puede no tener el locale es_ES instalado.
    """
    from datetime import date

    from transparencia_gobcan.alertas.correo import fecha_larga

    assert fecha_larga(date(2026, 7, 27)) == "27 de julio"
    assert fecha_larga(date(2026, 1, 1)) == "1 de enero"
    assert fecha_larga(date(2026, 12, 31)) == "31 de diciembre"


def test_el_correo_dice_quien_impulsa_segun_la_fuente():
    """En el Gobierno es la consejería; en el Parlamento, el grupo proponente."""
    from transparencia_gobcan.alertas.correo import _quien_impulsa

    gobierno = {"fuente": "gobierno", "area": "sanidad", "grupo_parlamentario": None}
    assert "Sanidad" in _quien_impulsa(gobierno)

    parlamento = {"fuente": "parlamento", "area": "vivienda",
                  "grupo_parlamentario": "GP Socialista Canario"}
    assert _quien_impulsa(parlamento) == "GP Socialista Canario"

    # Un proyecto de ley lo presenta el Gobierno y no tiene grupo: se dice así
    # en vez de dejarlo en blanco.
    del_gobierno = {"fuente": "parlamento", "area": "hacienda", "grupo_parlamentario": None}
    assert _quien_impulsa(del_gobierno) == "Iniciativa del Gobierno"


def test_el_correo_escapa_el_html_de_la_fuente():
    """Los títulos vienen de fuera: no pueden inyectar marcado en el correo."""
    from transparencia_gobcan.alertas.correo import componer_html

    fila = {
        "fuente": "gobierno", "fecha_real": "2026-07-27", "area": "sanidad",
        "titulo": '<script>alert("x")</script> Titular',
        "entrada": "Entradilla de prueba.", "url": "https://ejemplo.org/",
        "territorio": "Canarias", "materias": ["sanidad"],
        "grupo_parlamentario": None, "situacion": None,
    }
    html = componer_html([fila])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
