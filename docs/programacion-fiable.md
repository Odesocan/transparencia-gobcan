# Cómo se programa la ejecución, y por qué así

Resumen para quien tenga prisa: **el reloj es `pg_cron` en Supabase, no el cron
de GitHub**. La base llama a la API de GitHub para lanzar el workflow por
`workflow_dispatch`. El cron de GitHub sigue puesto, pero solo como red de
seguridad.

---

## El problema que resuelve

GitHub **no cumple los cron programados**. Medido sobre cuatro días reales:

| Hora UTC | Hora canaria | Cumplimiento |
|---|---|---|
| 07:00 | 08:00 | **0%** |
| 08:00 | 09:00 | **0%** |
| 09:00–19:00 | 10:00–20:00 | 12–25% |
| 21:00 | 22:00 | 50% |

De 25 ejecuciones diarias que pedía el cron, corrían 7 u 8. La separación real
entre ellas era de 104 minutos de mediana, con máximos de 197, y la primera del
día llegaba a las 10:33 en vez de a las 8:00.

No es un fallo del proyecto: los trabajos `schedule` tienen la prioridad más
baja de la cola de GitHub y se descartan cuando hay carga. Las 07:00-09:00 UTC
son hora punta mundial, que es justo cuando peor se cumple.

**Ninguna hora superaba el 25%**, así que no había ajuste de cron que lo
arreglara. Ese fue el momento de cambiar de enfoque.

> Aviso por si alguien intenta «arreglarlo» moviendo horas: ya se probó. Poner
> los intentos de la mañana a las 8:13 y 8:43 UTC fue peor, porque esa es
> precisamente la franja con 0% de cumplimiento.

## La arquitectura

```
pg_cron (Supabase, cumple horarios)
    └─> disparar_si_toca()      comprueba la hora canaria real
          └─> disparar_y_registrar()   deja rastro en transp_gobcan.disparos
                └─> pg_net → API de GitHub → workflow_dispatch
                      └─> el workflow se ejecuta al instante
```

`workflow_dispatch` **sí se ejecuta siempre**. La deprioritización solo afecta a
`schedule`.

**El cambio de hora se resuelve solo.** `pg_cron` corre en UTC igual que GitHub,
pero aquí la función comprueba `now() AT TIME ZONE 'Atlantic/Canary'` antes de
disparar. El cron cubre una franja UTC ancha y la función descarta lo que cae
fuera de la franja local. No hay que reajustar nada en octubre ni en marzo.

Horarios efectivos, siempre en hora canaria:

| Trabajo | Cuándo | Qué hace |
|---|---|---|
| `transparencia-jornada` | cada hora a y media, 9:30–20:30, L-V | Gobierno |
| `transparencia-cierre` | 22:00 todos los días | Gobierno + Parlamento |

---

## Cómo debe estar configurado el token

Vive en el Vault de Supabase con el nombre **`github_token_actions`**, que es el
que busca la función. Es un fine-grained personal access token con esto:

| Campo | Valor |
|---|---|
| **Resource owner** | `Odesocan` — la organización, **no** la cuenta personal |
| **Repository access** | Only select repositories → `transparencia-gobcan` |
| **Permissions → Repositories** | **Actions: Read and write** y Metadata: Read-only |
| **Permissions → Organizations** | ninguno |

Dos cosas que cuestan encontrar:

**El owner del repositorio es `Odesocan`, no `Cristianodesocan`.** Este último es
un nombre anterior de la cuenta. `gh` sigue el redirect y funciona; la API no lo
sigue en peticiones POST y responde 404.

**Seleccionar el repositorio no basta.** Hay que añadir además el permiso. Un
token con el repositorio en su lista pero con `Repositories: 0` en permisos no
puede ni leerlo, y GitHub responde 404 igual que si el repositorio no existiera.

---

## Diagnóstico cuando falla

