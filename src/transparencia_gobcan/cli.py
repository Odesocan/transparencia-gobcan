"""Interfaz de línea de comandos.

Punto de entrada único del pipeline, tanto en local como en GitHub Actions.
Cada subcomando corresponde a una operación completa y trazable.

    transparencia extraer --modo incremental
    transparencia extraer --modo historico --desde 2023-05-01
    transparencia extraer --simular
    transparencia validar-config
"""

from __future__ import annotations

import logging
import pathlib
import re
from datetime import date, datetime, timedelta

import typer
from rich.console import Console
from rich.table import Table

from .config import cargar, entorno
from .modelos import Fuente

app = typer.Typer(
    help="Seguimiento de la actividad ejecutiva y parlamentaria de Canarias · ODESOCAN",
    no_args_is_help=True,
)
consola = Console()

# Inicio de la XI legislatura y del propio observatorio
FECHA_INICIO = date(2023, 5, 1)


def _configurar_registro() -> None:
    logging.basicConfig(
        level=entorno("NIVEL_LOG", "INFO"),
        format="%(asctime)s  %(levelname)-7s %(name)s · %(message)s",
        datefmt="%H:%M:%S",
    )


def _fecha(texto: str | None) -> datetime | None:
    if not texto:
        return None
    try:
        return datetime.fromisoformat(texto)
    except ValueError:
        consola.print(f"[red]Fecha no válida: {texto!r}. Formato esperado AAAA-MM-DD.[/red]")
        raise typer.Exit(1) from None


@app.command()
def extraer(
    fuente: str = typer.Option("gobcan", help="Fuente a extraer: gobcan | parcan"),
    modo: str = typer.Option("incremental", help="incremental | historico"),
    desde: str | None = typer.Option(None, help="Fecha inicial en formato AAAA-MM-DD"),
    hasta: str | None = typer.Option(None, help="Fecha final en formato AAAA-MM-DD"),
    simular: bool = typer.Option(False, "--simular", help="Extrae y valida, pero no carga"),
) -> None:
    """Ejecuta el pipeline completo: extracción, transformación, validación y carga."""
    _configurar_registro()

    if fuente != "gobcan":
        consola.print(f"[yellow]La fuente {fuente!r} todavía no está implementada.[/yellow]")
        raise typer.Exit(1)

    from .carga.logs import abrir_registro, cerrar_registro
    from .extraccion.gobcan_api import descargar_categorias, descargar_entradas
    from .transformacion.validacion import detectar_anomalias, validar_lote

    if modo == "historico":
        inicio = _fecha(desde) or datetime.combine(FECHA_INICIO, datetime.min.time())
    else:
        horas = int(entorno("VENTANA_INCREMENTAL_HORAS", "24"))
        inicio = _fecha(desde) or (datetime.now() - timedelta(hours=horas))

    # Sin esto, dos ejecuciones solapadas duplican las peticiones a la fuente y
    # compiten por el mismo UPSERT. Ya ocurrió una vez: dos cargas históricas
    # con 27 segundos de diferencia, 30.000 peticiones donde bastaban 15.000.
    # La idempotencia salvó los datos, pero el desperdicio es real y la fuente
    # es pública: conviene no abusar. El workflow de Actions ya lo evita con
    # `concurrency`; esto cubre la ejecución en local.
    cerrojo = _tomar_cerrojo(simular)

    registro = abrir_registro(Fuente.GOBIERNO, modo)
    consola.print(
        f"[bold]Extrayendo[/bold] de gobcan · modo {modo} · desde {inicio:%Y-%m-%d %H:%M}"
        + (" · [yellow]simulación[/yellow]" if simular else "")
    )

    try:
        catalogo = descargar_categorias()
        crudos = list(
            descargar_entradas(desde=inicio, hasta=_fecha(hasta), incremental=(modo != "historico"))
        )
        consola.print(f"  entradas descargadas: [cyan]{len(crudos)}[/cyan]")

        ids_vistos = {cid for c in crudos for cid in (c.get("categories") or [])}
        entradas, registro = validar_lote(crudos, registro, catalogo)
        registro = detectar_anomalias(entradas, registro, ids_vistos, catalogo)

        if simular:
            _resumen(entradas, registro, cargado=False)
            consola.print("\n[yellow]Simulación: no se ha escrito nada en Supabase.[/yellow]")
            return

        from .carga.supabase import upsert_entradas

        registro = upsert_entradas(entradas, registro)
        cerrar_registro(registro)
        _resumen(entradas, registro, cargado=True)

    except Exception as e:  # noqa: BLE001 - cualquier fallo debe quedar registrado
        registro.exito = False
        registro.errores.append(f"{type(e).__name__}: {e}")
        consola.print(f"[red]La ejecución ha fallado: {type(e).__name__}: {e}[/red]")
        if not simular:
            try:
                cerrar_registro(registro)
            except Exception as e2:  # noqa: BLE001
                consola.print(f"[red]Tampoco se pudo guardar el registro: {e2}[/red]")
        raise typer.Exit(1) from e
    finally:
        if cerrojo is not None:
            cerrojo.close()


