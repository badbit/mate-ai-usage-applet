#!/usr/bin/env bash
#
# Instalador del applet «Uso de IA» para el panel de MATE.
# Muestra cuatro barras (sesión 5 h y semanal 7 d, para Claude y ChatGPT)
# con los mismos datos que /usage en Claude Code y /status en Codex CLI.
#
#   bash install.sh              # instalar o actualizar
#   bash install.sh --link       # instalar enlazando al repo (para desarrollar)
#   bash install.sh --no-migrate # no tocar la configuración del panel (dconf)
#   bash install.sh --uninstall  # desinstalar
#
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$REPO_DIR/src/ai_usage_applet.py"

BIN="$HOME/.local/bin/mate-ai-usage-applet.py"
SVC_DIR="$HOME/.local/share/dbus-1/services"
SVC="$SVC_DIR/org.mate.panel.applet.AiUsageFactory.service"
DESC_NAME="org.badbit.AiUsage.mate-panel-applet"
DESC_SYS="/usr/share/mate-panel/applets/$DESC_NAME"
DESC_USER="$HOME/.local/share/mate-panel/applets/$DESC_NAME"
IID="AiUsageFactory::AiUsageApplet"

# Rastros del predecesor (claude-usage-applet), que usaba otros identificadores.
OLD_BIN="$HOME/.local/bin/claude-usage-applet.py"
OLD_SVC="$SVC_DIR/org.mate.panel.applet.ClaudeUsageFactory.service"
OLD_DESC_NAME="org.badbit.ClaudeUsage.mate-panel-applet"
OLD_DESC_SYS="/usr/share/mate-panel/applets/$OLD_DESC_NAME"
OLD_DESC_USER="$HOME/.local/share/mate-panel/applets/$OLD_DESC_NAME"
OLD_IID="ClaudeUsageFactory::ClaudeUsageApplet"

LINK=0
MIGRATE=1
for arg in "$@"; do
    case "$arg" in
        --link)       LINK=1 ;;
        --no-migrate) MIGRATE=0 ;;
        --uninstall)  UNINSTALL=1 ;;
        *) echo "Opción desconocida: $arg" >&2; exit 2 ;;
    esac
done

# ---------------------------------------------------------------------------
# Panel (dconf): sustituye un applet por otro conservando panel y posición.
#   $1 = IID a buscar   $2 = IID nuevo (vacío = solo quitar)
panel_swap() {
    command -v dconf >/dev/null || return 0
    python3 - "$1" "${2:-}" <<'PY'
import ast, subprocess, sys, os, time

old_iid, new_iid = sys.argv[1], sys.argv[2]
OBJ = "/org/mate/panel/objects/"
LIST = "/org/mate/panel/general/object-id-list"

def dconf(*args):
    return subprocess.run(["dconf", *args], capture_output=True, text=True).stdout.strip()

def read(path):
    out = dconf("read", path)
    if not out:
        return None
    if out in ("true", "false"):            # GVariant booleano
        return out == "true"
    try:
        return ast.literal_eval(out)
    except (ValueError, SyntaxError):
        return out

ids = read(LIST) or []
victims = []
for entry in dconf("list", OBJ).splitlines():
    name = entry.rstrip("/")
    if not name:
        continue
    if read(f"{OBJ}{name}/applet-iid") == old_iid:
        victims.append(name)

if not victims:
    sys.exit(0)

backup_dir = os.path.expanduser("~/.cache/mate-ai-usage-applet")
os.makedirs(backup_dir, exist_ok=True)
backup = os.path.join(backup_dir, time.strftime("panel-%Y%m%d-%H%M%S.dconf"))
with open(backup, "w") as f:
    f.write(dconf("dump", "/org/mate/panel/"))
print(f"  ✓ respaldo del panel en {backup}")

for name in victims:
    keys = {k: read(f"{OBJ}{name}/{k}")
            for k in ("toplevel-id", "position", "relative-to-edge",
                      "panel-right-stick", "locked")}
    subprocess.run(["dconf", "reset", "-f", f"{OBJ}{name}/"], check=False)
    ids = [i for i in ids if i != name]
    if not new_iid:
        continue
    new_name = "ai-usage"
    n = 0
    while new_name in ids:
        n += 1
        new_name = f"ai-usage-{n}"
    subprocess.run(["dconf", "write", f"{OBJ}{new_name}/object-type", "'applet'"])
    subprocess.run(["dconf", "write", f"{OBJ}{new_name}/applet-iid", repr(new_iid)])
    for k, v in keys.items():
        if v is None:
            continue
        value = repr(v) if isinstance(v, str) else ("true" if v is True else
                                                    "false" if v is False else str(v))
        subprocess.run(["dconf", "write", f"{OBJ}{new_name}/{k}", value])
    ids.append(new_name)
    print(f"  ✓ {name} ({old_iid}) → {new_name} ({new_iid})")

subprocess.run(["dconf", "write", LIST, repr(ids)])
PY
}

