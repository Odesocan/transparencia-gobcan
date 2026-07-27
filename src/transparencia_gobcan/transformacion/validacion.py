"""Reglas de calidad previas a la carga.

Nada llega a Supabase sin pasar por aquí. Cuando una fila se descarta, lo que
interesa registrar es el MOTIVO, no el recuento: la tabla de logs existe para
aprender de los fallos del extractor.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from ..alertas.clasificador import clasificar
from ..modelos import Entrada, Fuente, MotivoDescarte, RegistroEjecucion
from .areas import AREA_RESIDUAL, detectar_categorias_nuevas, esta_excluida, normalizar_area
from .entradilla import extraer_entradilla, limpiar_html
from .territorio import derivar_territorio

log = logging.getLogger(__name__)

# Umbrales de degradación silenciosa. Un extractor roto rara vez lanza una
# excepción: sigue devolviendo filas, solo que peores. Ver docs/puntos-de-rotura.md.
UMBRAL_SUMARIOS_MINIMO = 0.30
UMBRAL_SIN_AREA_MAXIMO = 0.20
UMBRAL_DESCARTES_MAXIMO = 0.05


def construir_entrada(crudo: dict[str, Any], catalogo: dict[int, dict] | None = None) -> Entrada:
    """Convierte un registro crudo de la API en una `Entrada` validada.

    Aquí es donde el cuerpo de la noticia se usa y se descarta: `content` entra
    para extraer la entradilla y no sale de esta función.
    """
    fecha_real = datetime.fromisoformat(crudo["date"]).date()
    ids_categoria = crudo.get("categories") or []

    entradilla, origen_entradilla = extraer_entradilla(
        (crudo.get("content") or {}).get("rendered", ""),
        (crudo.get("excerpt") or {}).get("rendered", ""),
    )
    titulo = limpiar_html((crudo.get("title") or {}).get("rendered", ""))
    area, subareas = normalizar_area(ids_categoria, fecha_real, catalogo)
    territorio, origen_territorio = derivar_territorio(titulo, entradilla)

    modificacion = crudo.get("modified")
    return Entrada(
        id_fuente=str(crudo["id"]),
        fuente=Fuente.GOBIERNO,
        fecha_ext=datetime.now(),
        fecha_real=fecha_real,
        fecha_modificacion=datetime.fromisoformat(modificacion) if modificacion else None,
        titulo=titulo,
        entrada=entradilla,
        entrada_origen=origen_entradilla,
        url=crudo["link"],
        area=area,
        areas=subareas,
        territorio=territorio,
        territorio_origen=origen_territorio,
    )


def validar_lote(
    crudos: list[dict[str, Any]],
    registro: RegistroEjecucion,
    catalogo: dict[int, dict] | None = None,
) -> tuple[list[Entrada], RegistroEjecucion]:
    """Valida un lote y devuelve solo las entradas aptas para cargar.

    Comprueba nulos, entradillas vacías, fechas fuera de rango, URLs mal
    formadas y duplicados dentro del propio lote. Cada descarte se anota en el
    registro con su motivo y su detalle.
    """
    validas: list[Entrada] = []
    hashes_vistos: set[str] = set()
    registro.filas_leidas = len(crudos)

    for crudo in crudos:
        identificador = crudo.get("id", "?")

        # Red de seguridad: la exclusión principal se hace en origen, pero si la
        # fuente cambiara los identificadores conviene descartar aquí y dejar
        # constancia del motivo en vez de cargar partes del 112.
        exclusion = esta_excluida(crudo.get("categories") or [])
        if exclusion:
            registro.anotar_descarte(
                MotivoDescarte.CATEGORIA_EXCLUIDA, f"id {identificador}: {exclusion['etiqueta']}"
            )
            continue

        try:
            entrada = construir_entrada(crudo, catalogo)
        except ValidationError as e:
            motivo = _motivo_desde_error(e)
            registro.anotar_descarte(motivo, f"id {identificador}: {_resumir_error(e)}")
            continue
        except (KeyError, ValueError, TypeError) as e:
            registro.anotar_descarte(
                MotivoDescarte.ERROR_VALIDACION, f"id {identificador}: {type(e).__name__} {e}"
            )
            continue

        if entrada.hash_dedup in hashes_vistos:
            registro.anotar_descarte(MotivoDescarte.DUPLICADO_EN_LOTE, f"id {identificador}")
            continue
        hashes_vistos.add(entrada.hash_dedup)

        validas.append(clasificar(entrada))

    # Distribución de la cascada de entradillas, para vigilar su salud
    for entrada in validas:
        clave = entrada.entrada_origen.value
        registro.entradillas_por_origen[clave] = registro.entradillas_por_origen.get(clave, 0) + 1

    return validas, registro


def _motivo_desde_error(error: ValidationError) -> MotivoDescarte:
    """Traduce un error de pydantic al motivo de descarte que le corresponde."""
    campos = {str(e["loc"][0]) if e["loc"] else "" for e in error.errors()}
    if "fecha_real" in campos:
        return MotivoDescarte.FECHA_FUERA_RANGO
    if "entrada" in campos:
        return MotivoDescarte.ENTRADILLA_VACIA
    if "titulo" in campos:
        return MotivoDescarte.TITULO_VACIO
    if "url" in campos:
        return MotivoDescarte.URL_INVALIDA
    return MotivoDescarte.ERROR_VALIDACION


def _resumir_error(error: ValidationError) -> str:
    return "; ".join(f"{'.'.join(str(x) for x in e['loc'])}: {e['msg']}" for e in error.errors()[:3])


def detectar_anomalias(
    entradas: list[Entrada],
    registro: RegistroEjecucion,
    ids_categoria_vistos: set[int] | None = None,
    catalogo: dict[int, dict] | None = None,
) -> RegistroEjecucion:
    """Busca señales de que el extractor se está degradando sin fallar.

    Un extractor roto rara vez lanza una excepción: sigue devolviendo filas, solo
    que peores. Las señales que vigilamos:
        - caída del porcentaje de entradillas obtenidas del sumario;
        - subida del porcentaje de entradas con área residual;
        - proporción alta de descartes;
        - categorías nuevas sin correspondencia en la configuración.
    """
    total = len(entradas)
    if total:
        sumarios = registro.entradillas_por_origen.get("sumario", 0) / total
        if sumarios < UMBRAL_SUMARIOS_MINIMO:
            registro.anomalias.append(
                f"Solo el {sumarios:.0%} de las entradillas viene del sumario editorial "
                f"(umbral {UMBRAL_SUMARIOS_MINIMO:.0%}): revisar si cambió la plantilla del gabinete"
            )

        sin_area = sum(1 for e in entradas if e.area == AREA_RESIDUAL) / total
        if sin_area > UMBRAL_SIN_AREA_MAXIMO:
            registro.anomalias.append(
                f"El {sin_area:.0%} de las entradas queda sin área asignada "
                f"(umbral {UMBRAL_SIN_AREA_MAXIMO:.0%}): revisar config/areas.yaml"
            )

    if registro.filas_leidas:
        descartes = registro.filas_descartadas / registro.filas_leidas
        if descartes > UMBRAL_DESCARTES_MAXIMO:
            registro.anomalias.append(
                f"Se descarta el {descartes:.0%} de lo leído "
                f"(umbral {UMBRAL_DESCARTES_MAXIMO:.0%}): revisar la estructura de la fuente"
            )

    nuevas = detectar_categorias_nuevas(ids_categoria_vistos or set(), catalogo)
    if nuevas:
        etiquetas = [
            f"{cid} ({(catalogo or {}).get(cid, {}).get('nombre', '?')})" for cid in sorted(nuevas)
        ][:12]
        registro.anomalias.append(
            f"{len(nuevas)} categorías sin correspondencia en config/areas.yaml: {', '.join(etiquetas)}"
        )

    for anomalia in registro.anomalias:
        log.warning("Anomalía: %s", anomalia)
    return registro
