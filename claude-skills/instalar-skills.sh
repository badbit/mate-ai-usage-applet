#!/usr/bin/env bash
#
# instalar-skills.sh
# Instala los skills de Claude Code que viven en esta carpeta de Syncthing
# hacia ~/.claude/skills/ del equipo donde se ejecute.
#
# Instala tambien los scripts de scripts/ hacia ~/.claude/scripts/ y deja
# configurada la barra de estado (statusLine) en ~/.claude/settings.json.
#
# Hay dos barras disponibles (ver README.md):
#   context  ->  scripts/context-bar.sh   (dos lineas, rama git, requiere jq)
#   python   ->  scripts/statusline.py    (una linea, colores, sin dependencias)
#
# Uso:
#   bash instalar-skills.sh                 # skills + scripts + barra
#   bash instalar-skills.sh hoy             # instala solo el skill "hoy"
#   bash instalar-skills.sh --solo-barra    # solo scripts + barra
#   bash instalar-skills.sh --barra=python  # elige barra explicitamente
#   bash instalar-skills.sh --barra=context
#   bash instalar-skills.sh --barra=no      # no toca settings.json
#
# Sin --barra, respeta la barra que ya este puesta en este equipo: si
# settings.json apunta a una de las dos conocidas la conserva, si no hay
# ninguna instala 'context', y si apunta a algo ajeno no lo toca.
#
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="$HOME/.claude/skills"

echo "==> Origen:  $DIR"
echo "==> Destino: $DEST"

SOLO_BARRA=0
BARRA=""
ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --solo-barra) SOLO_BARRA=1 ;;
        --barra=*)    BARRA="${1#--barra=}" ;;
        --barra)      shift; BARRA="${1:-}" ;;
        -*)           echo "ERROR: opcion desconocida '$1'" >&2; exit 1 ;;
        *)            ARGS+=("$1") ;;
    esac
    shift
done

case "$BARRA" in
    ""|context|python|no) ;;
    *) echo "ERROR: --barra debe ser 'context', 'python' o 'no' (dado: '$BARRA')" >&2; exit 1 ;;
esac

if [[ $SOLO_BARRA -eq 1 ]]; then
    SKILLS=()