# ---------------------------------------------------------------------------
uninstall() {
    echo "Desinstalando el applet «Uso de IA»…"
    if [ "$MIGRATE" = 1 ]; then panel_swap "$IID" ""; fi
    rm -f "$BIN" "$SVC" "$DESC_USER"
    if [ -f "$DESC_SYS" ]; then
        echo "Se requiere sudo para quitar el descriptor del sistema:"
        sudo rm -f "$DESC_SYS"
    fi
    command -v mate-panel >/dev/null && (mate-panel --replace >/dev/null 2>&1 &) || true
    echo "Listo."
    exit 0
}
[ "${UNINSTALL:-0}" = 1 ] && uninstall

# ---------------------------------------------------------------------------
echo "Instalando el applet «Uso de IA» para $USER (HOME=$HOME)…"
[ -f "$SRC" ] || { echo "No encuentro $SRC" >&2; exit 1; }

# 1) Dependencias GIR.
if ! python3 - <<'PYCHK' 2>/dev/null
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("MatePanelApplet", "4.0")
gi.require_version("PangoCairo", "1.0")
import cairo
from gi.repository import Gtk, GLib, Pango, PangoCairo, MatePanelApplet  # noqa
PYCHK
then
    echo "FALTAN dependencias. En Debian/Ubuntu/Mint instala:" >&2
    echo "    sudo apt install gir1.2-matepanelapplet-4.0 gir1.2-pango-1.0 \\" >&2
    echo "                     python3-gi python3-gi-cairo" >&2
    exit 1
fi

# 2) El script del applet.
mkdir -p "$(dirname "$BIN")"
if [ "$LINK" = 1 ]; then
    ln -sfn "$SRC" "$BIN"
    echo "  ✓ $BIN → $SRC (enlace)"
else
    install -m 755 "$SRC" "$BIN"
    echo "  ✓ $BIN"
fi

# 3) Servicio D-Bus de sesión, con el HOME real de esta máquina.
mkdir -p "$SVC_DIR"
cat > "$SVC" <<EOF
[D-BUS Service]
Name=org.mate.panel.applet.AiUsageFactory
Exec=$BIN
EOF
echo "  ✓ $SVC"

# 4) Descriptor del applet (copia de usuario, sirve de referencia).
mkdir -p "$(dirname "$DESC_USER")"
cat > "$DESC_USER" <<EOF
[Applet Factory]
Id=AiUsageFactory
InProcess=false
Location=$BIN
Name=AI Usage Factory
Description=Límites de uso de asistentes de IA

[AiUsageApplet]
Name=Uso de IA
Description=Barras de uso de sesión (5 h) y semanal (7 d) de Claude y ChatGPT
Icon=utilities-system-monitor
MateComponentId=OAFIID:MATE_AiUsageApplet;
EOF

# 5) XDG_DATA_DIRS en ~/.profile (idempotente).
if ! grep -q 'mate-panel applets de usuario' "$HOME/.profile" 2>/dev/null &&
   ! grep -q 'claude-usage-applet' "$HOME/.profile" 2>/dev/null; then
    cat >> "$HOME/.profile" <<'EOF'

# mate-panel applets de usuario (mate-ai-usage-applet)
case ":$XDG_DATA_DIRS:" in
    *":$HOME/.local/share:"*) ;;
    *) export XDG_DATA_DIRS="$HOME/.local/share:${XDG_DATA_DIRS:-/usr/local/share:/usr/share}" ;;
esac
EOF
    echo "  ✓ XDG_DATA_DIRS añadido a ~/.profile"
fi

# 6) Descriptor del sistema: ÚNICO paso con sudo. mate-panel 1.26 ignora
#    XDG_DATA_DIRS y solo escanea /usr/share/mate-panel/applets/.
echo "Se requiere sudo para registrar el descriptor en $DESC_SYS"
sudo install -m 644 "$DESC_USER" "$DESC_SYS"
echo "  ✓ $DESC_SYS"

# 7) Retirar el predecesor «Uso de Claude», si sigue instalado.
if [ -e "$OLD_BIN" ] || [ -e "$OLD_SVC" ] || [ -e "$OLD_DESC_SYS" ]; then
    echo "Retirando el applet anterior («Uso de Claude»)…"
    rm -f "$OLD_BIN" "$OLD_SVC" "$OLD_DESC_USER"
    if [ -f "$OLD_DESC_SYS" ]; then sudo rm -f "$OLD_DESC_SYS"; fi
    echo "  ✓ archivos del applet anterior eliminados"
fi
if [ "$MIGRATE" = 1 ]; then panel_swap "$OLD_IID" "$IID"; fi

# 8) Reiniciar el panel para que lea el descriptor nuevo.
if command -v mate-panel >/dev/null; then
    (mate-panel --replace >/dev/null 2>&1 &) || true
    echo "  ✓ panel reiniciado"
fi

cat <<EOF

Listo. Si el applet anterior estaba en el panel, el nuevo ocupa su lugar.
Si no, añádelo: clic derecho en el panel → «Añadir al panel…» → «Uso de IA».

Comprobación rápida sin panel:
    $BIN --check
EOF
