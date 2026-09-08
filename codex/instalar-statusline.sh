#!/usr/bin/env bash
#
# Configura la barra de estado nativa de Codex CLI sin reemplazar el resto de
# ~/.codex/config.toml.
#
# Uso:
#   bash instalar-statusline.sh
#   bash instalar-statusline.sh --uninstall
#
set -euo pipefail

ACTION="install"
for arg in "$@"; do
    case "$arg" in
        --uninstall) ACTION="uninstall" ;;
        -h|--help)
            sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "ERROR: opcion desconocida '$arg'" >&2; exit 2 ;;
    esac
done

command -v python3 >/dev/null 2>&1 || {
    echo "ERROR: se necesita python3 para editar config.toml de forma segura." >&2
    exit 1
}

CONFIG_DIR="${CODEX_HOME:-$HOME/.codex}"
CONFIG_FILE="$CONFIG_DIR/config.toml"
mkdir -p "$CONFIG_DIR"

STATUS_ITEMS='["model-with-reasoning", "current-dir", "git-branch", "context-used", "five-hour-limit", "weekly-limit", "thread-credits", "estimated-thread-cost"]'

result="$(
    STATUSLINE_ACTION="$ACTION" \
    STATUSLINE_CONFIG="$CONFIG_FILE" \
    STATUSLINE_ITEMS="$STATUS_ITEMS" \
    python3 - <<'PY'
import datetime
import os
import re
import shutil
import tempfile

action = os.environ["STATUSLINE_ACTION"]
path = os.environ["STATUSLINE_CONFIG"]
items = os.environ["STATUSLINE_ITEMS"]

try:
    with open(path, encoding="utf-8") as fh:
        original = fh.read()
except FileNotFoundError:
    original = ""


def table_bounds(text, name):
    """Devuelve (inicio del cuerpo, fin) para una tabla TOML de primer nivel."""
    header = re.compile(r"(?m)^\s*\[" + re.escape(name) + r"\]\s*(?:#.*)?$")
    match = header.search(text)
    if not match:
        return None
    next_table = re.compile(r"(?m)^\s*\[\[?[^\n]+\]\]?\s*(?:#.*)?$").search(
        text, match.end()
    )
    return match.end(), next_table.start() if next_table else len(text)


def assignment_end(text, start, limit):
    """Consume una asignacion, incluidas matrices TOML de varias lineas."""
    pos = text.find("=", start, limit)
    if pos < 0:
        return text.find("\n", start, limit)
    depth = 0
    quote = None
    escaped = False
    comment = False
    saw_array = False
    i = pos + 1
    while i < limit:
        char = text[i]
        if comment:
            if char == "\n":
                comment = False
                if not saw_array or depth == 0:
                    return i + 1
            i += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\" and quote == '"':
                escaped = True
            elif char == quote:
                quote = None
            i += 1
            continue
        if char in "'\"":
            quote = char
        elif char == "#":
            comment = True
        elif char == "[":
            saw_array = True
            depth += 1
        elif char == "]" and depth:
            depth -= 1
        elif char == "\n" and (not saw_array or depth == 0):
            return i + 1
        i += 1
    return limit


def find_status_line(text, bounds):
    if not bounds:
        return None
    start, end = bounds
    match = re.compile(r"(?m)^\s*status_line\s*=").search(text, start, end)
    if not match:
        return None
    return match.start(), assignment_end(text, match.start(), end)


bounds = table_bounds(original, "tui")
assignment = find_status_line(original, bounds)

if action == "install":
    replacement = "status_line = " + items + "\n"
    if assignment:
        updated = original[: assignment[0]] + replacement + original[assignment[1] :]
    elif bounds:
        insert_at = bounds[1]
        prefix = original[:insert_at]
        if prefix and not prefix.endswith("\n"):
            prefix += "\n"
        updated = prefix + replacement + original[insert_at:]
    else:
        updated = original
        if updated and not updated.endswith("\n"):
            updated += "\n"
        if updated and not updated.endswith("\n\n"):
            updated += "\n"
        updated += "[tui]\n" + replacement
else:
    if not assignment:
        updated = original
    else:
        updated = original[: assignment[0]] + original[assignment[1] :]

if updated == original:
    print("unchanged")
    raise SystemExit(0)

if original:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = path + ".bak-" + stamp
    suffix = 1
    while os.path.exists(backup):
        backup = path + ".bak-" + stamp + "-" + str(suffix)
        suffix += 1
    shutil.copy2(path, backup)
else:
    backup = ""

directory = os.path.dirname(path)
fd, temp_path = tempfile.mkstemp(prefix=".config.toml.", dir=directory, text=True)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(updated)
    if original:
        os.chmod(temp_path, os.stat(path).st_mode)
    else:
        os.chmod(temp_path, 0o600)
    os.replace(temp_path, path)
except Exception:
    try:
        os.unlink(temp_path)
    except FileNotFoundError:
        pass
    raise

print("changed\t" + backup)
PY
)"

state="${result%%$'\t'*}"
backup=""
if [[ "$result" == *$'\t'* ]]; then
    backup="${result#*$'\t'}"
fi

if [[ "$ACTION" == "install" ]]; then
    if [[ "$state" == "unchanged" ]]; then
        echo "La barra de Codex ya estaba configurada; sin cambios."
    else
        echo "Barra de Codex configurada en $CONFIG_FILE"
    fi
else
    if [[ "$state" == "unchanged" ]]; then
        echo "No habia una barra de Codex instalada; sin cambios."
    else
        echo "Barra de Codex retirada de $CONFIG_FILE"
    fi
fi

[[ -z "$backup" ]] || echo "Respaldo: $backup"
echo "Abre una sesion nueva de Codex para ver el cambio (o usa /statusline)."
