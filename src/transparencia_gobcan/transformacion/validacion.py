"""Reglas de calidad previas a la carga.

Nada llega a Supabase sin pasar por aquí. Cuando una fila se descarta, lo que
interesa registrar es el MOTIVO, no el recuento: la tabla de logs existe para
aprender de los fallos del extractor.

Pendiente de implementación en el Hito 3.
"""

from __future__ import annotations

from typing import Any

from ..modelos import Entrada, RegistroEjecucion


def validar_lote(
    crudos: list[dict[str, Any]], registro: RegistroEjecucion
) -> tuple[list[Entrada], RegistroEjecucion]:
    """Valida un lote y devuelve solo las entradas aptas para cargar.

    Comprueba nulos, entradillas vacías, fechas fuera de rango, URLs mal
    formadas y duplicados dentro del propio lote. Cada descarte se anota en el
    registro con su motivo y su detalle.
    """
    raise NotImplementedError("Hito 3")


def detectar_anomalias(entradas: list[Entrada], registro: RegistroEjecucion) -> RegistroEjecucion:
    """Busca señales de que el extractor se está degradando sin fallar.

    Un extractor roto rara vez lanza una excepción: sigue devolviendo filas, solo
    que peores. Las señales que vigilamos:
        - caída del porcentaje de entradillas obtenidas del sumario;
        - subida del porcentaje de entradas con área `sin_asignar`;
        - volumen diario muy por debajo de lo esperado (referencia: ~15/día);
        - categorías nuevas sin correspondencia en la configuración.
    """
    raise NotImplementedError("Hito 3")
