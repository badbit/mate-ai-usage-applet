# Skills de Claude Code

Skills y scripts personales sincronizados vía Syncthing para instalarlos en laptop, desktop y trabajo.

## Instalar

Desde esta carpeta, en el equipo destino:

```bash
bash instalar-skills.sh                 # skills + scripts + barra de estado
bash instalar-skills.sh hoy             # solo un skill
bash instalar-skills.sh --solo-barra    # solo scripts + barra de estado
bash instalar-skills.sh --barra=python  # elige barra explicitamente
bash instalar-skills.sh --barra=context
bash instalar-skills.sh --barra=no      # no toca settings.json
```

Copia cada `<skill>/SKILL.md` a `~/.claude/skills/<skill>/SKILL.md`. Si ya existe una versión distinta, la respalda como `SKILL.md.bak-<fecha>` antes de sobrescribir. Después hay que **reiniciar Claude Code**.

También copia todo `scripts/*.sh` y `scripts/*.py` a `~/.claude/scripts/` y deja la clave
`statusLine` puesta en `~/.claude/settings.json`, respaldando el archivo antes de tocarlo y
preservando el resto de las claves. Es idempotente.

**Qué barra elige.** Sin `--barra` respeta lo que ya haya en el equipo: si `settings.json`
apunta a una de las dos barras de esta carpeta, la conserva; si no hay ninguna, instala
`context`; y si apunta a algo ajeno, avisa y **no la toca**. Para cambiarla hay que pedirlo
con `--barra=context` o `--barra=python`. Edita el JSON con `jq` si está y con `python3` si
no — así funciona también en equipos sin `jq`.

## Skills incluidos

### `hoy`

Resumen del día: agenda de Google Calendar, correo personal (disroot), correo de trabajo (UABC), tareas de TickTick vencidas y de hoy, y pendientes en la memoria de Claude.

**Requisitos en el equipo destino** — sin esto, el skill se instala pero falla al correr:

1. **himalaya** con la cuenta personal de disroot configurada (`~/.config/himalaya/config.toml`), con contraseña en el llavero del sistema, nunca en `password.raw`:
   - Linux: `secret-tool store --label='himalaya' service himalaya account badbit@disroot.org`, y en el TOML `password.cmd = "secret-tool lookup service himalaya account badbit@disroot.org"`.
   - macOS: `security add-generic-password -a badbit@disroot.org -s himalaya -w '<password>' -U`, y en el TOML `password.cmd = "security find-generic-password -a badbit@disroot.org -s himalaya -w"`.

   El skill ya no asume un nombre de cuenta fijo ni una versión concreta del CLI de himalaya: los detecta en tiempo de ejecución (ver `hoy/SKILL.md`, pasos 0 y a).
2. **TickTick accesible por MCP**, ya sea como servidor de usuario (`claude mcp add --transport http --scope user ticktick https://mcp.ticktick.com` + autenticar con `/mcp`) o como conector de cuenta de claude.ai — el skill busca las herramientas por palabra clave, no por nombre exacto, así que sirve cualquiera de las dos formas.
3. **Conectores de Gmail y Google Calendar** de claude.ai activos, con la cuenta `lozano.miguel@uabc.edu.mx`.

**Ojo con la ruta de memoria:** el skill lee `~/.claude/projects/<cwd-con-guiones>/memory/`, que depende del equipo y de desde dónde se invoque Claude Code (p. ej. `-home-badbit` en Linux invocando desde el home, `-Users-miguellozano` en el iMac). El propio skill dice cómo verificarla con `ls ~/.claude/projects/`; no hace falta editar nada a mano salvo que la ruta real no sea obvia.

**Verificado compatible con macOS** (2026-09-07): probado en un iMac sin `jq` y sin GNU date nativo (solo `gdate` de Homebrew coreutils) — por eso el skill calcula fechas con `python3` en vez de `date -d`, y detecta cuenta/CLI de himalaya y nombre de herramienta de TickTick en vez de asumirlos.

## Barras de estado

