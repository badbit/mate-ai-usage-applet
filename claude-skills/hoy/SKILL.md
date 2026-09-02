---
name: hoy
description: Genera el resumen del día de Miguel — revisa la agenda de Google Calendar, el correo personal (disroot vía himalaya), el correo de trabajo (UABC vía Gmail MCP), las tareas de TickTick vencidas y de hoy, y los pendientes registrados en la memoria de Claude. Úsalo cuando pida "qué tengo que hacer hoy", "resumen del día", "mi día", "pendientes de hoy", "cómo viene mi día" o invoque /hoy.
---

# Resumen del día

Reúne en un solo lugar lo que Miguel debe atender hoy. Responde **siempre en español**.

## Paso 0 — Cargar herramientas (obligatorio)

Las herramientas MCP están diferidas al inicio de cada sesión. Cárgalas en **una sola** llamada a ToolSearch antes de nada:

```
ToolSearch query: "select:mcp__ticktick__list_undone_tasks_by_date,mcp__ticktick__list_projects,mcp__claude_ai_Gmail__search_threads,mcp__claude_ai_Gmail__get_thread,mcp__claude_ai_Google_Calendar__list_events"
```

## Paso 1 — Fecha local

Ejecuta `date +%F` para obtener la fecha de hoy en la zona horaria local (Mexicali, `America/Tijuana`). **No asumas UTC**: usa esa fecha local para construir los rangos ISO 8601 que necesites (p. ej. `2026-08-10T00:00:00-07:00`). Calcula también `hoy-7` y `mañana` con `date -d`.

## Paso 2 — Recolectar (en paralelo, una sola tanda de llamadas)

### a) Correo personal — disroot vía himalaya

```bash
himalaya envelope list -a Personal -s 40 -o json 'not flag seen and after AAAA-MM-DD'
```

- La fecha del filtro es **hoy menos 2 días**.
- El orden importa: primero las banderas (`-a`, `-s`, `-o`), al final la query entre comillas.
- Si necesitas el cuerpo de un correo concreto: `himalaya message read -a Personal <ID>`.
- Solo revisa `INBOX`. Las subcarpetas (`INBOX.Trabajo`, `INBOX.Papás`, `INBOX.Mailing lists`, …) son filtros del servidor y no entran al resumen salvo que Miguel lo pida.
- Hay backlog acumulado de no leídos (decenas). Por eso se acota a 2 días: **no** intentes vaciar el inbox.

### b) Correo de trabajo — UABC vía Gmail MCP

```
mcp__claude_ai_Gmail__search_threads  query: "in:inbox newer_than:2d"  pageSize: 25
```

Si un hilo parece pedir acción y el `snippet` no basta, usa `mcp__claude_ai_Gmail__get_thread` con su `id`.

### c) Tareas — TickTick

```
mcp__ticktick__list_undone_tasks_by_date
  search: { startDate: "<hoy-7>T00:00:00-07:00", endDate: "<mañana>T00:00:00-07:00" }
```

El rango hacia atrás sirve para **capturar lo vencido**, no solo lo de hoy. El máximo que acepta la API son 14 días.

**Ojo:** esta respuesta suele pasarse del límite de tokens y quedar volcada en un archivo (la herramienta te dará la ruta). Es lo normal, no un error: parsea el archivo con `python3` en vez de leerlo entero. En este equipo **no hay `jq`**.

```bash
python3 -c "
import json,sys
d=json.load(open(sys.argv[1]))['result']
print('TOTAL',len(d))
for t in sorted(d,key=lambda t:(t.get('dueDate') or 'zz')):
    print((t.get('dueDate') or '-')[:16],'| P'+str(t.get('priority',0)),'|',t.get('projectId','')[-6:],'|',(t.get('title') or '')[:75])
" <RUTA_DEL_ARCHIVO>
```

Prioridad TickTick: `P5` = alta, `P3` = media, `P1` = baja, `P0` = sin prioridad. Los `projectId` recortados se resuelven con `list_projects` si hace falta nombrar la lista.

Si algo no cuadra o Miguel pregunta por una lista concreta, `mcp__ticktick__list_projects` da los IDs (Doctorado, CIAD, Clases y tutorías, Salud, Dinero, Boda, etc.).

