"""Interfaz de línea de comandos.

Punto de entrada único del pipeline, tanto en local como en GitHub Actions.
Cada subcomando corresponde a una operación completa y trazable.

    transparencia extraer --modo incremental
    transparencia extraer --modo historico --desde 2023-05-01
    transparencia validar-config
    transparencia clasificar --recalcular

Pendiente de implementación en el Hito 3.
"""

from __future__ import annotations

import typer

app = typer.Typer(
    help="Seguimiento de la actividad ejecutiva y parlamentaria de Canarias · ODESOCAN",
    no_args_is_help=True,
)


@app.command()
def extraer(
    fuente: str = typer.Option("gobcan", help="Fuente a extraer: gobcan | parcan"),
    modo: str = typer.Option("incremental", help="incremental | historico | respaldo"),
    desde: str | None = typer.Option(None, help="Fecha inicial en formato AAAA-MM-DD"),
    hasta: str | None = typer.Option(None, help="Fecha final en formato AAAA-MM-DD"),
    simular: bool = typer.Option(False, "--simular", help="Extrae y valida, pero no carga"),
) -> None:
    """Ejecuta el pipeline completo: extracción, transformación, validación y carga."""
    raise NotImplementedError("Hito 3")


@app.command("validar-config")
def validar_config() -> None:
    """Comprueba la coherencia de los ficheros de configuración.

    Verifica que las correspondencias de áreas apunten a claves existentes, que
    los patrones de alertas compilen como expresiones regulares y que las
    categorías declaradas sigan existiendo en la fuente.
    """
    raise NotImplementedError("Hito 3")


@app.command()
def clasificar(
    recalcular: bool = typer.Option(False, help="Reaplica la capa semántica al histórico"),
) -> None:
    """Aplica la capa semántica de alertas.

    Con `--recalcular` reevalúa las entradas ya cargadas, que es lo que hay que
    hacer cada vez que se amplíe el vocabulario de `config/alertas.yaml`.
    """
    raise NotImplementedError("Hito 3")


if __name__ == "__main__":
    app()
