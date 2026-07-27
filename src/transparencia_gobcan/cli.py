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
    desde_cache: bool = typer.Option(
        False, "--desde-cache",
        help="Solo parcan: reutiliza la última extracción volcada en disco",
    ),
) -> None:
    """Ejecuta el pipeline completo: extracción, transformación, validación y carga."""
    _configurar_registro()

    if fuente not in ("gobcan", "parcan"):
        consola.print(f"[yellow]La fuente {fuente!r} no existe. Usa gobcan o parcan.[/yellow]")
        raise typer.Exit(1)

    if fuente == "parcan":
        _extraer_parcan(modo, simular, desde_cache)
        return

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


def _extraer_parcan(modo: str, simular: bool, desde_cache: bool = False) -> None:
    """Recorre el buscador de iniciativas del Parlamento y carga el resultado.

    A diferencia de Gobcan no hay modo incremental útil: el buscador no filtra
    por fecha de modificación, así que se recorre el anillo entero y el UPSERT
    se encarga de que reprocesar no duplique. Son unas 679 iniciativas con
    crawl-delay de 3 segundos, es decir alrededor de media hora.
    """
    from pydantic import ValidationError

    from .alertas.clasificador import clasificar
    from .carga.logs import abrir_registro, cerrar_registro
    from .extraccion.parcan_iniciativas import leer_cache, recorrer, ruta_cache
    from .modelos import MotivoDescarte
    from .transformacion.iniciativas import construir_entrada

    anillo = "control" if modo == "control" else "decisiones"
    cerrojo = _tomar_cerrojo(simular)
    registro = abrir_registro(Fuente.PARLAMENTO, "historico")
    consola.print(
        f"[bold]Extrayendo[/bold] de parcan · anillo {anillo}"
        + (" · [yellow]simulación[/yellow]" if simular else "")
    )
    consola.print("  [dim]crawl-delay de 3 s por petición: esto va a tardar[/dim]")

    if desde_cache:
        crudas = leer_cache(anillo)
        if not crudas:
            consola.print(f"[red]No hay extracción guardada en {ruta_cache(anillo)}[/red]")
            raise typer.Exit(1)
        consola.print(f"  [cyan]{len(crudas)}[/cyan] iniciativas recuperadas del volcado en disco")
        fuente_datos = iter(crudas)
    else:
        fuente_datos = recorrer(anillo=anillo)

    entradas: list = []
    try:
        for cruda in fuente_datos:
            registro.filas_leidas += 1
            try:
                entradas.append(clasificar(construir_entrada(cruda)))
            except ValidationError as e:
                registro.anotar_descarte(
                    MotivoDescarte.ERROR_VALIDACION,
                    f"{cruda.get('codigo')}: {e.errors()[0]['msg'] if e.errors() else e}",
                )
            except (KeyError, ValueError, TypeError) as e:
                registro.anotar_descarte(
                    MotivoDescarte.ERROR_VALIDACION, f"{cruda.get('codigo')}: {e}"
                )
            if registro.filas_leidas % 50 == 0:
                consola.print(f"  {registro.filas_leidas} iniciativas procesadas…")

        for entrada in entradas:
            clave = entrada.entrada_origen.value
            registro.entradillas_por_origen[clave] = (
                registro.entradillas_por_origen.get(clave, 0) + 1
            )

        if simular:
            _resumen(entradas, registro, cargado=False)
            _resumen_parcan(entradas)
            consola.print("\n[yellow]Simulación: no se ha escrito nada en Supabase.[/yellow]")
            return

        from .carga.supabase import upsert_entradas

        registro = upsert_entradas(entradas, registro)
        cerrar_registro(registro)
        _resumen(entradas, registro, cargado=True)
        _resumen_parcan(entradas)

    except Exception as e:  # noqa: BLE001
        registro.exito = False
        registro.errores.append(f"{type(e).__name__}: {e}")
        consola.print(f"[red]La ejecución ha fallado: {type(e).__name__}: {e}[/red]")
        if not simular:
            try:
                cerrar_registro(registro)
            except Exception:  # noqa: BLE001
                pass
        raise typer.Exit(1) from e
    finally:
        if cerrojo is not None:
            cerrojo.close()


