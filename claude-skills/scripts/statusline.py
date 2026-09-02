#!/usr/bin/env python3
"""Claude Code statusLine: user@host:dir | modelo (esfuerzo) | ctx | barras de uso.

Lee el JSON de estado por stdin. Sin dependencias externas (no requiere jq).
Nunca debe fallar: ante cualquier error imprime al menos user@host:dir.
"""
import json
import os
import socket
import sys

RESET = "\033[00m"
GREEN = "01;32"
YELLOW = "01;33"
RED = "01;31"
BRIGHT_RED = "01;91"
MAGENTA = "01;35"
CYAN = "01;36"
BLUE = "01;34"
DIM = "2"
PLAIN = "0"

# Color por familia de modelo, buscado como subcadena de model.id (estable)
# y, si no hay id, de display_name. Un modelo desconocido va sin color.
MODEL_COLORS = (
    ("opus", MAGENTA),
    ("sonnet", CYAN),
    ("haiku", GREEN),
    ("fable", YELLOW),
)

# Semáforo de esfuerzo: verde -> rojo. Nivel desconocido va atenuado.
EFFORT_COLORS = {
    "low": GREEN,
    "medium": YELLOW,
    "high": RED,
    "xhigh": BRIGHT_RED,
    "max": MAGENTA,
}

BAR_WIDTH = 5
BAR_EIGHTHS = " ▏▎▍▌▋▊▉█"
BAR_EMPTY = "░"


def paint(text, code):
    if text == "":
        return ""
    return "\033[%sm%s%s" % (code, text, RESET)


SEP = " " + paint("|", DIM) + " "


def user_host():
    try:
        user = os.environ.get("USER") or os.getlogin()
    except Exception:
        user = "?"
    host = socket.gethostname().split(".")[0]
    chroot = os.environ.get("debian_chroot", "")
    prefix = "(%s)" % chroot if chroot else ""
    return "%s%s" % (prefix, paint("%s@%s" % (user, host), GREEN))


def get(d, *path, default=None):
    for key in path:
        if not isinstance(d, dict):
            return default
        d = d.get(key)
        if d is None:
            return default
    return d


def num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def fmt_tokens(n):
    n = num(n)
    if n is None:
        return None
    n = int(n)
    if n >= 1000000:
        return "%.1fM" % (n / 1000000.0)
    if n >= 1000:
        return "%dk" % (n // 1000)
    return str(n)


def level_color(pct):
    """Umbrales de saturación: tranquilo, atención, alerta."""
    if pct >= 80:
        return RED
    if pct >= 50:
        return YELLOW
    return GREEN


def bar(pct, width=BAR_WIDTH):
    """Barra de progreso con resolución de octavos, coloreada por umbral."""
    pct = max(0.0, min(100.0, pct))
    eighths = int(round(pct / 100.0 * width * 8))
    full, rest = divmod(eighths, 8)
    cells = "█" * full
    if rest and full < width:
        cells += BAR_EIGHTHS[rest]
    filled = len(cells)
    body = paint(cells, level_color(pct)) + paint(BAR_EMPTY * (width - filled), DIM)
    return paint("[", DIM) + body + paint("]", DIM)


def model_color(model):
    key = ("%s %s" % (get(model, "id") or "", get(model, "display_name") or "")).lower()
    for needle, color in MODEL_COLORS:
        if needle in key:
            return color
    return PLAIN


def main():
    parts = []
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}

    cwd = get(data, "workspace", "current_dir") or os.getcwd()
    home = os.path.expanduser("~")
    if cwd == home:
        cwd = "~"
    elif cwd.startswith(home + os.sep):
        cwd = "~" + cwd[len(home):]
    parts.append("%s:%s" % (user_host(), paint(cwd, BLUE)))

    model = get(data, "model", default={})
    name = get(model, "display_name")
    if name:
        chunk = paint(str(name), model_color(model))
        effort = get(data, "effort", "level")
        if effort:
            effort = str(effort)
            chunk += " " + paint("(%s)" % effort, EFFORT_COLORS.get(effort.lower(), DIM))
        if get(data, "fast_mode") is True:
            chunk += " ⚡"
        parts.append(chunk)

    cw = get(data, "context_window", default={})
    used = num(get(cw, "total_input_tokens"))
    size = num(get(cw, "context_window_size"))
    pct = num(get(cw, "used_percentage"))
    if used:
        chunk = paint("ctx", DIM) + " " + (fmt_tokens(used) or "?")
        if size:
            chunk += "/" + (fmt_tokens(size) or "?")
        if pct is not None:
            chunk += " " + paint("(%d%%)" % round(pct), level_color(pct))
        parts.append(chunk)

    gauges = []
    for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
        pct = num(get(data, "rate_limits", key, "used_percentage"))
        if pct is not None:
            gauges.append("%s %d%% %s" % (bar(pct), round(pct), paint(label, DIM)))
    if gauges:
        parts.append((" " + paint("·", DIM) + " ").join(gauges))

    sys.stdout.write(SEP.join(parts))


try:
    main()
except Exception:
    try:
        sys.stdout.write("%s:%s" % (user_host(), paint(os.getcwd(), BLUE)))
    except Exception:
        pass
sys.exit(0)
