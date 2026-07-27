"""Conversión de iniciativas parlamentarias al modelo común.

Las iniciativas y las notas de prensa acaban en la misma tabla, pero llegan con
formas muy distintas. Aquí se salvan esas diferencias:

  - No hay título y entradilla separados: el extracto de la iniciativa hace de
    los dos. Se compone un título legible con el tipo y el extracto recortado.
  - El área no viene dada. Se toma de la comisión dictaminante cuando existe
    —dato publicado— y si no se deduce de las materias del extracto, marcándolo
    como inferido. Nunca se presenta una deducción como dato de la Cámara.
  - `grupo_parlamentario`, `tipo_iniciativa` y `situacion` sí tienen sitio
    propio en el modelo y se rellenan tal cual.
"""

from __future__ import annotations

import functools
import re
from datetime import date, datetime
from typing import Any

from ..alertas.clasificador import _patrones, normalizar
from ..config import cargar
from ..modelos import Entrada, Fuente, OrigenArea, OrigenEntradilla
from .areas import AREA_RESIDUAL
from .territorio import derivar_territorio

# Longitud del título compuesto: el extracto de una iniciativa puede ocupar un
# párrafo entero y no cabe como titular.
LONGITUD_TITULO = 150

# Nombre legible de cada tipo, para el título. Los códigos son opacos fuera del
# Parlamento y el equipo no tiene por qué saberse la nomenclatura.
NOMBRE_TIPO = {
    "PL": "Proyecto de ley",
    "PPL": "Proposición de ley",
    "PPLP": "Proposición de ley de iniciativa popular",
    "DL": "Decreto ley",
    "DLG": "Decreto legislativo",
    "PNLP": "Proposición no de ley en pleno",
    "PNLC": "Proposición no de ley en comisión",
    "M": "Moción",
    "I": "Interpelación",
    "CG": "Comunicación del Gobierno",
    "C/P": "Comparecencia en pleno",
    "C/C": "Comparecencia en comisión",
}


@functools.lru_cache(maxsize=1)
def _mapas() -> dict:
    cfg = cargar("areas")
    return {
        "comisiones": cfg.get("correspondencias_parcan_comisiones") or {},
        "materias": cfg.get("correspondencias_materia_area") or {},
        "grupos": {g["nombre"] for g in cfg.get("grupos_parlamentarios", [])},
    }


def derivar_area(comision: str | None, extracto: str) -> tuple[str, OrigenArea]:
    """Determina el área de una iniciativa y de dónde sale ese dato.

    Prioridad:
        1. Comisión dictaminante, que es un dato publicado por la Cámara.
        2. Materias detectadas en el extracto, que es una deducción nuestra.
        3. Área residual, visible al filtrar y vigilada en logs.
    """
    mapas = _mapas()

    if comision:
        clave = mapas["comisiones"].get(comision.strip())
        if clave:
            return clave, OrigenArea.PUBLICADO
        # Comisión conocida pero no sectorial (Reglamento, Cabildos...): no
        # designa área de gobierno, así que se sigue por el extracto.

    texto = normalizar(extracto)
    encontradas = [k for k, rx in _patrones()["materias"].items() if rx.search(texto)]
    for materia in encontradas:
        area = mapas["materias"].get(materia)
        if area:
            return area, OrigenArea.INFERIDO_TEXTO

    return AREA_RESIDUAL, OrigenArea.POR_DEFECTO


def componer_titulo(tipo: str, extracto: str) -> str:
    """Compone un titular legible a partir del tipo y el extracto.

    Muchos extractos empiezan por minúscula porque continúan el nombre del tipo
    ("De Presupuestos Generales...", "Por la que se modifica..."), así que el
    resultado se lee bien como "Proyecto de ley: De Presupuestos Generales...".
    """
    nombre = NOMBRE_TIPO.get(tipo, tipo)
    cuerpo = " ".join((extracto or "").split())
    if len(cuerpo) > LONGITUD_TITULO:
        corte = cuerpo[:LONGITUD_TITULO].rsplit(" ", 1)[0].rstrip(" ,;:-–—")
        cuerpo = f"{corte}…"
    return f"{nombre}: {cuerpo}" if cuerpo else nombre


def normalizar_grupo(proponentes: str | None) -> str | None:
    """Devuelve el grupo parlamentario si el proponente es uno de ellos.

    El campo también recoge órganos —"Pleno del Parlamento", "Gobierno de
    Canarias"—, que no son grupos y no deben acabar en `grupo_parlamentario`
    porque falsearían el filtro de la interfaz.
    """
    if not proponentes:
        return None
    valor = " ".join(proponentes.split())
    if valor in _mapas()["grupos"]:
        return valor
    # Varios grupos separados por coma o punto y coma en iniciativas conjuntas
    partes = [p.strip() for p in re.split(r"[;,]", valor) if p.strip()]
    reconocidos = [p for p in partes if p in _mapas()["grupos"]]
    if reconocidos:
        return ", ".join(reconocidos)
    return valor if valor.startswith("GP ") else None


def construir_entrada(cruda: dict[str, Any]) -> Entrada:
    """Convierte una iniciativa cruda en una `Entrada` validada."""
    fecha = cruda.get("fecha_creacion")
    if not fecha:
        raise ValueError(f"iniciativa {cruda.get('codigo')} sin fecha de creación legible")
    fecha_real = date(*fecha)

    extracto = " ".join((cruda.get("extracto") or "").split())
    titulo = componer_titulo(cruda.get("tipo", ""), extracto)
    area, area_origen = derivar_area(cruda.get("comision"), extracto)
    territorio, territorio_origen = derivar_territorio(titulo, extracto)

    # La situación de la ficha manda sobre la del listado: es más específica.
    situacion = cruda.get("situacion") or cruda.get("situacion_listado")
    if cruda.get("resultado"):
        situacion = f"{situacion} · {cruda['resultado']}" if situacion else cruda["resultado"]

    subareas: list[str] = []
    if cruda.get("comision"):
        subareas.append(cruda["comision"])
    if cruda.get("a_instancias_de"):
        subareas.append(f"A instancias de {cruda['a_instancias_de']}")

    return Entrada(
        id_fuente=cruda["codigo"],
        fuente=Fuente.PARLAMENTO,
        fecha_ext=datetime.now(),
        fecha_real=fecha_real,
        titulo=titulo,
        entrada=extracto,
        # El extracto es el texto que publica la Cámara, no una construcción
        # nuestra: equivale al sumario editorial de una nota de prensa.
        entrada_origen=OrigenEntradilla.SUMARIO,
        url=cruda["url"],
        area=area,
        area_origen=area_origen,
        areas=subareas,
        territorio=territorio,
        territorio_origen=territorio_origen,
        grupo_parlamentario=normalizar_grupo(cruda.get("proponentes")),
        tipo_iniciativa=cruda.get("tipo"),
        situacion=situacion,
    )
