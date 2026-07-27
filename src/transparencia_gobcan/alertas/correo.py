"""Composición y envío del aviso por correo.

El contenido responde al caso de uso 3 de la guía: título, quién impulsa la
medida —consejería en el Gobierno, grupo parlamentario en la Cámara—, un
resumen breve y las áreas a las que afecta.

Sobre el HTML: los clientes de correo son mucho más limitados que un navegador.
Nada de hojas de estilo externas ni tipografías web —Gmail las descarta—, así
que va todo en estilos en línea, la maquetación se apoya en tablas y las
tipografías son las del sistema. Se envía también una versión en texto plano,
que es lo que ven quienes leen el correo sin formato.

Se envía siempre desde la cuenta autenticada: Gmail rechaza remitentes que no
coincidan con la cuenta salvo que estén dados de alta como alias verificado.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from datetime import date, datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from ..config import cargar, entorno

log = logging.getLogger(__name__)

# Identidad visual ODESOCAN
TEAL = "#00C8B4"
TEAL_OSCURO = "#009E8E"
TEAL_CLARO = "#E0FAF7"
NAVY = "#0D1B2A"
NAVY_MEDIO = "#1A2F45"
TEXTO_TENUE = "#6B8CA5"
BORDE = "#E4EDF5"
FONDO = "#F5F8FA"

TIPO_TITULAR = "'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
TIPO_CUERPO = "'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

# Nombre legible de cada área y materia, para no enseñar las claves internas
_NOMBRES: dict[str, str] | None = None


def nombre_area(clave: str) -> str:
    """Traduce la clave interna del área a su nombre completo."""
    global _NOMBRES
    if _NOMBRES is None:
        _NOMBRES = {a["clave"]: a["nombre"] for a in cargar("areas")["areas"]}
    return _NOMBRES.get(clave, clave.replace("_", " ").capitalize())


def nombre_materia(clave: str) -> str:
    return clave.replace("_", " ").replace("violencia genero", "violencia de género").capitalize()


def _quien_impulsa(fila: dict) -> str:
    """Devuelve quién está detrás de la medida, según la fuente.

    En el Gobierno es la consejería; en el Parlamento, el grupo proponente. Si
    la iniciativa la presenta el Gobierno no hay grupo, y se dice así en vez de
    dejarlo en blanco.
    """
    if fila["fuente"] == "parlamento":
        return fila.get("grupo_parlamentario") or "Iniciativa del Gobierno"
    return nombre_area(fila["area"])


def _escapar(texto: str) -> str:
    return (
        (texto or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


# Meses en español, mapeados a mano. `strftime("%B")` depende del locale del
# sistema: da "July" en el runner de GitHub Actions, que arranca en inglés.
# Es el mismo motivo por el que las fechas de Parcan se parsean a mano.
MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def fecha_larga(dia: date) -> str:
    """Devuelve '27 de julio' sin depender del locale del sistema."""
    return f"{dia.day} de {MESES[dia.month - 1]}"


def componer_asunto(filas: list[dict]) -> str:
    n = len(filas)
    hoy = fecha_larga(date.today())
    if n == 1:
        return f"ODESOCAN · 1 decisión detectada · {hoy}"
    return f"ODESOCAN · {n} decisiones detectadas · {hoy}"


def componer_texto(filas: list[dict]) -> str:
    """Versión en texto plano, para quien lee el correo sin formato."""
    lineas = [
        "ODESOCAN · Observatorio de Derechos Sociales de Canarias",
        "Seguimiento de la actividad ejecutiva y parlamentaria",
        "",
        f"{len(filas)} entrada(s) detectada(s).",
        "",
    ]
    for f in filas:
        origen = "Gobierno de Canarias" if f["fuente"] == "gobierno" else "Parlamento de Canarias"
        lineas += [
            "-" * 68,
            f["titulo"],
            f"  {origen} · {_quien_impulsa(f)}",
            f"  {f['fecha_real']} · {f['territorio']}",
            "",
            f"  {f['entrada']}",
            "",
        ]
        if f.get("materias"):
            lineas.append("  Áreas afectadas: " + ", ".join(nombre_materia(m) for m in f["materias"]))
        lineas += [f"  {f['url']}", ""]

    lineas += [
        "-" * 68,
        "",
        "Aviso automático de la herramienta transparencia-gobcan.",
        "Recoge lo publicado por el Gobierno y el Parlamento de Canarias: detecta",
        "actividad comunicada, no toda la actividad ejecutiva.",
        "",
        "Para dejar de recibirlo, responde a este correo indicándolo.",
    ]
    return "\n".join(lineas)


def _tarjeta(f: dict) -> str:
    """Una entrada dentro del correo."""
    es_gobierno = f["fuente"] == "gobierno"
    origen = "Gobierno de Canarias" if es_gobierno else "Parlamento de Canarias"
    color_origen = TEAL_OSCURO if es_gobierno else "#7C5CE6"

    etiquetas = "".join(
        f'<span style="display:inline-block;background:{TEAL_CLARO};color:{TEAL_OSCURO};'
        f'font-size:11px;font-weight:700;padding:3px 10px;border-radius:99px;'
        f'margin:0 6px 6px 0;">{_escapar(nombre_materia(m)).upper()}</span>'
        for m in (f.get("materias") or [])
    )

    situacion = ""
    if f.get("situacion"):
        situacion = (
            f'<span style="color:{TEXTO_TENUE};font-size:12px;"> · {_escapar(f["situacion"])}</span>'
        )

    return f"""
    <tr><td style="padding:0 0 14px 0;">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border:1px solid {BORDE};border-radius:12px;">
        <tr><td style="padding:18px 20px;">
          <div style="font-family:{TIPO_TITULAR};font-size:10px;font-weight:700;
                      letter-spacing:.1em;text-transform:uppercase;color:{color_origen};
                      padding-bottom:6px;">{origen}</div>
          <div style="font-family:{TIPO_TITULAR};font-size:16px;font-weight:700;
                      color:{NAVY_MEDIO};line-height:1.35;padding-bottom:8px;">
            {_escapar(f["titulo"])}
          </div>
          <div style="font-family:{TIPO_CUERPO};font-size:12px;color:{TEXTO_TENUE};
                      padding-bottom:10px;">
            <strong style="color:{NAVY_MEDIO};">{_escapar(_quien_impulsa(f))}</strong>
            &nbsp;·&nbsp; {f["fecha_real"]}
            &nbsp;·&nbsp; {_escapar(f["territorio"])}{situacion}
          </div>
          <div style="font-family:{TIPO_CUERPO};font-size:14px;color:#1A2F45;
                      line-height:1.6;padding-bottom:12px;">
            {_escapar(f["entrada"])}
          </div>
          {etiquetas}
          <div style="padding-top:10px;">
            <a href="{_escapar(f["url"])}"
               style="font-family:{TIPO_TITULAR};font-size:13px;font-weight:700;
                      color:{TEAL_OSCURO};text-decoration:none;">Ver la publicación &rarr;</a>
          </div>
        </td></tr>
      </table>
    </td></tr>"""


def componer_html(filas: list[dict]) -> str:
    """Correo en HTML con la identidad visual de ODESOCAN."""
    n = len(filas)
    titular = "1 decisión detectada" if n == 1 else f"{n} decisiones detectadas"
    tarjetas = "".join(_tarjeta(f) for f in filas)

    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{FONDO};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{FONDO};">
<tr><td align="center" style="padding:24px 12px;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="max-width:640px;width:100%;">

    <tr><td style="background:{NAVY};border-radius:14px 14px 0 0;padding:26px 24px;">
      <div style="font-family:{TIPO_TITULAR};font-size:10px;font-weight:700;
                  letter-spacing:.14em;text-transform:uppercase;
                  color:rgba(255,255,255,.55);padding-bottom:10px;">
        ODESOCAN · Observatorio de Derechos Sociales de Canarias
      </div>
      <div style="font-family:{TIPO_TITULAR};font-size:22px;font-weight:700;color:#ffffff;
                  line-height:1.25;">
        <span style="color:{TEAL};">{titular}</span> en el Gobierno y el Parlamento
      </div>
      <div style="font-family:{TIPO_CUERPO};font-size:13px;color:rgba(255,255,255,.65);
                  padding-top:8px;">
        Seguimiento de la actividad ejecutiva y parlamentaria de Canarias
      </div>
    </td></tr>

    <tr><td style="background:{FONDO};height:18px;line-height:18px;">&nbsp;</td></tr>
    {tarjetas}

    <tr><td style="padding:18px 22px;background:#ffffff;border:1px solid {BORDE};
                   border-radius:12px;">
      <div style="font-family:{TIPO_CUERPO};font-size:12px;color:{TEXTO_TENUE};line-height:1.65;">
        Aviso automático de la herramienta <strong>transparencia-gobcan</strong>.
        Recoge lo que publican el Gobierno y el Parlamento de Canarias, así que
        detecta <strong>actividad comunicada</strong>, no toda la actividad
        ejecutiva: que una medida no aparezca aquí no significa que no exista.
        <br><br>
        Para dejar de recibir estos avisos, responde a este correo indicándolo.
      </div>
    </td></tr>

    <tr><td style="padding:16px 4px;font-family:{TIPO_CUERPO};font-size:11px;
                   color:{TEXTO_TENUE};text-align:center;">
      ODESOCAN · Calle los Dragos, 45, 3ª planta · 35118 Agüimes, Las Palmas
    </td></tr>

  </table>
</td></tr></table>
</body></html>"""