elif [[ ${#ARGS[@]} -gt 0 ]]; then
    SKILLS=("${ARGS[@]}")
else
    SKILLS=()
    for d in "$DIR"/*/; do
        [[ -f "$d/SKILL.md" ]] && SKILLS+=("$(basename "$d")")
    done
fi

if [[ ${#SKILLS[@]} -eq 0 && $SOLO_BARRA -eq 0 ]]; then
    echo "ERROR: no encontre ningun skill (carpeta con SKILL.md) en $DIR" >&2
    exit 1
fi

mkdir -p "$DEST"

for s in ${SKILLS[@]+"${SKILLS[@]}"}; do
    src="$DIR/$s"
    if [[ ! -f "$src/SKILL.md" ]]; then
        echo "   OMITIDO: '$s' no tiene SKILL.md" >&2
        continue
    fi
    if [[ -f "$DEST/$s/SKILL.md" ]] && ! diff -q "$src/SKILL.md" "$DEST/$s/SKILL.md" >/dev/null; then
        ts="$(date +%Y%m%d-%H%M%S)"
        cp "$DEST/$s/SKILL.md" "$DEST/$s/SKILL.md.bak-$ts"
        echo "   Habia una version distinta instalada; respaldada como SKILL.md.bak-$ts"
    fi
    mkdir -p "$DEST/$s"
    cp -v "$src/SKILL.md" "$DEST/$s/SKILL.md"
done

# --- Scripts y barra de estado -------------------------------------------
# context-bar.sh: modelo | carpeta | rama git y estado | % de contexto, y en
#   una segunda linea el ultimo mensaje del usuario. Requiere jq.
#   Origen: https://github.com/ykdojo/claude-code-tips (scripts/context-bar.sh)
# statusline.py: user@host:dir | modelo (esfuerzo) | ctx tokens (%) | barras
#   de los limites 5h/7d. Solo Python 3, sin dependencias externas.

SCRIPTS_SRC="$DIR/scripts"
SCRIPTS_DEST="$HOME/.claude/scripts"
SETTINGS="$HOME/.claude/settings.json"

CMD_CONTEXT="~/.claude/scripts/context-bar.sh"
CMD_PYTHON="~/.claude/scripts/statusline.py"

# Escribe .statusLine.command en settings.json preservando el resto del
# archivo. Usa jq si esta, si no python3 (que ademas es lo que necesita la
# barra 'python', asi que siempre hay al menos una de las dos vias).
poner_barra() {
    local cmd="$1"
    if command -v jq >/dev/null 2>&1; then
        local tmp; tmp="$(mktemp)"
        jq --arg c "$cmd" '.statusLine = {"type":"command","command":$c}' \
            "$SETTINGS" > "$tmp" && mv "$tmp" "$SETTINGS"
    elif command -v python3 >/dev/null 2>&1; then
        SL_FILE="$SETTINGS" SL_CMD="$cmd" python3 - <<'PY'
import io, json, os
path, cmd = os.environ["SL_FILE"], os.environ["SL_CMD"]
with io.open(path, encoding="utf-8") as fh:
    data = json.load(fh)
data["statusLine"] = {"type": "command", "command": cmd}
with io.open(path, "w", encoding="utf-8") as fh:
    json.dump(data, fh, ensure_ascii=False, indent=2)
    fh.write("\n")
PY
    else
        return 1
    fi
}

if [[ -d "$SCRIPTS_SRC" ]]; then
    echo
    echo "==> Scripts: $SCRIPTS_SRC -> $SCRIPTS_DEST"
    mkdir -p "$SCRIPTS_DEST"
    for f in "$SCRIPTS_SRC"/*.sh "$SCRIPTS_SRC"/*.py; do
        [[ -e "$f" ]] || continue
        cp -v "$f" "$SCRIPTS_DEST/"
        chmod +x "$SCRIPTS_DEST/$(basename "$f")"
    done

    # Que barra queda puesta
    actual=""
    if [[ -f "$SETTINGS" ]] && command -v python3 >/dev/null 2>&1; then
        actual="$(SL_FILE="$SETTINGS" python3 -c 'import io,json,os
try:
    with io.open(os.environ["SL_FILE"], encoding="utf-8") as fh:
        print(json.load(fh).get("statusLine", {}).get("command", ""))
except Exception:
    print("")' 2>/dev/null || true)"
    elif [[ -f "$SETTINGS" ]] && command -v jq >/dev/null 2>&1; then
        actual="$(jq -r '.statusLine.command // empty' "$SETTINGS")"
    fi

    elegida="$BARRA"
    if [[ -z "$elegida" ]]; then
        case "$actual" in
            "$CMD_CONTEXT") elegida="context" ;;
            "$CMD_PYTHON")  elegida="python" ;;
            "")             elegida="context" ;;
            *)              elegida="no"
                            echo "   settings.json apunta a una barra ajena a este instalador:"
                            echo "     $actual"
                            echo "   No la toco. Para cambiarla: --barra=context o --barra=python"
                            ;;
        esac
    fi

    if [[ "$elegida" == "context" ]] && ! command -v jq >/dev/null 2>&1; then
        echo "   OJO: falta 'jq' y la barra 'context' lo necesita para leer el JSON."
        echo "        Instalalo con: sudo apt install jq   (o usa --barra=python)"
    fi

    case "$elegida" in
        context) destino="$CMD_CONTEXT" ;;
        python)  destino="$CMD_PYTHON" ;;
        no)      destino="" ;;
    esac

    if [[ -n "$destino" ]]; then
        if [[ ! -f "$SETTINGS" ]]; then
            printf '{\n  "statusLine": {\n    "type": "command",\n    "command": "%s"\n  }\n}\n' \
                "$destino" > "$SETTINGS"
            echo "   settings.json creado con la barra '$elegida'."
        elif [[ "$actual" == "$destino" ]]; then
            echo "   settings.json ya apuntaba a la barra '$elegida'; sin cambios."
        else
            cp "$SETTINGS" "$SETTINGS.bak-$(date +%Y%m%d-%H%M%S)"
            if poner_barra "$destino"; then
                echo "   settings.json actualizado a la barra '$elegida' (respaldo .bak-* al lado)."
            else
                echo "   Sin jq ni python3 no puedo editar settings.json. Agrega a mano:"
                echo "     \"statusLine\": { \"type\": \"command\", \"command\": \"$destino\" }"
            fi
        fi
    fi
fi

echo
echo "LISTO. Reinicia Claude Code para que los skills y la barra aparezcan."
echo "Verifica con: /hoy   (o escribiendo 'resumen del dia')"
echo "Colores de context-bar.sh: edita COLOR= en ~/.claude/scripts/context-bar.sh"
echo "                           (previsualiza con: bash ~/.claude/scripts/color-preview.sh)"
echo "Colores de statusline.py:  edita las tablas MODEL_COLORS / EFFORT_COLORS del script."