Hay dos, y se elige una por equipo con `--barra`.

### `context` — `scripts/context-bar.sh`

Barra de dos líneas:

```
Opus 5 | 📁badbit | 🔀main (3 files uncommitted, synced 12m ago) | ██░░░░░░░░ 18% of 200k tokens
💬 último mensaje del usuario…
```

Muestra modelo, carpeta de trabajo, rama de git con archivos sin commitear y estado
respecto a `origin`, y el porcentaje de ventana de contexto usada, que calcula leyendo el
transcript de la sesión.

> **Nota (1 de septiembre de 2026).** El script lee el transcript porque en su momento
> `total_input_tokens` no incluía el prompt de sistema ni las herramientas
> ([issue 13652](https://github.com/anthropics/claude-code/issues/13652)). **Eso ya no es
> cierto:** en Claude Code 2.1.258 el CLI calcula ese campo como
> `input_tokens + cache_creation + cache_read` —la misma suma— y entrega además
> `context_window.used_percentage` ya resuelto. Verificado con un payload real:
> `55 480 = 2 + 1 631 + 53 847`.

**Origen:** copiado sin modificar de `scripts/context-bar.sh` del repo
[ykdojo/claude-code-tips](https://github.com/ykdojo/claude-code-tips) (clon local en
`~/.bin/claude-code-tips`). Para traer mejoras del upstream: `git -C ~/.bin/claude-code-tips pull`
y volver a copiar el script a esta carpeta.

**Requisitos:** `jq` (obligatorio), `git` (opcional, para la rama) y Claude Code 2.0.65+.

**Color:** editar `COLOR=` al inicio del script (gray, orange, blue, teal, green, lavender,
rose, gold, slate, cyan). Previsualizar con `bash ~/.claude/scripts/color-preview.sh`.
Aquí está en `blue`. El color vive dentro del script, así que se sincroniza a todos los
equipos: si quieres uno distinto por máquina, hay que editarlo después de instalar.

### `python` — `scripts/statusline.py`

Barra de una línea, en el formato del `PS1` de bash:

```
badbit@desktop:/ruta/de/trabajo | Opus 5 (high) | ctx 55k/1.0M (6%) | [▊░░░░] 15% 5h · [▍░░░░] 8% 7d
```

Muestra `user@host`, carpeta (abreviada con `~` si cuelga del home), modelo, nivel de esfuerzo,
tokens de contexto ocupados sobre el total, y los límites de uso de 5 horas y 7 días como barras
de progreso. **No** muestra rama de git ni el último mensaje del usuario: para eso está `context`.

- **Color del modelo** por familia, leyendo `model.id`: opus magenta, sonnet cian, haiku verde,
  fable amarillo. Un modelo que no reconozca sale sin color.
- **Esfuerzo como semáforo:** `low` verde, `medium` amarillo, `high` rojo, `xhigh` rojo intenso,
  `max` magenta. Un nivel desconocido va atenuado.
- **Barras y porcentaje de contexto** por umbral: <50 % verde, <80 % amarillo, ≥80 % rojo.

**Requisitos:** sólo Python 3 — **no necesita `jq`**, que es la razón por la que existe (en
`desktop` no está instalado y `context-bar.sh` fallaba en silencio).

Todo el cuerpo va en `try/except` con salida de respaldo `user@host:dir` y `exit 0` siempre:
un script de `statusLine` corre en cada repintado y una excepción deja la línea en blanco.

**Color:** editar las tablas `MODEL_COLORS` y `EFFORT_COLORS` al inicio del script. Igual que con
`context-bar.sh`, el color viaja dentro del archivo y se sincroniza a todos los equipos.

**Ancho:** con rutas largas la línea pasa de 130 columnas y puede partirse en terminales angostas.

## Flujo de edición

La copia autoritativa es la de esta carpeta. Al modificar un skill, editar aquí y volver a correr `instalar-skills.sh` en cada equipo — no al revés, porque `~/.claude/skills/` no está sincronizado.