### d) Agenda — Google Calendar

Miguel tiene **13 calendarios**. `list_events` consulta **uno a la vez**, así que solo se revisan estos tres, en el mismo rango de hoy (00:00 a 24:00 hora local):

| Calendario | `calendarId` | Qué sacar |
|---|---|---|
| Principal (trabajo) | `lozano.miguel@uabc.edu.mx` | Todo |
| Papá | `c_301d889dfbda69bcc99171476df7cda391d8d062520eb4d5efa354d20a082d62@group.calendar.google.com` | Solo turnos de cuidadoras |
| Claudia | `lecon.claudia.108@gmail.com` | Solo lo que involucre a Miguel |

```
mcp__claude_ai_Google_Calendar__list_events
  calendarId: "<id>"
  startTime: "<hoy>T00:00:00-07:00"
  endTime: "<mañana>T00:00:00-07:00"
  orderBy: "startTime"
  pageSize: 20
```

**El calendario de Papá es una rutina de cuidados completa**, no la agenda de Miguel: desayuno, baño, siesta, comida, cena, recreación, paseo de mascotas, ejercicio, natación. **Descarta todo eso.** Quedan los eventos con nombre de persona (Adriana Robles, Ana Lorena, Cecilia, Primi…), que son los turnos de las cuidadoras — resúmelos en **una sola línea**, no uno por punto.

**Calendarios que NO se revisan** (ruido o duplicado):
- `TickTick` — duplica exactamente lo que ya sale de TickTick.
- Festivos (México, Francia, cristianos), NYT Astronomy, Mundial 26.
- Los `2026-I …` de Classroom: ahí van fechas que Miguel pone a sus alumnos, no pendientes suyos.
- `Semana del Arte Mexicali`: solo si Miguel lo pide o si es temporada del evento.

En el resumen, la agenda va **primero**: es lo que fija las horas disponibles del día.

### e) Pendientes en memoria

`MEMORY.md` ya viene cargado en el contexto de la sesión. Revísalo y **lee solo** los archivos `project_*.md` de `~/.claude/projects/-home-badbit/memory/` cuya línea sugiera trabajo abierto o decisiones sin tomar. No leas los `setup_*`, `user_*` ni `feedback_*`: son configuración y preferencias, no pendientes.

## Paso 3 — Filtrar ruido

Descarta antes de redactar:

- Promociones, newsletters y ofertas (Temu, Pinterest, Chatbooks, OfferUp, Substack…).
- Confirmaciones automáticas: envíos, recibos de pago, alertas de seguridad rutinarias.
- Los "confirmo de recibido" / "enterada, gracias" en hilos institucionales de UABC: el hilo vale una línea, no una por respuesta.
- Correos donde Miguel va en copia (CC) y nadie le pide nada.

Se queda lo que **pide una acción, una respuesta o tiene fecha límite**.

## Paso 4 — Redactar el resumen

Formato: markdown, agrupado por urgencia, frases cortas. Cada punto dice **qué hacer**, no solo de qué trata. Omite las secciones que queden vacías.

```markdown
# Hoy — <día> de <mes> de <año>

## 🗓️ Agenda
- 09:00–09:30 — … (con lugar o liga de Meet si la hay)
- Papá: turnos de … a las …

## ⚠️ Vencido / urgente
- …

## 📌 Para hoy
- …

## ✉️ Correos que piden respuesta
- **[Trabajo]** Remitente — asunto → qué se espera de ti
- **[Personal]** …

## 🧠 Pendientes de memoria
- …

## 👀 Vale la pena mirar (sin prisa)
- …
```

Cierra con una línea de contexto: cuántas tareas vencidas hay, o si el día está tranquilo. Si una fuente falla (himalaya sin conexión, MCP sin autenticar), **dilo explícitamente** en el resumen en lugar de omitirla en silencio.

## Notas

- El Gmail conectado por MCP es **lozano.miguel@uabc.edu.mx** (trabajo). La cuenta personal de Gmail `el.badbit@gmail.com` **no** está conectada; si aparece algo relevante ahí, Miguel tiene que revisarlo aparte.
- Este skill solo lee. No marca correos como leídos, no completa tareas ni responde nada sin que Miguel lo pida.