def _resumen_parcan(entradas: list) -> None:
    """Desglose propio del Parlamento: quién propone y de dónde sale el área."""
    import collections

    if not entradas:
        return
    grupos = collections.Counter(e.grupo_parlamentario or "(sin grupo)" for e in entradas)
    consola.print("\n[bold]Grupo proponente[/bold]")
    for grupo, n in grupos.most_common():
        consola.print(f"  {grupo[:46]:48} {n:>4}")

    origen = collections.Counter(e.area_origen.value for e in entradas)
    consola.print("\n[bold]Procedencia del área[/bold]")
    for k, n in origen.most_common():
        consola.print(f"  {k:26} {n:>4}  ({n / len(entradas):.0%})")


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

    from .alertas.clasificador import TIPOS_QUE_SON_DECISION, _patrones, normalizar
    from .carga.supabase import conectar

    esquema = entorno("SUPABASE_SCHEMA", "transp_gobcan")
    patrones = _patrones()
    cambios: list[tuple] = []
    antes = despues = 0

    # Se reevalúa desde la base: el vocabulario solo mira título y entradilla,
    # así que no hace falta volver a tocar la fuente. Eso permite afinar el
    # vocabulario cuantas veces haga falta contra tres años reales.
    with conectar() as conexion, conexion.cursor() as cursor:
        cursor.execute(
            f"SELECT hash_dedup, titulo, entrada, tipo_iniciativa, es_alerta FROM {esquema}.entradas"
        )
        filas = cursor.fetchall()
        consola.print(f"Reevaluando [cyan]{len(filas)}[/cyan] entradas…")

        for hash_dedup, titulo, entrada, tipo, era_alerta in filas:
            texto = normalizar(f"{titulo} {entrada}")
            actos = [k for k, rx in patrones["actos"].items() if rx.search(texto)]
            materias = [k for k, rx in patrones["materias"].items() if rx.search(texto)]
            if tipo and tipo in TIPOS_QUE_SON_DECISION:
                actos.append("iniciativa_parlamentaria")
            institucion = bool(
                patrones["cabildos"].search(texto) or patrones["ayuntamientos"].search(texto)
            )
            motivo = (
                "entidad_propia" if patrones["propias"].search(texto)
                else "decision_con_materia" if (actos and materias)
                else "institucion_con_materia" if (institucion and materias)
                else None
            )
            antes += bool(era_alerta)
            despues += motivo is not None
            cambios.append((actos, materias, motivo is not None, motivo, hash_dedup))

        from psycopg2.extras import execute_batch

        execute_batch(
            cursor,
            f"""UPDATE {esquema}.entradas
                   SET actos = %s, materias = %s, es_alerta = %s, motivo_alerta = %s
                 WHERE hash_dedup = %s""",
            cambios,
            page_size=500,
        )

    consola.print(
        f"[green]Reclasificación terminada[/green] · alertas: {antes} → {despues} "
        f"({despues - antes:+d})"
    )