GitHub responde **404 a casi todo** y no dice cuál de las cuatro causas
posibles es. Esta consulta lo resuelve en un segundo, y es por donde hay que
empezar siempre:

```sql
SELECT net.http_get(
  url := 'https://api.github.com/user/repos?per_page=100',
  headers := jsonb_build_object(
    'Authorization', 'Bearer ' || (SELECT decrypted_secret FROM vault.decrypted_secrets
                                    WHERE name='github_token_actions'),
    'Accept', 'application/vnd.github+json',
    'User-Agent', 'transparencia-gobcan-pgcron')
);
-- y con el id que devuelve:
SELECT status_code,
       (SELECT string_agg(r->>'full_name', ', ')
          FROM jsonb_array_elements(content::jsonb) r) AS repos_que_alcanza
FROM net._http_response WHERE id = <el_id>;
```

**Preguntarle al token qué repositorios ve es la prueba que resuelve el caso.**
Si devuelve 200 con una lista y `transparencia-gobcan` no aparece, el problema
está en ese token concreto y no en la organización ni en las credenciales. En el
episodio que motivó este documento se tardó en llegar aquí porque se supuso que
el 404 venía de la política de la organización, y esta consulta lo habría
señalado en el primer intento.

Tabla de códigos:

| Código | Qué significa | Qué hacer |
|---|---|---|
| **401** Bad credentials | El token no existe, se borró o se copió incompleto | Comprobar que tiene ~93 caracteres. Regenerar si hace falta |
| **404** en `/repos/...` pero **200** en `/user` | El token es válido pero no alcanza ESE repositorio | Añadir el repositorio **y sus permisos** al token |
| **404** en todo, incluido `/user/repos` | El token no está aprobado por la organización | Aprobar en `github.com/organizations/Odesocan/settings/personal-access-token-requests` |
| **204** en el dispatch | Correcto, GitHub acepta | Nada |

Y para ver si los disparos salen:

```sql
SELECT d.id, d.lanzado_en, r.status_code, left(r.content, 120) AS respuesta, d.error
FROM transp_gobcan.disparos d
LEFT JOIN net._http_response r ON r.id = d.peticion_id
ORDER BY d.id DESC LIMIT 10;
```

`status_code = 204` es lo correcto. Cualquier otra cosa, a la tabla de arriba.

---

## Cosas que romperán esto en el futuro

**El token caduca.** El actual expira el **28 de septiembre de 2026**. Cuando lo
haga, los disparos empezarán a devolver 401 y la automatización se parará **sin
avisar a nadie**: pg_cron no informa de fallos y GitHub tampoco, porque para él
la petición nunca llegó. La única señal será que `disparos` acumule 401 y que no
lleguen avisos. Anotado también en `vigilancia.md`.

**Si se renombra el repositorio o la organización**, hay que cambiar la URL en
`transp_gobcan.disparar_extraccion`. El redirect de GitHub no sirve para POST.

**Si se cambia el nombre del fichero del workflow**, lo mismo: la URL lo lleva
codificado como `extraccion.yml`.

## Lo que se descartó, y por qué

**Ajustar el cron de GitHub.** Ninguna hora pasaba del 25%. No había nada que
ajustar.

**Un token classic con scope `repo`.** Habría funcionado a la primera y sin
pasar por la aprobación de la organización, pero da acceso a **todos** los
repositorios de la cuenta. Para un token cuyo único trabajo es decir «lanza este
workflow», eso es mucho más poder del necesario. Si el fine-grained volviera a
dar problemas insalvables, es la salida de emergencia — sabiendo lo que se cede.

**Reescribir el pipeline como Edge Function de Supabase.** Eliminaría GitHub de
la ecuación, pero implica reescribir en TypeScript lo que hoy son 1.500 líneas
de Python probadas, y perder los tests. No compensa.

**Un servidor propio con systemd.** Infraestructura que hoy no existe y habría
que mantener, para ganar minutos que nadie va a usar.