def construir_mensaje(filas: list[dict], destinatarias: list[str]) -> EmailMessage:
    """Arma el mensaje con sus dos versiones, texto plano y HTML."""
    remitente = entorno("ALERTAS_REMITENTE", obligatoria=True)
    mensaje = EmailMessage()
    mensaje["Subject"] = componer_asunto(filas)
    mensaje["From"] = formataddr(("ODESOCAN · Transparencia", remitente))
    mensaje["To"] = ", ".join(destinatarias)
    mensaje["Date"] = formatdate(localtime=True)
    mensaje["Message-ID"] = make_msgid(domain=remitente.split("@")[-1])
    # Ayuda a que los clientes agrupen los avisos y no los tomen por correo masivo
    mensaje["Auto-Submitted"] = "auto-generated"
    mensaje["X-Entity-Ref-ID"] = f"transparencia-gobcan-{datetime.now():%Y%m%d%H%M}"

    mensaje.set_content(componer_texto(filas))
    mensaje.add_alternative(componer_html(filas), subtype="html")
    return mensaje


def enviar(mensaje: EmailMessage) -> None:
    """Envía el mensaje por el SMTP configurado."""
    host = entorno("SMTP_HOST", obligatoria=True)
    puerto = int(entorno("SMTP_PORT", "587"))
    usuario = entorno("SMTP_USUARIO", obligatoria=True)
    clave = entorno("SMTP_CONTRASENA", obligatoria=True)

    with smtplib.SMTP(host, puerto, timeout=60) as servidor:
        servidor.ehlo()
        servidor.starttls(context=ssl.create_default_context())
        servidor.ehlo()
        servidor.login(usuario, clave)
        servidor.send_message(mensaje)
    log.info("Aviso enviado a %s", mensaje["To"])
