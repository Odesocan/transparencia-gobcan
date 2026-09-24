/* Interfaz de consulta de transparencia-gobcan · React + D3.

   React gobierna el estado y el DOM de la página; D3 dibuja los dos gráficos
   dentro de un contenedor que React le cede. Ninguno de los dos pisa al otro.

   No hay paso de compilación, y es deliberado: la página se tiene que poder
   abrir con doble clic, y Chrome bloquea los módulos ES desde file://. Por eso
   React va en su versión UMD y la plantilla se escribe con htm, que da una
   sintaxis casi idéntica a JSX sin necesitar Babel. */
(function(){
"use strict";

const {useState, useEffect, useMemo, useRef, useCallback} = React;
const html = htm.bind(React.createElement);

const POR_PAGINA = 10;
const MESES = ["enero","febrero","marzo","abril","mayo","junio",
               "julio","agosto","septiembre","octubre","noviembre","diciembre"];
const AUTONOMICO = "Canarias";
const VARIAS = "Varias islas";
// Cuando el Parlamento tramita algo sin grupo proponente, lo ha traído el Gobierno
const GOBIERNO_PROPONE = "Gobierno de Canarias";

// Las materias salen de la capa de alertas; sus claves no son legibles tal cual
const NOMBRE_MATERIA = {
  servicios_sociales: "Servicios sociales", sanidad: "Sanidad", dependencia: "Dependencia",
  empleo: "Empleo", educacion: "Educación", vivienda: "Vivienda", migraciones: "Migraciones",
  violencia_genero: "Violencia de género", emergencia_social: "Emergencia social",
  territorio_aguas: "Territorio y aguas",
};
const materia = k => NOMBRE_MATERIA[k] || k.replace(/_/g, " ");

/* ------------------------------------------------------------------ utilidades */
function normalizar(s){
  return (s || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}
function escapar(s){
  return String(s ?? "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
const num = n => n.toLocaleString("es-ES");
function fechaLarga(iso){
  const [a,m,d] = iso.split("-").map(Number);
  return `${d} de ${MESES[m-1]} de ${a}`;
}
function fechaCorta(iso){
  const [a,m,d] = iso.split("-").map(Number);
  return `${d} ${MESES[m-1].slice(0,3)} ${a}`;
}
function mesLargo(clave){
  const [a,m] = clave.split("-").map(Number);
  return `${MESES[m-1]} de ${a}`;
}
function limitesMes(clave){
  const [a,m] = clave.split("-").map(Number);
  const ultimo = new Date(a, m, 0).getDate();
  return [`${clave}-01`, `${clave}-${String(ultimo).padStart(2,"0")}`];
}
function recortar(s, max){
  if (s.length <= max) return s;
  const corte = s.slice(0, max - 1);
  const espacio = corte.lastIndexOf(" ");
  return (espacio > max * .6 ? corte.slice(0, espacio) : corte).replace(/[,\s]+$/, "") + "…";
}
// «Consejería de Educación, Formación Profesional, Actividad Física y Deportes»
// no cabe en una etiqueta: se queda en «Educación» y el nombre completo va al
// tooltip. Es la forma en que se nombra a cada consejería en la conversación.
const cortoArea = n => (n || "").replace(/^Consejería de /, "").split(",")[0];
const cortoGrupo = n => n.replace(/^GP /, "");

/* ----------------------------------------------------------- preparación
   Se hace una vez al cargar. El texto de búsqueda se normaliza aquí y no en
   cada pulsación: sobre 16.000 títulos y entradillas eran 27 ms por tecla,
   frente a 9 con esto hecho de antemano. Las filas guardan claves estables
   (la clave del área, el código del tipo) y no índices de catálogo, porque
   los índices cambian con cada volcado y romperían los enlaces compartidos. */
function preparar(d){
  const IDX = {};
  d.campos.forEach((nombre, i) => IDX[nombre] = i);
  const C = d.catalogos;
  const islaDe = d.isla_de || {};
  // «Cerrada · aprobado» y «Cerrada · aprobada» son lo mismo escrito dos veces
  const situaciones = C.situacion.map(s => s.replace(/aprobado$/, "aprobada"));
  // Las iniciativas firmadas por varios grupos llegan como una sola cadena.
  // Se separan para que filtrar por un grupo incluya lo que firmó con otros.
  const gruposDe = C.grupo.map(g => g.split(/,\s*(?=GP )/).map(s => s.trim()));
  const val = (f, campo, catalogo) => f[IDX[campo]] == null ? null : catalogo[f[IDX[campo]]];

  const filas = d.filas.map((f, i) => {
    const terr = val(f, "territorio", C.territorio) || AUTONOMICO;
    const esPar = f[IDX.fuente] === 1;
    const titulo = f[IDX.titulo] || "", entrada = f[IDX.entrada] || "";
    return {
      i, fecha: f[IDX.fecha], mes: f[IDX.fecha].slice(0, 7),
      fuente: String(f[IDX.fuente]), titulo, entrada, url: f[IDX.url],
      area: val(f, "area", C.area) || "sin_asignar",
      terr,
      isla: terr === AUTONOMICO || terr === VARIAS ? terr : (islaDe[terr] || terr),
      grupos: esPar ? (f[IDX.grupo] == null ? [GOBIERNO_PROPONE] : gruposDe[f[IDX.grupo]]) : [],
      tipo: val(f, "tipo", C.tipo),
      sit: f[IDX.situacion] == null ? null : situaciones[f[IDX.situacion]],
      dec: !!f[IDX.alerta],
      mats: (f[IDX.materias] || []).map(k => C.materias[k]),
      heno: normalizar(titulo + " " + entrada),
    };
  });

  return {
    filas,
    meses: d.actividad.map(a => a.mes),
    nombresArea: d.nombres_area || {},
    nombresTipo: d.nombres_tipo || {},
    tieneIslas: !!d.isla_de,
    version: d.version, generado: d.generado || null,
    total: {
      todo: filas.length,
      gob: filas.filter(r => r.fuente === "0").length,
      par: filas.filter(r => r.fuente === "1").length,
      dec: filas.filter(r => r.dec).length,
    },
  };
}

/* ------------------------------------------------------------------ estado */
const INICIAL = {f:"0", q:"", desde:"", hasta:"", area:[], grupo:[], tipo:[], sit:[],
                 isla:"", muni:"", mat:[], dec:false, orden:"desc", p:1};
const LISTAS = ["area","grupo","tipo","sit","mat"];
const TEXTOS = ["q","isla","muni"];
const FECHA_ISO = /^\d{4}-\d{2}-\d{2}$/;

/* El estado vive en la URL (#…): así cualquier vista filtrada se puede
   compartir con un enlace o guardar en marcadores. Las listas se separan con
   «|» porque los nombres de los grupos llevan comas. */
function leerHash(){
  const p = new URLSearchParams(location.hash.slice(1));
  const e = {...INICIAL};
  if (p.get("f") === "1") e.f = "1";
  TEXTOS.forEach(k => { if (p.get(k)) e[k] = p.get(k); });
  ["desde","hasta"].forEach(k => { if (FECHA_ISO.test(p.get(k) || "")) e[k] = p.get(k); });
  LISTAS.forEach(k => { if (p.get(k)) e[k] = p.get(k).split("|").filter(Boolean); });
  e.dec = p.get("dec") === "1";
  e.orden = p.get("orden") === "asc" ? "asc" : "desc";
  e.p = Math.max(1, parseInt(p.get("p"), 10) || 1);
  return e;
}
function escribirHash(e){
  const p = new URLSearchParams();
  if (e.f !== "0") p.set("f", e.f);
  [...TEXTOS, "desde", "hasta"].forEach(k => { if (e[k]) p.set(k, e[k]); });
  LISTAS.forEach(k => { if (e[k].length) p.set(k, e[k].join("|")); });
  if (e.dec) p.set("dec", "1");
  if (e.orden !== "desc") p.set("orden", e.orden);
  if (e.p > 1) p.set("p", e.p);
  const cadena = p.toString();
  history.replaceState(null, "", cadena ? "#" + cadena : location.pathname + location.search);
}

/* ---------------------------------------------------------------- facetas
   Cada faceta sabe qué valores tiene una fila y si la fila pasa su filtro.
   Los recuentos siguen la convención de la búsqueda facetada: los de cada
   faceta se calculan con todos los filtros MENOS el suyo, para que al marcar
   un área se sigan viendo las demás con su cifra y se pueda añadir otra. */
const FACETAS = {
  // Las fechas también son una faceta: así el gráfico mensual sigue mostrando
  // los demás meses cuando se ha elegido uno, y se puede saltar a otro.
  fecha:  {valores: r => [r.mes],    activa: e => !!(e.desde || e.hasta),
           pasa: (r,e) => !(e.desde && r.fecha < e.desde) && !(e.hasta && r.fecha > e.hasta)},
  fuente: {valores: r => [r.fuente], activa: () => true,         pasa: (r,e) => r.fuente === e.f},
  area:   {valores: r => [r.area],   activa: e => e.area.length,  pasa: (r,e) => e.area.includes(r.area)},
  grupo:  {valores: r => r.grupos,   activa: e => e.grupo.length, pasa: (r,e) => r.grupos.some(g => e.grupo.includes(g))},
  tipo:   {valores: r => r.tipo ? [r.tipo] : [], activa: e => e.tipo.length, pasa: (r,e) => e.tipo.includes(r.tipo)},
  sit:    {valores: r => r.sit ? [r.sit] : [],   activa: e => e.sit.length,  pasa: (r,e) => e.sit.includes(r.sit)},
  isla:   {valores: r => [r.isla],   activa: e => !!e.isla,       pasa: (r,e) => r.isla === e.isla},
  muni:   {valores: r => [r.terr],   activa: e => !!e.muni,       pasa: (r,e) => r.terr === e.muni},
  mat:    {valores: r => r.mats,     activa: e => e.mat.length,   pasa: (r,e) => r.mats.some(m => e.mat.includes(m))},
  dec:    {valores: r => r.dec ? ["1"] : [], activa: e => e.dec, pasa: r => r.dec},
};
const CLAVES = Object.keys(FACETAS);

// Una sola pasada: una fila que falla en una única faceta cuenta solo para esa
function calcular(filas, e){
  const palabras = normalizar(e.q).trim().split(/\s+/).filter(Boolean);
  const activas = CLAVES.filter(k => FACETAS[k].activa(e));
  const cuentas = {};
  CLAVES.forEach(k => cuentas[k] = new Map());
  const sumar = (mapa, valores) => valores.forEach(v => mapa.set(v, (mapa.get(v) || 0) + 1));
  const resultado = [];

  for (const r of filas){
    // Todas las palabras deben aparecer: «vivienda lanzarote» no debe devolver
    // todo lo de vivienda más todo lo de Lanzarote.
    if (palabras.length && !palabras.every(p => r.heno.includes(p))) continue;

    let fallo = null, fallos = 0;
    for (const k of activas){
      if (!FACETAS[k].pasa(r, e)){ fallo = k; if (++fallos > 1) break; }
    }
    if (fallos > 1) continue;
    if (fallos === 1){ sumar(cuentas[fallo], FACETAS[fallo].valores(r)); continue; }
    resultado.push(r);
    CLAVES.forEach(k => sumar(cuentas[k], FACETAS[k].valores(r)));
  }
  return {resultado, cuentas, palabras};
}

/* ------------------------------------------------------------------ tooltip */
const tooltip = () => document.getElementById("tooltip");
function mostrarTooltip(ev, contenido){
  const t = tooltip();
  t.innerHTML = contenido;
  t.style.opacity = 1;
  moverTooltip(ev);
}
function moverTooltip(ev){
  const t = tooltip(), r = t.getBoundingClientRect();
  // Con teclado no hay puntero: se ancla al elemento enfocado
  const caja = ev.clientX == null ? ev.target.getBoundingClientRect() : null;
  const cx = caja ? caja.left + caja.width / 2 : ev.clientX;
  const cy = caja ? caja.top : ev.clientY;
  let x = cx + 14, y = cy - r.height - 10;
  if (x + r.width > innerWidth - 8) x = cx - r.width - 14;
  if (y < 8) y = cy + 18;
  t.style.left = x + "px"; t.style.top = y + "px";
}
function ocultarTooltip(){ tooltip().style.opacity = 0; }

/* ----------------------------------------------------------- gráficos D3 */
function useAncho(ref){
  const [ancho, setAncho] = useState(0);
  useEffect(() => {
    // Medida inicial directa: el observador solo avisa cuando el navegador
    // pinta, y en una pestaña en segundo plano eso puede no pasar
    setAncho(Math.floor(ref.current.clientWidth));
    const ro = new ResizeObserver(entradas => setAncho(Math.floor(entradas[0].contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return ancho;
}

// Barra con el extremo de datos redondeado y la base recta, apoyada en el eje
function barraVertical(x, y, w, h, r){
  if (h <= 0) return "";
  r = Math.min(r, w / 2, h);
  return `M${x},${y+h}V${y+r}Q${x},${y} ${x+r},${y}H${x+w-r}Q${x+w},${y} ${x+w},${y+r}V${y+h}Z`;
}
function barraHorizontal(x, y, w, h, r){
  if (w <= 0) return "";
  r = Math.min(r, h / 2, w);
  return `M${x},${y}H${x+w-r}Q${x+w},${y} ${x+w},${y+r}V${y+h-r}Q${x+w},${y+h} ${x+w-r},${y+h}H${x}Z`;
}
// Las zonas de clic son más grandes que la barra, y se manejan también con teclado
function interactivo(sel, {tip, accion, etiqueta}){
  sel.attr("tabindex", 0).attr("role", "button")
    .attr("aria-label", etiqueta)
    .style("cursor", "pointer")
    .on("pointerenter", (ev, d) => mostrarTooltip(ev, tip(d)))
    .on("pointermove", moverTooltip)
    .on("pointerleave", ocultarTooltip)
    .on("focus", (ev, d) => mostrarTooltip(ev, tip(d)))
    .on("blur", ocultarTooltip)
    .on("click", (ev, d) => { ocultarTooltip(); accion(d); })
    .on("keydown", (ev, d) => {
      if (ev.key === "Enter" || ev.key === " "){ ev.preventDefault(); accion(d); }
    });
}

/* Actividad mensual. Se recalcula sobre el resultado filtrado, lo que resuelve
   de paso el problema de escala: el Parlamento publica unas 23 veces menos que
   el Gobierno y en un eje compartido sería una línea invisible. Al filtrar por
   fuente el eje se reescala y se lee bien, sin recurrir a un doble eje. */
function GraficoMensual({datos, serie, mesSel, enRango, etiquetaN, onMes}){
  const ref = useRef(null);
  const ancho = useAncho(ref);

  useEffect(() => {
    const cont = ref.current;
    if (!ancho) return;
    ocultarTooltip();
    cont.innerHTML = "";
    const alto = 160, m = {arriba: 10, derecha: 4, abajo: 22, izquierda: 38};
    const meses = datos.map(d => d.mes);
    const svg = d3.select(cont).append("svg")
      .attr("width", ancho).attr("height", alto).attr("role", "group")
      .attr("aria-label", `${etiquetaN} por mes`);

    const x = d3.scaleBand().domain(meses).range([m.izquierda, ancho - m.derecha]).padding(0.2);
    const y = d3.scaleLinear().domain([0, d3.max(datos, d => d.n) || 1]).nice()
      .range([alto - m.abajo, m.arriba]);

    svg.append("g").attr("class", "eje")
      .attr("transform", `translate(${m.izquierda},0)`)
      .call(d3.axisLeft(y).ticks(4).tickFormat(d => Number.isInteger(d) ? num(d) : "")
        .tickSize(-(ancho - m.izquierda - m.derecha)).tickPadding(6));

    // Las etiquetas del eje se espacian según el ancho disponible, en pasos
    // que respetan los trimestres. El año se escribe en la primera etiqueta de
    // cada año: la serie arranca en mayo y, sin esto, el eje decía «may ago nov
    // feb…» sin forma de saber de qué año era cada barra.
    const caben = Math.max(1, (ancho - m.izquierda) / 46);
    const paso = [1, 2, 3, 4, 6, 12].find(p => meses.length / p <= caben) || 12;
    const visibles = meses.filter((_, i) => i % paso === 0);
    const primeros = new Set();
    let anio = null;
    visibles.forEach(v => { if (v.slice(0, 4) !== anio){ primeros.add(v); anio = v.slice(0, 4); } });

    svg.append("g").attr("class", "eje")
      .attr("transform", `translate(0,${alto - m.abajo})`)
      .call(d3.axisBottom(x).tickSize(0).tickPadding(7).tickValues(visibles)
        .tickFormat(v => {
          const mes = MESES[+v.slice(5) - 1].slice(0, 3);
          return primeros.has(v) ? `${mes} ${v.slice(2, 4)}` : mes;
        }))
      .call(g => g.selectAll(".tick text").filter(d => primeros.has(d))
        .style("font-weight", 600).style("fill", "var(--text-main)"));

    const w = x.bandwidth();
    svg.append("g").attr("pointer-events", "none").selectAll("path").data(datos).join("path")
      .attr("d", d => barraVertical(x(d.mes), y(d.n), w, y(0) - y(d.n), 3))
      .style("fill", d => enRango(d.mes) ? serie : "var(--barra-apagada)");

    const paso2 = x.step();
    svg.append("g").selectAll("rect").data(datos).join("rect")
      .attr("class", "barra")
      .attr("x", d => x(d.mes) - (paso2 - w) / 2).attr("width", paso2)
      .attr("y", m.arriba).attr("height", alto - m.abajo - m.arriba)
      .style("fill", "transparent")
      .call(interactivo, {
        etiqueta: d => `${mesLargo(d.mes)}: ${num(d.n)}. ${d.mes === mesSel ? "Quitar el filtro de mes" : "Filtrar este mes"}`,
        tip: d => `<div class="t">${mesLargo(d.mes)}</div>
          <div class="f"><span>${etiquetaN}</span><b>${num(d.n)}</b></div>
          <div class="a">${d.mes === mesSel ? "Clic para quitar el filtro" : "Clic para ver solo este mes"}</div>`,
        accion: d => onMes(d.mes),
      });
  }, [datos, ancho, serie, mesSel, enRango, etiquetaN]);

  return html`<div ref=${ref} class="grafico"></div>`;
}

/* Distribución por una dimensión. Las barras marcadas conservan el color de la
   serie y las demás se apagan: la selección se lee sin leyenda. El orden es
   por volumen, pero el color nunca depende del puesto. */
function GraficoBarras({items, serie, hayMarcadas, onClic, etiquetaN}){
  const ref = useRef(null);
  const ancho = useAncho(ref);

  useEffect(() => {
    const cont = ref.current;
    if (!ancho) return;
    ocultarTooltip();
    cont.innerHTML = "";
    if (!items.length){
      cont.innerHTML = `<div class="nota" style="padding:30px 0;text-align:center">Sin datos para esta vista</div>`;
      return;
    }
    const fila = 24, alto = items.length * fila + 6;
    const etq = Math.min(190, Math.max(110, ancho * .42));
    const derecha = 44;
    const caracteres = Math.floor(etq / 6.3);
    const svg = d3.select(cont).append("svg")
      .attr("width", ancho).attr("height", alto).attr("role", "group")
      .attr("aria-label", "Distribución del resultado");
    const x = d3.scaleLinear().domain([0, d3.max(items, d => d.n) || 1]).range([0, ancho - etq - derecha]);

    const g = svg.selectAll("g.fila").data(items).join("g")
      .attr("class", "fila").attr("transform", (d, i) => `translate(0,${i * fila + 3})`);
    g.append("text").attr("class", "etq-barra").attr("x", etq - 8).attr("y", fila / 2 - 1)
      .attr("text-anchor", "end").attr("dominant-baseline", "middle")
      .style("font-weight", d => d.marcado ? 600 : 400)
      .text(d => recortar(d.etiqueta, caracteres));
    g.append("path")
      .attr("d", d => barraHorizontal(etq, 3, x(d.n), fila - 10, 3))
      .style("fill", d => !hayMarcadas || d.marcado ? serie : "var(--barra-apagada)");
    g.append("text").attr("class", "val-barra")
      .attr("x", d => etq + x(d.n) + 6).attr("y", fila / 2 - 1).attr("dominant-baseline", "middle")
      .text(d => num(d.n));
    g.append("rect").attr("class", "barra")
      .attr("x", 0).attr("y", 0).attr("width", ancho).attr("height", fila - 2)
      .style("fill", "transparent")
      .call(interactivo, {
        etiqueta: d => `${d.completa}: ${num(d.n)}. ${d.marcado ? "Quitar filtro" : "Filtrar"}`,
        tip: d => `<div class="t">${escapar(d.completa)}</div>
          <div class="f"><span>${etiquetaN}</span><b>${num(d.n)}</b></div>
          <div class="a">${d.marcado ? "Clic para quitar el filtro" : "Clic para filtrar"}</div>`,
        accion: d => onClic(d.clave),
      });
  }, [items, ancho, serie, hayMarcadas, etiquetaN]);

  return html`<div ref=${ref} class="grafico"></div>`;
}

/* ------------------------------------------------------------ componentes */
function Logo(){
  return html`<svg viewBox="0 0 32 32" aria-hidden="true">
    <circle cx="16" cy="16" r="10.5" fill="none" stroke="#00C8B4" stroke-width="2.4"/>
    <circle cx="16" cy="16" r="3.2" fill="#00C8B4"/>
    <path d="M16 1.5v5M16 25.5v5M1.5 16h5M25.5 16h5" stroke="#00C8B4" stroke-width="2.4" stroke-linecap="round"/>
  </svg>`;
}

function Cabecera({base}){
  const t = base.total;
  const actualizado = base.generado
    ? "Actualizado el " + new Date(base.generado).toLocaleString("es-ES", {
        timeZone: "Atlantic/Canary", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit"})
    : "Datos hasta el " + fechaLarga(base.filas[0].fecha);
  const desde = base.filas[base.filas.length - 1].fecha;
  return html`<header class="hero">
    <div class="wrap">
      <div class="hero-top">
        <div class="marca"><${Logo}/><span class="label">ODESOCAN · Observatorio de Derechos Sociales de Canarias</span></div>
        <span class="hero-badge"><i></i>${actualizado}</span>
      </div>
      <h1>Actividad <em>ejecutiva y parlamentaria</em> de Canarias</h1>
      <p>Buscador de las publicaciones del Gobierno de Canarias y de las iniciativas del
        Parlamento de Canarias desde el ${fechaLarga(desde)}. Filtra por área, grupo,
        isla, materia o fecha, y comparte cualquier vista con su enlace.</p>
      <div class="kpis">
        <div class="kpi"><b>${num(t.todo)}</b><span>Publicaciones</span></div>
        <div class="kpi"><b>${num(t.gob)}</b><span>Gobierno</span></div>
        <div class="kpi"><b>${num(t.par)}</b><span>Parlamento</span></div>
        <div class="kpi"><b>${num(t.dec)}</b><span>Decisiones detectadas</span></div>
      </div>
    </div>
  </header>`;
}

function Faceta({titulo, opciones, seleccion, onAlternar, onLimpiar, limite = 7, nota}){
  const [todas, setTodas] = useState(false);
  const visibles = todas ? opciones : opciones.slice(0, limite);
  // Lo marcado se ve siempre, aunque quede fuera del recorte
  opciones.slice(limite).forEach(o => {
    if (!todas && seleccion.includes(o.valor)) visibles.push(o);
  });
  if (!opciones.length) return null;
  return html`<section class="faceta">
    <div class="faceta-cab">
      <h4>${titulo}</h4>
      ${seleccion.length ? html`<button onClick=${onLimpiar}>Quitar</button>` : null}
    </div>
    <div class="opciones">
      ${visibles.map(o => html`<button key=${o.valor} class=${"opcion" + (o.n ? "" : " cero")}
          aria-pressed=${seleccion.includes(o.valor) ? "true" : "false"}
          title=${o.completa || o.etiqueta}
          onClick=${() => onAlternar(o.valor)}>
        <span class="caja"></span><span>${o.etiqueta}</span><span class="cuenta">${num(o.n)}</span>
      </button>`)}
    </div>
    ${opciones.length > limite ? html`<button class="ver-mas" onClick=${() => setTodas(!todas)}>
      ${todas ? "Ver menos" : `Ver las ${opciones.length}`}</button>` : null}
    ${nota ? html`<p class="nota">${nota}</p>` : null}
  </section>`;
}

// Opciones de una faceta a partir de sus recuentos, con lo marcado aunque cuente cero
function opcionesDe(mapa, seleccion, etiqueta, completa){
  const valores = new Set([...mapa.keys(), ...seleccion]);
  return [...valores].map(v => ({valor: v, n: mapa.get(v) || 0, etiqueta: etiqueta(v),
                                 completa: completa ? completa(v) : etiqueta(v)}))
    .sort((a, b) => b.n - a.n || a.etiqueta.localeCompare(b.etiqueta, "es"));
}

function resaltar(texto, palabras){
  if (!palabras.length || !texto) return texto;
  // Se busca sobre el texto normalizado pero se recorta sobre el original, para
  // no perder tildes ni mayúsculas en lo que se muestra.
  const plano = normalizar(texto);
  const marcas = [];
  palabras.forEach(p => {
    let i = plano.indexOf(p);
    while (i !== -1){ marcas.push([i, i + p.length]); i = plano.indexOf(p, i + p.length); }
  });
  if (!marcas.length) return texto;
  marcas.sort((a, b) => a[0] - b[0]);
  const trozos = [];
  let cursor = 0;
  marcas.forEach(([a, b], k) => {
    if (a < cursor) return;
    trozos.push(texto.slice(cursor, a), html`<mark key=${k}>${texto.slice(a, b)}</mark>`);
    cursor = b;
  });
  trozos.push(texto.slice(cursor));
  return trozos;
}

function Tarjeta({r, base, palabras, e, alternar, actualizar}){
  const esGob = r.fuente === "0";
  const nombreArea = base.nombresArea[r.area] || r.area;
  const quien = esGob
    ? html`<button onClick=${() => alternar("area", r.area)} title="Filtrar por esta área">${nombreArea}</button>`
    : r.grupos.map((g, k) => html`<span key=${g}>${k ? ", " : ""}<button
        onClick=${() => alternar("grupo", g)} title="Filtrar por este grupo">${g}</button></span>`);
  const territorio = r.terr === AUTONOMICO || r.terr === VARIAS
    ? html`<button onClick=${() => actualizar({isla: r.isla, muni: ""})}
        title="Filtrar por este ámbito">${r.terr === AUTONOMICO ? "Ámbito autonómico" : VARIAS}</button>`
    : html`<button onClick=${() => actualizar(r.terr === r.isla ? {isla: r.isla, muni: ""} : {isla: r.isla, muni: r.terr})}
        title="Filtrar por este territorio">${r.terr}${r.terr !== r.isla ? ` (${r.isla})` : ""}</button>`;

  return html`<article class="tarjeta">
    <div class=${"origen " + (esGob ? "gob" : "par")}>${esGob ? "Gobierno de Canarias" : "Parlamento de Canarias"}</div>
    <h3><a href=${r.url} target="_blank" rel="noopener">${resaltar(r.titulo, palabras)}</a></h3>
    <div class="meta">${quien} · ${fechaCorta(r.fecha)} · ${territorio}${r.sit ? " · " + r.sit : ""}</div>
    ${r.entrada ? html`<div class="entradilla">${resaltar(r.entrada, palabras)}</div>` : null}
    <div class="pills">
      ${r.dec ? html`<button class="pill alerta" onClick=${() => actualizar({dec: true})}
                   title="Ver solo decisiones">Decisión</button>` : null}
      ${r.tipo ? html`<button class="pill tipo" onClick=${() => alternar("tipo", r.tipo)}
                   title="Filtrar por este tipo">${base.nombresTipo[r.tipo] || r.tipo}</button>` : null}
      ${!esGob && r.area !== "sin_asignar" ? html`<button class="pill neutra"
          onClick=${() => alternar("area", r.area)} title=${nombreArea}>${recortar(cortoArea(nombreArea), 34)}</button>` : null}
      ${r.mats.map(m => html`<button key=${m} class="pill" aria-pressed=${e.mat.includes(m) ? "true" : "false"}
          onClick=${() => alternar("mat", m)} title="Filtrar por esta materia">${materia(m)}</button>`)}
      <a class="enlace" href=${r.url} target="_blank" rel="noopener">Ver publicación →</a>
    </div>
  </article>`;
}

function Paginacion({pagina, paginas, ir}){
  if (paginas <= 1) return null;
  const cerca = [...new Set([1, paginas, pagina, pagina - 1, pagina + 1])]
    .filter(n => n >= 1 && n <= paginas).sort((a, b) => a - b);
  const botones = [];
  let ultima = 0;
  cerca.forEach(n => {
    if (n - ultima > 1) botones.push(html`<span key=${"p" + n} class="puntos">…</span>`);
    botones.push(html`<button key=${n} aria-current=${n === pagina ? "page" : null}
      onClick=${() => ir(n)}>${n}</button>`);
    ultima = n;
  });
  return html`<nav class="paginacion" aria-label="Paginación">
    <button disabled=${pagina === 1} aria-label="Página anterior" onClick=${() => ir(pagina - 1)}>←</button>
    ${botones}
    <button disabled=${pagina === paginas} aria-label="Página siguiente" onClick=${() => ir(pagina + 1)}>→</button>
  </nav>`;
}

/* CSV con punto y coma y BOM: es lo que abre bien Excel en español sin pasar
   por el asistente de importación. */
function descargarCSV(filas, base){
  const cab = ["fecha","fuente","titulo","entradilla","url","area","territorio","isla",
               "grupo_parlamentario","tipo_iniciativa","situacion","decision","materias"];
  const celda = v => {
    const s = String(v ?? "");
    return /[;"\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  const lineas = filas.map(r => [
    r.fecha, r.fuente === "0" ? "Gobierno" : "Parlamento", r.titulo, r.entrada, r.url,
    base.nombresArea[r.area] || r.area, r.terr, r.isla, r.grupos.join(" | "),
    r.tipo ? (base.nombresTipo[r.tipo] || r.tipo) : "", r.sit || "", r.dec ? "sí" : "no",
    r.mats.map(materia).join(" | "),
  ].map(celda).join(";"));
  const blob = new Blob(["\ufeff" + [cab.join(";"), ...lineas].join("\r\n")], {type: "text/csv;charset=utf-8"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `transparencia-gobcan-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function BotonTema(){
  const [tema, setTema] = useState(document.documentElement.getAttribute("data-tema") || "claro");
  useEffect(() => {
    // Mientras no se elija, manda el sistema, aunque cambie con la página abierta
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const seguir = ev => {
      let guardado = null;
      try { guardado = localStorage.getItem("tema-transparencia"); } catch (err) { /* modo privado */ }
      if (!guardado) aplicar(ev.matches ? "oscuro" : "claro");
    };
    mq.addEventListener("change", seguir);
    return () => mq.removeEventListener("change", seguir);
  }, []);
  function aplicar(nuevo){
    document.documentElement.setAttribute("data-tema", nuevo);
    setTema(nuevo);
  }
  function alternarTema(){
    const nuevo = tema === "oscuro" ? "claro" : "oscuro";
    try { localStorage.setItem("tema-transparencia", nuevo); } catch (err) { /* modo privado */ }
    aplicar(nuevo);
  }
  return html`<button class="btn btn-tema" onClick=${alternarTema}
      aria-label=${tema === "oscuro" ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}>
    <svg class="luna" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
    <svg class="sol" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/>
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>
    <span>${tema === "oscuro" ? "Claro" : "Oscuro"}</span>
  </button>`;
}

/* ---------------------------------------------------------------- aplicación */
function App({base}){
  const [e, setE] = useState(leerHash);
  const [texto, setTexto] = useState(e.q);
  const [panel, setPanel] = useState(false);
  const [pestana, setPestana] = useState("area");
  const esPar = e.f === "1";

  useEffect(() => escribirHash(e), [e]);
  useEffect(() => {
    const alCambiar = () => { const n = leerHash(); setE(n); setTexto(n.q); };
    addEventListener("hashchange", alCambiar);
    return () => removeEventListener("hashchange", alCambiar);
  }, []);

  // Con 16.000 filas, filtrar en cada pulsación se nota al teclear
  useEffect(() => {
    if (texto === e.q) return;
    const t = setTimeout(() => setE(prev => ({...prev, q: texto, p: 1})), 180);
    return () => clearTimeout(t);
  }, [texto]);

  const actualizar = useCallback(cambios => setE(prev => ({...prev, p: 1, ...cambios})), []);
  const alternar = useCallback((clave, valor) => setE(prev => {
    const lista = prev[clave];
    return {...prev, p: 1, [clave]: lista.includes(valor) ? lista.filter(v => v !== valor) : [...lista, valor]};
  }), []);

  const {resultado, cuentas, palabras} = useMemo(() => calcular(base.filas, e),
    [base, e.f, e.q, e.desde, e.hasta, e.area, e.grupo, e.tipo, e.sit, e.isla, e.muni, e.mat, e.dec]);
  const ordenado = useMemo(() => e.orden === "asc" ? resultado.slice().reverse() : resultado,
    [resultado, e.orden]);

  const serie = esPar ? "var(--serie-par)" : "var(--serie-gob)";
  const etiquetaN = esPar ? "Iniciativas" : "Publicaciones";

  // ---- gráfico mensual
  // Sale de los recuentos de la faceta de fecha, que no aplican el propio
  // filtro de fechas: los meses fuera del rango se ven apagados, no a cero
  const mensual = useMemo(() => base.meses.map(mes => ({mes, n: cuentas.fecha.get(mes) || 0})),
    [cuentas, base]);
  const enRango = useCallback(mes =>
    (!e.desde || mes >= e.desde.slice(0, 7)) && (!e.hasta || mes <= e.hasta.slice(0, 7)),
    [e.desde, e.hasta]);
  const mesSel = e.desde && e.hasta && e.desde.slice(0, 7) === e.hasta.slice(0, 7)
    && limitesMes(e.desde.slice(0, 7)).join() === [e.desde, e.hasta].join() ? e.desde.slice(0, 7) : null;
  const onMes = useCallback(mes => setE(prev => {
    const [desde, hasta] = limitesMes(mes);
    const ya = prev.desde === desde && prev.hasta === hasta;
    return {...prev, p: 1, desde: ya ? "" : desde, hasta: ya ? "" : hasta};
  }), []);

  // ---- gráfico de distribución
  const pest = pestana === "grupo" && !esPar ? "area" : pestana;
  const distribucion = useMemo(() => {
    const mapa = {area: cuentas.area, grupo: cuentas.grupo, isla: cuentas.isla, mat: cuentas.mat}[pest];
    const marcado = {
      area: v => e.area.includes(v), grupo: v => e.grupo.includes(v),
      isla: v => e.isla === v, mat: v => e.mat.includes(v),
    }[pest];
    const nombre = {
      area: v => base.nombresArea[v] || v, grupo: v => v, isla: v => v, mat: materia,
    }[pest];
    const corto = {area: v => cortoArea(nombre(v)), grupo: cortoGrupo, isla: v => v, mat: materia}[pest];
    return [...mapa.entries()]
      // Lo autonómico no es una isla y aplastaría la escala de las demás
      .filter(([v, n]) => n > 0 && !(pest === "isla" && v === AUTONOMICO))
      .map(([v, n]) => ({clave: v, n, etiqueta: corto(v), completa: nombre(v), marcado: marcado(v)}))
      .sort((a, b) => b.n - a.n);
  }, [cuentas, pest, e.area, e.grupo, e.isla, e.mat, base]);
  const onDistribucion = useCallback(v => {
    if (pest === "isla") setE(prev => ({...prev, p: 1, isla: prev.isla === v ? "" : v, muni: ""}));
    else alternar(pest, v);
  }, [pest, alternar]);
  const autonomicas = cuentas.isla.get(AUTONOMICO) || 0;

  // ---- paginación
  const paginas = Math.max(1, Math.ceil(ordenado.length / POR_PAGINA));
  const pagina = Math.min(e.p, paginas);
  const trozo = ordenado.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA);
  const irA = n => {
    setE(prev => ({...prev, p: n}));
    document.getElementById("resumen").scrollIntoView({behavior: "smooth", block: "start"});
  };

  // ---- conmutador de fuente: lo que solo existe en el Parlamento se limpia
  const cambiarFuente = f => actualizar({f, grupo: [], tipo: [], sit: []});

  // ---- chips de filtros activos
  const chips = [];
  if (e.q) chips.push({t: `«${e.q}»`, quitar: () => { setTexto(""); actualizar({q: ""}); }});
  if (e.desde || e.hasta) chips.push({
    t: mesSel ? mesLargo(mesSel) : `${e.desde ? fechaCorta(e.desde) : "…"} – ${e.hasta ? fechaCorta(e.hasta) : "hoy"}`,
    quitar: () => actualizar({desde: "", hasta: ""})});
  e.area.forEach(v => chips.push({t: recortar(cortoArea(base.nombresArea[v] || v), 36), quitar: () => alternar("area", v)}));
  e.grupo.forEach(v => chips.push({t: cortoGrupo(v), quitar: () => alternar("grupo", v)}));
  e.tipo.forEach(v => chips.push({t: base.nombresTipo[v] || v, quitar: () => alternar("tipo", v)}));
  e.sit.forEach(v => chips.push({t: v, quitar: () => alternar("sit", v)}));
  if (e.isla) chips.push({t: e.isla === AUTONOMICO ? "Ámbito autonómico" : e.isla, quitar: () => actualizar({isla: "", muni: ""})});
  if (e.muni) chips.push({t: e.muni, quitar: () => actualizar({muni: ""})});
  e.mat.forEach(v => chips.push({t: materia(v), quitar: () => alternar("mat", v)}));
  if (e.dec) chips.push({t: "Solo decisiones", quitar: () => actualizar({dec: false})});
  const limpiarTodo = () => { setTexto(""); setE({...INICIAL, f: e.f, orden: e.orden}); };

  // ---- opciones de las facetas
  const optsArea = opcionesDe(cuentas.area, e.area, v => cortoArea(base.nombresArea[v] || v), v => base.nombresArea[v] || v);
  const optsGrupo = opcionesDe(cuentas.grupo, e.grupo, cortoGrupo, v => v);
  const optsTipo = opcionesDe(cuentas.tipo, e.tipo, v => base.nombresTipo[v] || v);
  const optsSit = opcionesDe(cuentas.sit, e.sit, v => v);
  const optsMat = opcionesDe(cuentas.mat, e.mat, materia);
  const optsIsla = opcionesDe(cuentas.isla, e.isla ? [e.isla] : [],
    v => v === AUTONOMICO ? "Ámbito autonómico" : v);
  const esIsla = e.isla && e.isla !== AUTONOMICO && e.isla !== VARIAS && base.tieneIslas;
  const optsMuni = esIsla
    ? [...cuentas.muni.entries()].filter(([v]) => v !== e.isla)
        .sort((a, b) => a[0].localeCompare(b[0], "es"))
    : [];
  const nDec = cuentas.dec.get("1") || 0;
  const nFiltros = chips.length;

  return html`
    <${Cabecera} base=${base}/>

    <div class="filtros">
      <div class="wrap">
        <div class="conmutador" role="group" aria-label="Fuente">
          ${[["0", "Gobierno"], ["1", "Parlamento"]].map(([f, t]) => html`
            <button key=${f} aria-pressed=${e.f === f ? "true" : "false"} onClick=${() => cambiarFuente(f)}>
              ${t} <small>${num(cuentas.fuente.get(f) || 0)}</small></button>`)}
        </div>
        <input type="search" value=${texto} onInput=${ev => setTexto(ev.target.value)}
          placeholder="Buscar por palabra clave…" aria-label="Buscar por palabra clave"/>
        <div class="fechas">
          <input type="date" value=${e.desde} max=${e.hasta || null} aria-label="Desde"
            onChange=${ev => actualizar({desde: ev.target.value})}/>
          <span>a</span>
          <input type="date" value=${e.hasta} min=${e.desde || null} aria-label="Hasta"
            onChange=${ev => actualizar({hasta: ev.target.value})}/>
        </div>
        <button class="btn btn-panel" aria-expanded=${panel ? "true" : "false"} aria-controls="panel"
            onClick=${() => setPanel(!panel)}>
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h18M6 12h12M10 19h4"/></svg>
          Filtros${nFiltros ? ` (${nFiltros})` : ""}
        </button>
        <${BotonTema}/>
      </div>
    </div>

    <main class="wrap rejilla">
      <aside id="panel" class=${"panel" + (panel ? " abierto" : "")} aria-label="Filtros">
        <section class="faceta">
          <label class="interruptor">
            <span><b>Solo decisiones</b> <span class="cuenta nota">(${num(nDec)})</span></span>
            <input type="checkbox" checked=${e.dec} onChange=${ev => actualizar({dec: ev.target.checked})}/>
          </label>
          <p class="nota">Normas, acuerdos y planes que la capa de alertas marca como decisión.</p>
        </section>
        ${esPar ? html`
          <${Faceta} titulo="Grupo proponente" opciones=${optsGrupo} seleccion=${e.grupo}
            onAlternar=${v => alternar("grupo", v)} onLimpiar=${() => actualizar({grupo: []})}
            nota="Las iniciativas firmadas por varios grupos cuentan para cada uno."/>
          <${Faceta} titulo="Tipo de iniciativa" opciones=${optsTipo} seleccion=${e.tipo}
            onAlternar=${v => alternar("tipo", v)} onLimpiar=${() => actualizar({tipo: []})}/>
          <${Faceta} titulo="Situación" opciones=${optsSit} seleccion=${e.sit}
            onAlternar=${v => alternar("sit", v)} onLimpiar=${() => actualizar({sit: []})}/>` : null}
        <${Faceta} titulo=${esPar ? "Área (por comisión)" : "Área · consejería"} opciones=${optsArea}
          seleccion=${e.area} onAlternar=${v => alternar("area", v)} onLimpiar=${() => actualizar({area: []})}/>
        <${Faceta} titulo="Materia" opciones=${optsMat} seleccion=${e.mat}
          onAlternar=${v => alternar("mat", v)} onLimpiar=${() => actualizar({mat: []})}
          nota="Materias de derechos sociales detectadas en el texto."/>
        <section class="faceta">
          <div class="faceta-cab">
            <h4>Territorio</h4>
            ${e.isla ? html`<button onClick=${() => actualizar({isla: "", muni: ""})}>Quitar</button>` : null}
          </div>
          <select aria-label="Isla o ámbito" value=${e.isla}
              onChange=${ev => actualizar({isla: ev.target.value, muni: ""})}>
            <option value="">Todas las islas y ámbitos</option>
            ${optsIsla.map(o => html`<option key=${o.valor} value=${o.valor}>${o.etiqueta} (${num(o.n)})</option>`)}
          </select>
          ${esIsla && optsMuni.length ? html`
            <select aria-label="Municipio" value=${e.muni} style=${{marginTop: "8px"}}
                onChange=${ev => actualizar({muni: ev.target.value})}>
              <option value="">Toda la isla</option>
              ${optsMuni.map(([v, n]) => html`<option key=${v} value=${v}>${v} (${num(n)})</option>`)}
            </select>` : null}
          <p class="nota">El territorio se infiere del texto; la fuente no lo publica. Sin mención
            concreta, la publicación cuenta como de ámbito autonómico.</p>
        </section>
      </aside>

      <div>
        <p class="aviso"><b>Nota</b>Las dos fuentes son portales de comunicación institucional:
          recogen lo que cada gabinete decide contar. Que una medida no aparezca aquí no
          significa que no exista.</p>

        ${chips.length ? html`<div class="activos" aria-label="Filtros activos">
          ${chips.map((c, k) => html`<button key=${k} class="chip" onClick=${c.quitar}
              aria-label=${"Quitar filtro " + c.t}>${c.t}<i aria-hidden="true">×</i></button>`)}
          ${chips.length > 1 ? html`<button class="chip-limpiar" onClick=${limpiarTodo}>Quitar todos</button>` : null}
        </div>` : null}

        <div class="graficos">
          <figure class="chart-container">
            <span class="chart-etiqueta">Gráfico 1.</span>
            <div class="chart-tit">${etiquetaN} por mes · ${esPar ? "Parlamento" : "Gobierno"} de Canarias</div>
            <div class="chart-sub">${nFiltros ? "Sobre el resultado filtrado" : "Sin filtros aplicados"} · clic en una barra para ver ese mes</div>
            <${GraficoMensual} datos=${mensual} serie=${serie} mesSel=${mesSel} enRango=${enRango}
              etiquetaN=${etiquetaN} onMes=${onMes}/>
            <figcaption>Fuente: ${esPar ? "Parlamento de Canarias, consulta de iniciativas" : "Portal de Noticias del Gobierno de Canarias"}. Elaboración: ODESOCAN.</figcaption>
          </figure>
          <figure class="chart-container">
            <div class="chart-cab">
              <div>
                <span class="chart-etiqueta">Gráfico 2.</span>
                <div class="chart-tit">Distribución del resultado</div>
              </div>
              <div class="pestanas" role="tablist" aria-label="Dimensión">
                ${[["area", "Área"], ...(esPar ? [["grupo", "Grupo"]] : []), ["mat", "Materia"], ["isla", "Isla"]]
                  .map(([k, t]) => html`<button key=${k} role="tab" aria-selected=${pest === k ? "true" : "false"}
                    onClick=${() => setPestana(k)}>${t}</button>`)}
              </div>
            </div>
            <${GraficoBarras} items=${distribucion} serie=${serie} etiquetaN=${etiquetaN}
              hayMarcadas=${distribucion.some(d => d.marcado)} onClic=${onDistribucion}/>
            <figcaption>${pest === "isla"
              ? `No incluye ${num(autonomicas)} ${autonomicas === 1 ? "publicación" : "publicaciones"} de ámbito autonómico. `
              : pest === "mat" ? "Una publicación puede tratar varias materias. " : ""}Clic en una barra para filtrar.</figcaption>
          </figure>
        </div>

        <div class="resumen" id="resumen">
          <div class="n">${ordenado.length
            ? html`<b>${num(ordenado.length)}</b> ${ordenado.length === 1 ? (esPar ? "iniciativa" : "publicación") : etiquetaN.toLowerCase()}
                ${nFiltros ? html` <small>de ${num(esPar ? base.total.par : base.total.gob)}</small>` : null}`
            : "Sin resultados"}</div>
          <div class="acciones">
            <select aria-label="Orden" value=${e.orden} onChange=${ev => setE(prev => ({...prev, orden: ev.target.value, p: 1}))}>
              <option value="desc">Más recientes primero</option>
              <option value="asc">Más antiguas primero</option>
            </select>
            <button class="btn" disabled=${!ordenado.length} onClick=${() => descargarCSV(ordenado, base)}
                title="Descarga el resultado filtrado completo">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3v12M7 10l5 5 5-5M4 20h16"/></svg>
              CSV
            </button>
          </div>
        </div>

        ${ordenado.length
          ? trozo.map(r => html`<${Tarjeta} key=${r.i} r=${r} base=${base} palabras=${palabras}
              e=${e} alternar=${alternar} actualizar=${actualizar}/>`)
          : html`<div class="vacio"><strong>No hay publicaciones que coincidan</strong>
              Prueba a quitar algún filtro o a buscar otra palabra.</div>`}
        <${Paginacion} pagina=${pagina} paginas=${paginas} ir=${irA}/>
      </div>
    </main>

    <footer>
      <div class="wrap">
        <span><b>ODESOCAN</b> · Observatorio de Derechos Sociales de Canarias · <a href="mailto:info@odesocan.org">info@odesocan.org</a></span>
        <span>transparencia-gobcan v${base.version} · <a href="https://github.com/Odesocan/transparencia-gobcan">código</a></span>
      </div>
    </footer>`;
}

/* ---------------------------------------------------------------- arranque
   El volcado pesa unos 8 MB (2 comprimido). Se pide después de pintar la
   página, y no con un <script> en el HTML, para que mientras llega se vea la
   cabecera y un indicador en vez de una pantalla en blanco. Sigue siendo un
   <script> y no un fetch: Chrome bloquea fetch desde file://. */
const raiz = ReactDOM.createRoot(document.getElementById("app"));

// Un error al pintar desmontaría toda la página y la dejaría en blanco. Así se
// ve qué ha pasado y se puede volver a la vista sin filtros.
class LimiteError extends React.Component {
  constructor(props){ super(props); this.state = {error: null}; }
  static getDerivedStateFromError(error){ return {error}; }
  render(){
    if (!this.state.error) return this.props.children;
    return html`<div class="wrap" style=${{padding: "40px 18px"}}><div class="vacio">
      <strong>Algo ha fallado al mostrar esta vista</strong>
      <p>${String(this.state.error.message || this.state.error)}</p>
      <button class="btn btn-primario" onClick=${() => { location.hash = ""; location.reload(); }}>
        Volver a la vista inicial</button></div></div>`;
  }
}

function montar(){
  if (!window.DATOS_TRANSPARENCIA) return fallo();
  const base = preparar(window.DATOS_TRANSPARENCIA);
  raiz.render(html`<${LimiteError}><${App} base=${base}/></${LimiteError}>`);
}
function fallo(){
  document.getElementById("app").innerHTML = `<div class="wrap" style="padding:40px 18px">
    <div class="vacio"><strong>No se han podido cargar los datos</strong>
    Falta <code>datos.js</code> junto a este fichero. Se regenera con
    <code>transparencia exportar</code>, o se descarga como artefacto
    <code>datos-interfaz</code> desde la pestaña Actions del repositorio.</div></div>`;
}

if (window.DATOS_TRANSPARENCIA) montar();
else {
  const s = document.createElement("script");
  s.src = "datos.js";
  s.onload = montar;
  s.onerror = fallo;
  document.body.appendChild(s);
}
})();