@app.command()
def notificar(
    simular: bool = typer.Option(
        False, "--simular", help="Genera el correo a fichero y no envía nada"
    ),
    marcar_historico: bool = typer.Option(
        False, "--marcar-historico",
        help="Marca como notificado todo lo anterior a ALERTAS_DESDE, sin enviar",
    ),
    limite: int | None = typer.Option(None, help="Máximo de entradas en este envío"),
    prueba: bool = typer.Option(
        False, "--prueba",
        help="Envía un correo de muestra con las últimas alertas y NO las sella",
    ),
    a: str | None = typer.Option(
        None, "--a", help="Destinatarias solo para este envío, separadas por comas"
    ),
) -> None:
    """Envía el aviso con las decisiones detectadas y aún no notificadas.

    Solo entran las entradas marcadas como alerta cuya fecha sea igual o
    posterior a ALERTAS_DESDE y que no se hayan notificado ya. Tras el envío se
    sella `notificada_en`, de modo que reejecutarlo no repite avisos.
    """
    _configurar_registro()

    from .alertas.correo import construir_mensaje, enviar
    from .carga.supabase import conectar

    esquema = entorno("SUPABASE_SCHEMA", "transp_gobcan")
    desde = entorno("ALERTAS_DESDE", "2026-01-01")
    destinatarias = [
        d.strip() for d in (a or entorno("ALERTAS_DESTINATARIAS") or "").split(",") if d.strip()
    ]
    maximo = limite or int(cargar("alertas")["envio"]["maximo_por_envio"])

    with conectar() as conexion, conexion.cursor() as cursor:
        if marcar_historico:
            # El histórico son tres años: avisar de decisiones de 2023 no tiene
            # sentido. Se sellan como notificadas sin enviar nada.
            cursor.execute(
                f"""UPDATE {esquema}.entradas SET notificada_en = now()
                     WHERE es_alerta AND notificada_en IS NULL AND fecha_real < %s""",
                (desde,),
            )
            consola.print(
                f"[green]{cursor.rowcount}[/green] alertas anteriores a {desde} "
                "marcadas como notificadas, sin enviar nada."
            )
            return

        # En modo prueba se ignora tanto ALERTAS_DESDE como el sello de
        # notificación: interesa ver cómo queda el correo, no repartir avisos.
        # Y sobre todo no se sella nada, para que el envío real de mañana no
        # se encuentre con que esas entradas ya constan como notificadas.
        condicion = (
            "es_alerta" if prueba
            else "es_alerta AND notificada_en IS NULL AND fecha_real >= %s"
        )
        parametros = (maximo,) if prueba else (desde, maximo)
        cursor.execute(
            f"""SELECT hash_dedup, fuente, fecha_real, titulo, entrada, url, area,
                       territorio, materias, grupo_parlamentario, situacion
                  FROM {esquema}.entradas
                 WHERE {condicion}
                 ORDER BY fecha_real DESC, fuente
                 LIMIT %s""",
            parametros,
        )
        columnas = [c.name for c in cursor.description]
        filas = [dict(zip(columnas, f, strict=True)) for f in cursor.fetchall()]

        if not filas:
            consola.print("No hay decisiones nuevas que notificar.")
            return

        if prueba:
            consola.print("[yellow]Modo prueba:[/yellow] no se sellará ninguna entrada.")

        consola.print(f"[bold]{len(filas)}[/bold] decisiones pendientes de aviso:")
        for f in filas[:10]:
            consola.print(f"  · [{f['fuente'][:4]}] {f['titulo'][:78]}")
        if len(filas) > 10:
            consola.print(f"  … y {len(filas) - 10} más")

        if not destinatarias:
            consola.print("[red]ALERTAS_DESTINATARIAS está vacío en el .env[/red]")
            raise typer.Exit(1)

        mensaje = construir_mensaje(filas, destinatarias)

        if simular:
            salida = pathlib.Path("aviso-simulado.html")
            salida.write_text(mensaje.get_body("html").get_content(), encoding="utf-8")
            consola.print("\n[yellow]Simulación:[/yellow] no se ha enviado nada.")
            consola.print(f"  asunto      : {mensaje['Subject']}")
            consola.print(f"  destinatarias: {mensaje['To']}")
            consola.print(f"  vista previa: [cyan]{salida}[/cyan]")
            return

        if prueba:
            mensaje.replace_header("Subject", "[Prueba] " + mensaje["Subject"])

        enviar(mensaje)

        if prueba:
            consola.print(
                f"[green]Correo de prueba enviado[/green] a {mensaje['To']} · "
                f"{len(filas)} entradas · [yellow]sin sellar[/yellow]"
            )
            return

        cursor.execute(
            f"UPDATE {esquema}.entradas SET notificada_en = now() WHERE hash_dedup = ANY(%s)",
            ([f["hash_dedup"] for f in filas],),
        )
        consola.print(f"[green]Aviso enviado[/green] a {mensaje['To']} · {len(filas)} entradas")


@app.command()
def exportar(
    destino: str = typer.Option(
        "visualizacion/datos.js", help="Fichero de salida para la interfaz"
    ),
) -> None:
    """Vuelca los datos al fichero que consume la interfaz de consulta.

    La interfaz es estática y lee este fichero: no habla con Supabase, así que
    no hay que abrir la base al navegador ni escribir políticas de lectura
    pública. El mismo fichero sirve en local y empotrado en un bloque de Divi.
    """
    _configurar_registro()
    from .carga.exportar import exportar as volcar

    resumen = volcar(pathlib.Path(destino))
    consola.print(f"[green]Exportadas {resumen['entradas']} entradas[/green] a [cyan]{destino}[/cyan]")
    consola.print(
        f"  peso {resumen['peso_mb']} MB · "
        f"de {resumen['desde']} a {resumen['hasta']} · {resumen['meses']} meses"
    )


if __name__ == "__main__":
    app()
