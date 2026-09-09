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


# ---------------------------------------------------------------------------
# Etiquetas temáticas de la interfaz. Es un tercer vocabulario, distinto del de
# alertas y del de clasificación por área, y por la misma razón que aquellos dos
# ya estaban separados: resuelve otro problema. Ver config/etiquetas_tematicas.yaml.
# ---------------------------------------------------------------------------
def _patron_etiqueta(clave):
    cfg = cargar("etiquetas_tematicas")
    for e in cfg["etiquetas"]:
        if e["clave"] == clave:
            return re.compile(e["patron"], re.VERBOSE)
    pytest.fail(f"No existe la etiqueta {clave!r}")


def test_las_etiquetas_declaran_grupo_y_color_conocidos():
    """Un grupo o un color inventado deja el distintivo sin estilo en la página."""
    cfg = cargar("etiquetas_tematicas")
    grupos = {g["clave"] for g in cfg["grupos"]}
    familias = {"teal", "verde", "ambar", "rojo", "azul", "violeta", "naranja", "navy"}
    for e in cfg["etiquetas"]:
        assert e["grupo"] in grupos, f"{e['clave']} apunta al grupo inexistente {e['grupo']!r}"
        assert e["color"] in familias, f"{e['clave']} usa la familia desconocida {e['color']!r}"


def test_no_hay_claves_de_etiqueta_repetidas():
    """Dos etiquetas con la misma clave harían impredecible el filtro y el enlace."""
    claves = [e["clave"] for e in cargar("etiquetas_tematicas")["etiquetas"]]
    assert len(claves) == len(set(claves)), "Hay claves de etiqueta repetidas"


@pytest.mark.parametrize(
    "clave, termino",
    [
        # Las siete que pedía el encargo, cada una con su término más típico
        ("vivienda", "construccion de vivienda protegida y alquiler asequible"),
        ("sanidad", "listas de espera en atencion primaria"),
        ("salud_mental", "unidad de salud mental infanto-juvenil"),
        ("dependencia", "grado de dependencia y ayuda a domicilio"),
        ("discapacidad", "personas con discapacidad y accesibilidad universal"),
        ("economia", "tejido empresarial e industria de canarias"),
        ("empleo", "convenio colectivo y siniestralidad laboral"),
        # Y el resto del vocabulario
        ("mayores", "personas mayores y soledad no deseada"),
        ("infancia_familias", "menores y familias monoparentales"),
        ("servicios_sociales", "renta canaria de ciudadania y exclusion social"),
        ("pobreza", "riesgo de exclusion y banco de alimentos"),
        ("educacion", "el profesorado y el alumnado de formacion profesional"),
        ("igualdad_violencia", "victimas de violencia machista"),
        ("migraciones", "menores no acompanados y solicitudes de asilo"),
        ("territorio_aguas", "desaladora y ciclo del agua"),
        ("medio_ambiente", "energias renovables y cambio climatico"),
        ("movilidad", "transporte publico y guaguas"),
        ("agricultura_pesca", "ganaderia y sector primario"),
        ("turismo", "plazas alojativas y promocion turistica"),
        ("cultura_deporte", "patrimonio historico y deportistas"),
        ("seguridad_emergencias", "proteccion civil y bomberos"),
        ("administracion_justicia", "funcion publica y oposiciones"),
    ],
)
def test_cada_etiqueta_encuentra_su_termino_caracteristico(clave, termino):
    """Comprobar que el patrón compila no basta: hay que comprobar que encuentra.

    Es el mismo fallo que ya se ha dado dos veces en este repositorio —el plural
    de "violencias machistas" y el `naturales?` que no casa "natural"— y que se
    reconoce porque el patrón no da ningún error y simplemente no devuelve nada.
    """
    assert _patron_etiqueta(clave).search(termino), f"{clave!r} no detecta {termino!r}"


@pytest.mark.parametrize(
    "clave, falso_amigo, veces",
    [
        # Los tres los midió el auditor sobre las 16.044 entradas del volcado.
        # Los tres compilaban y parecían correctos.
        ("empleo", "la comunidad autonoma de canarias aprueba", 326),
        ("educacion", "el hospital universitario de gran canaria doctor negrin", 388),
        ("dependencia", "la unidad de continuidad de cuidados del hospital", 219),
    ],
)
def test_las_etiquetas_no_casan_sus_falsos_amigos(clave, falso_amigo, veces):
    """Regresión de los tres falsos positivos que obligaron a rehacer el vocabulario.

    `autonom[oa]s?` casaba "Comunidad Autónoma" y metía media administración en
    el filtro de empleo. `universitari[oa]s?` casaba "Hospital Universitario" y
    etiquetaba de educación toda la sanidad hospitalaria. `cuidados` a secas
    casaba una unidad clínica que no tiene que ver con la dependencia.
    """
    assert not _patron_etiqueta(clave).search(falso_amigo), (
        f"{clave!r} vuelve a casar {falso_amigo!r}, que disparaba {veces} veces de más"
    )


def test_las_etiquetas_se_solapan():
    """El solapamiento no es un efecto colateral: es lo que se pidió.

    Una entrada sobre vivienda adaptada tiene que salir tanto al filtrar por
    vivienda como al filtrar por discapacidad. Si el vocabulario dejara de
    solaparse, el filtro por área seguiría funcionando y devolvería menos.
    """
    from transparencia_gobcan.transformacion.etiquetas import etiquetar

    puestas = etiquetar(
        "El Gobierno destina cuatro millones a viviendas adaptadas",
        "Las obras beneficiarán a personas con discapacidad en situación de dependencia.",
    )
    assert {"vivienda", "discapacidad", "dependencia"} <= set(puestas)
