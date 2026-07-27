"""Modelo de datos de la herramienta.

Define la forma de una entrada capturada y de un registro de ejecución. Toda
entrada pasa por `Entrada` antes de llegar a Supabase: si no valida, no se carga
y el motivo queda escrito en la tabla de logs.

Decisiones de diseño que vienen del reconocimiento de las fuentes (Hito 1):

- `entrada` (la entradilla) se construye a partir del sumario editorial del
  cuerpo, no del campo `excerpt` de la fuente, que llega truncado a mitad de
  palabra. El cuerpo se procesa en memoria y no se persiste.
- `area` usa el vocabulario cerrado de `config/areas.yaml`, alineado con la
  herramienta de cargos políticos. Nunca es nulo: hay un valor residual explícito.
- `territorio` casi nunca viene publicado, así que se deriva del texto. Por eso
  existe `territorio_origen`: una inferencia nuestra no puede presentarse como
  un dato de la fuente.
- `hash_dedup` da idempotencia. Reejecutar la extracción no duplica entradas.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator

# Fecha de arranque del observatorio y de la XI legislatura. Una entrada anterior
# indica un fallo de parseo de fecha, no una noticia antigua legítima.
FECHA_MINIMA = date(2023, 5, 1)


class Fuente(StrEnum):
    """Origen institucional de la entrada."""

    GOBIERNO = "gobierno"
    PARLAMENTO = "parlamento"


class OrigenTerritorio(StrEnum):
    """Procedencia del campo `territorio`, para no confundir dato con inferencia."""

    PUBLICADO = "publicado"      # la fuente lo trae como campo
    INFERIDO_TEXTO = "inferido"  # lo hemos derivado del título o la entradilla
    POR_DEFECTO = "defecto"      # sin mención concreta: se asume ámbito canario


class OrigenArea(StrEnum):
    """Procedencia del campo `area`, por el mismo motivo que en el territorio.

    En Gobcan siempre es publicado: el área sale de la categoría que asigna el
    portal. En Parcan solo lo es cuando la iniciativa pasa por comisión, porque
    entonces hay comisión dictaminante; las proposiciones no de ley en pleno no
    la tienen y su área se deduce del extracto.
    """

    PUBLICADO = "publicado"      # categoría de Gobcan o comisión dictaminante
    INFERIDO_TEXTO = "inferido"  # deducido del extracto
    POR_DEFECTO = "defecto"      # sin señal: queda en el área residual


class OrigenEntradilla(StrEnum):
    """Nivel de la cascada de extracción del que salió la entradilla.

    Se registra para vigilar si el gabinete cambia de práctica editorial: una
    caída brusca de `sumario` avisa de que hay que revisar el extractor.
    """

    SUMARIO = "sumario"            # <blockquote> de apertura: el caso bueno
    PRIMER_PARRAFO = "parrafo"     # primer párrafo del cuerpo, cortado por frase
    EXCERPT = "excerpt"            # campo de la fuente, saneado; último recurso


class Entrada(BaseModel):
    """Una publicación capturada de cualquiera de las dos fuentes."""

    # --- Identificación ---
    id_fuente: str = Field(description="Identificador en origen: id de WordPress o código de iniciativa")
    fuente: Fuente
    hash_dedup: str = Field(default="", description="Clave de deduplicación; se calcula sola")

    # --- Fechas ---
    fecha_ext: datetime = Field(description="Momento de la extracción")
    fecha_real: date = Field(description="Fecha de publicación en origen")
    fecha_modificacion: datetime | None = Field(
        default=None, description="Última edición en origen, si la fuente la expone"
    )

    # --- Contenido ---
    titulo: str = Field(min_length=5)
    # Mínimo 5, no 20: el extracto de una iniciativa parlamentaria puede ser
    # legítimamente muy breve ("La DANA.", "Salud Mental."). El umbral solo
    # busca descartar campos vacíos, no extractos cortos pero válidos.
    entrada: str = Field(min_length=5, description="Entradilla de 2-3 líneas o extracto")
    entrada_origen: OrigenEntradilla
    url: HttpUrl

    # --- Clasificación ---
    area: str = Field(description="Clave del vocabulario cerrado de config/areas.yaml")
    areas: list[str] = Field(default_factory=list, description="Subáreas o áreas secundarias")
    area_origen: OrigenArea = OrigenArea.PUBLICADO
    territorio: str = Field(default="Canarias")
    territorio_origen: OrigenTerritorio = OrigenTerritorio.POR_DEFECTO

    # --- Solo Parlamento ---
    grupo_parlamentario: str | None = None
    tipo_iniciativa: str | None = Field(default=None, description="Código: PNLP, PL, DL...")
    situacion: str | None = Field(default=None, description="En trámite / cerrada")

    # --- Capa semántica de alertas ---
    es_alerta: bool = False
    motivo_alerta: str | None = None
    materias: list[str] = Field(default_factory=list)
    actos: list[str] = Field(default_factory=list)
    notificada_en: datetime | None = None

    @field_validator("titulo", "entrada")
    @classmethod
    def sin_espacios_sobrantes(cls, v: str) -> str:
        """Normaliza el espaciado: la fuente trae saltos y espacios dobles del HTML."""
        return " ".join(v.split())

    @field_validator("fecha_real")
    @classmethod
    def fecha_en_rango(cls, v: date) -> date:
        """Rechaza fechas imposibles.

        Una fecha futura o anterior al arranque del observatorio casi siempre
        significa que el parseo falló, no que la noticia sea de 1998.
        """
        if v < FECHA_MINIMA:
            raise ValueError(f"fecha_real {v} anterior al inicio del periodo ({FECHA_MINIMA})")
        if v > date.today():
            raise ValueError(f"fecha_real {v} en el futuro")
        return v

    @model_validator(mode="after")
    def calcular_hash(self) -> Entrada:
        """Calcula la clave de deduplicación si no venía dada.

        Se construye sobre fuente + identificador de origen, que son estables:
        usar el título rompería la idempotencia en cuanto corrigen una errata.
        """
        if not self.hash_dedup:
            semilla = f"{self.fuente.value}:{self.id_fuente}"
            object.__setattr__(self, "hash_dedup", hashlib.sha256(semilla.encode()).hexdigest()[:32])
        return self


class MotivoDescarte(StrEnum):
    """Por qué se descartó una fila. La tabla de logs guarda el motivo, no solo el conteo."""

    CATEGORIA_EXCLUIDA = "categoria_excluida"      # 112 y avisos meteorológicos
    ENTRADILLA_VACIA = "entradilla_vacia"
    FECHA_FUERA_RANGO = "fecha_fuera_rango"
    TITULO_VACIO = "titulo_vacio"
    URL_INVALIDA = "url_invalida"
    DUPLICADO_EN_LOTE = "duplicado_en_lote"
    ERROR_VALIDACION = "error_validacion"


class RegistroEjecucion(BaseModel):
    """Un registro de la tabla de logs.

    Existe para aprender de los fallos del extractor, así que guarda el detalle
    de los descartes y de las anomalías, no un simple recuento de filas.
    """

    inicio: datetime
    fin: datetime | None = None
    fuente: Fuente
    modo: str = Field(description="historico | incremental | respaldo")

    filas_leidas: int = 0
    filas_insertadas: int = 0
    filas_actualizadas: int = 0
    filas_descartadas: int = 0

    descartes_por_motivo: dict[str, int] = Field(default_factory=dict)
    entradillas_por_origen: dict[str, int] = Field(default_factory=dict)
    anomalias: list[str] = Field(default_factory=list)
    errores: list[str] = Field(default_factory=list)

    exito: bool = True
    version_extractor: str = "0.1.0"

    def anotar_descarte(self, motivo: MotivoDescarte, detalle: str = "") -> None:
        """Registra un descarte con su motivo y, si lo hay, el detalle concreto."""
        self.filas_descartadas += 1
        self.descartes_por_motivo[motivo.value] = self.descartes_por_motivo.get(motivo.value, 0) + 1
        if detalle:
            self.anomalias.append(f"{motivo.value}: {detalle}")
