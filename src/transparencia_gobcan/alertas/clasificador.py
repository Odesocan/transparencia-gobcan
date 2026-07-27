"""Capa semántica: decide qué entradas merecen notificación.

No todo lo capturado se notifica. Interesan las decisiones del ejecutivo y del
legislativo sobre iniciativas políticas, y las menciones a entidades que
seguimos. El vocabulario vive en `config/alertas.yaml`.

Medido sobre 1.000 entradas reales (27/04-27/07 de 2026): reduce de 11,0 a
1,7 entradas al día, un 16% del total.

Dos lecciones del ajuste, que conviene no perder:

  - La fuente alterna singular y plural, y publica "violencias machistas", no
    "violencia machista". Cotejar la forma exacta dejaba fuera las 354 entradas
    sobre violencia de género publicadas desde mayo de 2023. Por eso el
    vocabulario usa raíces con variantes, no palabras cerradas.

  - Un municipio en el texto suele ser el LUGAR donde ocurre algo, no la
    institución que decide. Cotejar el topónimo a secas disparaba 154 alertas
    falsas de 292. Los cabildos y ayuntamientos solo cuentan cuando aparecen
    como institución actuante, y aun así necesitan una materia.

Pendiente de implementación en el Hito 3.
"""

from __future__ import annotations

from ..modelos import Entrada


def normalizar(texto: str) -> str:
    """Pasa a minúsculas y quita tildes, para que el cotejo no dependa de la acentuación."""
    raise NotImplementedError("Hito 3")


def clasificar(entrada: Entrada) -> Entrada:
    """Marca la entrada con su motivo de alerta, materias y actos detectados.

    Reglas de disparo, en orden:
        1. Mención propia (ODESOCAN, ACUFADE, AFFA) -> alerta siempre.
        2. Acto de decisión + materia vigilada -> alerta.
        3. Cabildo o ayuntamiento actuante + materia -> alerta.
    """
    raise NotImplementedError("Hito 3")