def _tomar_cerrojo(simular: bool):
    """Impide que dos extracciones corran a la vez.

    Usa un bloqueo de fichero, que el sistema libera solo aunque el proceso
    muera de mala manera: un fichero centinela normal dejaría el cerrojo puesto
    para siempre tras un Ctrl-C. En simulación no hace falta, porque no escribe.
    """
    if simular:
        return None

    import fcntl
    import tempfile

    ruta = pathlib.Path(tempfile.gettempdir()) / "transparencia-gobcan.lock"
    fichero = ruta.open("w")
    try:
        fcntl.flock(fichero, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        fichero.close()
        consola.print(
            "[red]Ya hay otra extracción en marcha.[/red] Espera a que termine, "
            f"o borra {ruta} si estás seguro de que no queda ninguna."
        )
        raise typer.Exit(1) from None
    return fichero


def _resumen(entradas: list, registro, cargado: bool) -> None:
    """Muestra en consola lo que ha hecho la ejecución."""
    tabla = Table(show_header=False, box=None, pad_edge=False)
    tabla.add_column(style="dim")
    tabla.add_column(justify="right")
    tabla.add_row("filas leídas", str(registro.filas_leidas))
    tabla.add_row("válidas", f"[green]{len(entradas)}[/green]")
    tabla.add_row("descartadas", str(registro.filas_descartadas))
    if cargado:
        tabla.add_row("insertadas", str(registro.filas_insertadas))
        tabla.add_row("actualizadas", str(registro.filas_actualizadas))
    tabla.add_row("alertas", f"[cyan]{sum(1 for e in entradas if e.es_alerta)}[/cyan]")
    consola.print(tabla)

    if registro.descartes_por_motivo:
        consola.print("\n[bold]Descartes por motivo[/bold]")
        for motivo, n in sorted(registro.descartes_por_motivo.items(), key=lambda x: -x[1]):
            consola.print(f"  {motivo:26} {n}")

    if registro.entradillas_por_origen:
        consola.print("\n[bold]Origen de las entradillas[/bold]")
        total = sum(registro.entradillas_por_origen.values())
        for origen, n in sorted(registro.entradillas_por_origen.items(), key=lambda x: -x[1]):
            consola.print(f"  {origen:26} {n:>4}  ({n / total:.0%})")

    if registro.anomalias:
        consola.print("\n[bold yellow]Anomalías[/bold yellow]")
        for anomalia in registro.anomalias:
            consola.print(f"  · {anomalia}")


@app.command("validar-config")
def validar_config() -> None:
    """Comprueba la coherencia de los ficheros de configuración.

    Verifica que las correspondencias de áreas apunten a claves existentes y que
    los patrones de alertas compilen como expresiones regulares.
    """
    _configurar_registro()
    problemas: list[str] = []

    areas = cargar("areas")
    claves = {a["clave"] for a in areas["areas"]}
    for c in areas["correspondencias_gobcan"]:
        if c["area"] not in claves:
            problemas.append(f"La categoría {c['id']} apunta al área inexistente {c['area']!r}")

    alertas = cargar("alertas")
    for grupo in ("actos", "materias"):
        for nombre, patron in alertas[grupo].items():
            try:
                re.compile(patron, re.VERBOSE)
            except re.error as e:
                problemas.append(f"El patrón {grupo}.{nombre} no compila: {e}")

    territorio = cargar("territorio")
    municipios = [m for i in territorio["islas"] for m in i["municipios"]]
    repetidos = {m for m in municipios if municipios.count(m) > 1}
    if repetidos:
        problemas.append(f"Municipios repetidos entre islas: {sorted(repetidos)}")

    if problemas:
        consola.print("[red]Configuración con problemas:[/red]")
        for p in problemas:
            consola.print(f"  · {p}")
        raise typer.Exit(1)

    consola.print(
        f"[green]Configuración correcta[/green] · {len(claves)} áreas, "
        f"{len(areas['correspondencias_gobcan'])} correspondencias, "
        f"{len(alertas['materias'])} materias, {len(municipios)} municipios"
    )


@app.command("probar-conexion")
def probar_conexion() -> None:
    """Comprueba que las credenciales del `.env` llegan a la base de datos.

    Solo lee: cuenta las filas que ya hay en las dos tablas. Sirve para separar
    un problema de credenciales de un problema del pipeline, sin escribir nada.
    """
    _configurar_registro()
    esquema = entorno("SUPABASE_SCHEMA", "transp_gobcan")

    try:
        from .carga.supabase import conectar

        with conectar() as conexion, conexion.cursor() as cursor:
            cursor.execute("SELECT current_database(), current_user, version()")
            base, usuario, version = cursor.fetchone()
            cursor.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema = %s", (esquema,)
            )
            (n_tablas,) = cursor.fetchone()
            if not n_tablas:
                consola.print(
                    f"[red]Conecta, pero el schema {esquema!r} no existe.[/red] "
                    "Aplica migraciones/001_crear_schema_transp_gobcan.sql."
                )
                raise typer.Exit(1)
            cursor.execute(f"SELECT count(*) FROM {esquema}.entradas")
            (n_entradas,) = cursor.fetchone()
            cursor.execute(f"SELECT count(*) FROM {esquema}.logs_ejecucion")
            (n_logs,) = cursor.fetchone()
    except typer.Exit:
        raise
    except Exception as e:  # noqa: BLE001
        consola.print(f"[red]No se ha podido conectar:[/red] {type(e).__name__}: {e}")
        # Los tres fallos habituales dan errores que despistan: conviene
        # nombrarlos, porque ninguno es lo que parece a primera vista.
        mensaje = str(e).lower()
        if "tenant" in mensaje or "not found" in mensaje:
            consola.print(
                "\n[yellow]No es la contraseña:[/yellow] el pooler no encuentra el proyecto. "
                "Prueba el otro prefijo de host ([cyan]aws-1[/cyan] en vez de [cyan]aws-0[/cyan], "
                "o al revés) y comprueba que el usuario sea "
                "[cyan]postgres.<ref-del-proyecto>[/cyan], no [cyan]postgres[/cyan] a secas."
            )
        elif "nodename" in mensaje or "could not translate" in mensaje:
            consola.print(
                "\n[yellow]Es un problema de DNS, no de credenciales:[/yellow] estás usando la "
                "conexión directa ([cyan]db.<ref>.supabase.co[/cyan]), que solo publica IPv6. "
                "Usa la cadena del [cyan]Session pooler[/cyan]."
            )
        elif "password" in mensaje or "authentication" in mensaje:
            consola.print(
                "\nRevisa la contraseña de [cyan]DATABASE_URL[/cyan]: es la de la BASE DE DATOS, "
                "no la de tu cuenta de Supabase. Se regenera en "
                "Project Settings > Database > Reset database password."
            )
        raise typer.Exit(1) from e

    consola.print(f"[green]Conexión correcta[/green] · {base} como {usuario}")
    consola.print(f"  {version.split(',')[0]}")
    consola.print(f"  schema [cyan]{esquema}[/cyan]: {n_entradas} entradas, {n_logs} ejecuciones")


@app.command()
def clasificar(
    recalcular: bool = typer.Option(False, help="Reaplica la capa semántica al histórico"),
) -> None:
    """Aplica la capa semántica de alertas a las entradas ya cargadas.

    Hay que ejecutarlo con `--recalcular` cada vez que se amplíe el vocabulario
    de `config/alertas.yaml`, o las entradas antiguas conservarán la
    clasificación vieja.
    """
    _configurar_registro()
    if not recalcular:
        consola.print("Nada que hacer: usa [cyan]--recalcular[/cyan] para reevaluar el histórico.")
        return
    consola.print(
        "[yellow]Pendiente: se implementa junto con la capa de alertas por correo.[/yellow]"
    )


if __name__ == "__main__":
    app()
