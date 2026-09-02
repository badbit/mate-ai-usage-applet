#!/usr/bin/env python3
"""Applet de panel MATE con los límites de uso de Claude y ChatGPT.

Dibuja una rejilla de barras de progreso en el panel: para cada servicio, la
ventana corta (5 h) y la larga (7 d), con el mismo dato que muestran
`/usage` en Claude Code y `/status` en Codex CLI.

Los datos se leen de los endpoints oficiales usando las credenciales que ya
tienes en disco:

  Claude   ~/.claude/.credentials.json  -> api.anthropic.com/api/oauth/usage
  ChatGPT  ~/.codex/auth.json           -> chatgpt.com/backend-api/codex/usage

Los tokens nunca salen hacia otro destino: cada uno viaja solo al servicio
que lo emitió.

Modos de uso fuera del panel:

    ai_usage_applet.py --check            # imprime los datos en texto
    ai_usage_applet.py --window           # ventana suelta, sin panel
    ai_usage_applet.py --preview [a.png]  # renderiza el applet a un PNG
                                          # (--light para tema claro,
                                          #  --demo con datos de ejemplo)
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo  # noqa: E402

CONFIG_PATH = os.path.expanduser("~/.config/mate-ai-usage-applet.json")

DEFAULTS = {
    # grid: una columna por servicio, filas 5 h / 7 d (predeterminado)
    # compact: una fila por servicio, solo porcentajes
    # rotate: un servicio a la vez, alternando cada rotate_seconds
    "layout": "grid",
    "providers": ["claude", "chatgpt"],
    "poll_seconds": 300,
    "rotate_seconds": 6,
    "column_width": 150,   # ancho por servicio, en píxeles
    "gap": 10,             # separación entre columnas
    "font": "Sans 8",
}


def load_config():
    cfg = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH) as f:
            user = json.load(f)
        if isinstance(user, dict):
            cfg.update({k: v for k, v in user.items() if k in DEFAULTS})
    except FileNotFoundError:
        pass
    except Exception as e:                                  # config rota
        print(f"[ai-usage-applet] config ignorada: {e}", file=sys.stderr)
    if cfg["layout"] not in ("grid", "compact", "rotate"):
        cfg["layout"] = DEFAULTS["layout"]
    known = [p for p in cfg["providers"] if p in PROVIDERS]
    cfg["providers"] = known or list(DEFAULTS["providers"])
    return cfg


# ---------------------------------------------------------------------------
# Datos

class Window:
    """Una ventana de límite: porcentaje usado y momento del reinicio."""

    __slots__ = ("pct", "resets_at")

    def __init__(self, pct, resets_at=None):
        self.pct = max(0, min(100, int(round(pct or 0))))
        self.resets_at = resets_at          # epoch (float) o None


class Snapshot:
    """Lo que sabemos de un servicio en un instante dado."""

    __slots__ = ("key", "name", "short", "color", "session", "weekly",
                 "plan", "error", "extra")

    def __init__(self, key, name, short, color):
        self.key, self.name, self.short, self.color = key, name, short, color
        self.session = self.weekly = None
        self.plan = None
        self.error = None
        self.extra = []                     # [(etiqueta, Window)] para el tooltip


def _http_json(url, headers, timeout=20):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _iso_to_epoch(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return None


_claude_version = None


def claude_version():
    """Versión del CLI para el User-Agent; el endpoint la exige coherente."""
    global _claude_version
    if _claude_version is None:
        _claude_version = "2.1.0"
        try:
            out = subprocess.check_output(
                ["claude", "--version"], text=True,
                stderr=subprocess.DEVNULL, timeout=10)
            for tok in out.split():
                if tok[:1].isdigit() and "." in tok:
                    _claude_version = tok
                    break
        except Exception:
            pass
    return _claude_version


def fetch_claude(snap):
    with open(os.path.expanduser("~/.claude/.credentials.json")) as f:
        token = json.load(f)["claudeAiOauth"]["accessToken"]
    data = _http_json("https://api.anthropic.com/api/oauth/usage", {
        "Authorization": f"Bearer {token}",
        "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": f"claude-code/{claude_version()}",
        "Content-Type": "application/json",
    })
    five = data.get("five_hour") or {}
    seven = data.get("seven_day") or {}
    snap.session = Window(five.get("utilization"), _iso_to_epoch(five.get("resets_at")))
    snap.weekly = Window(seven.get("utilization"), _iso_to_epoch(seven.get("resets_at")))
    opus = data.get("seven_day_opus") or {}
    if opus.get("utilization") is not None:
        snap.extra.append(("Opus (7 d)",
                           Window(opus.get("utilization"),
                                  _iso_to_epoch(opus.get("resets_at")))))
    snap.plan = data.get("subscription_type") or data.get("plan")


def fetch_chatgpt(snap):
    with open(os.path.expanduser("~/.codex/auth.json")) as f:
        tokens = json.load(f)["tokens"]
    data = _http_json("https://chatgpt.com/backend-api/codex/usage", {
        "Authorization": f"Bearer {tokens['access_token']}",
        "chatgpt-account-id": tokens.get("account_id") or "",
        "User-Agent": "codex-cli",
        "originator": "codex_cli_rs",
        "Content-Type": "application/json",
    })
    limits = data.get("rate_limit") or {}
    primary = limits.get("primary_window") or {}
    secondary = limits.get("secondary_window") or {}
    snap.session = Window(primary.get("used_percent"), primary.get("reset_at"))
    snap.weekly = Window(secondary.get("used_percent"), secondary.get("reset_at"))
    snap.plan = data.get("plan_type")


PROVIDERS = {
    "claude": {
        "name": "Claude",
        "short": "CL",
        "color": (0.851, 0.467, 0.341),     # naranja de Anthropic
        "fetch": fetch_claude,
        "hint": "inicia sesión con «claude»",
    },
    "chatgpt": {
        "name": "ChatGPT",
        "short": "GPT",
        "color": (0.063, 0.639, 0.498),     # verde de OpenAI
        "fetch": fetch_chatgpt,
        "hint": "inicia sesión con «codex login»",
    },
}


def poll(keys):
    """Consulta cada servicio y devuelve su Snapshot (nunca lanza)."""
    snaps = []
    for key in keys:
        spec = PROVIDERS[key]
        snap = Snapshot(key, spec["name"], spec["short"], spec["color"])
        try:
            spec["fetch"](snap)
        except FileNotFoundError:
            snap.error = "sin sesión"
        except KeyError:
            snap.error = "sin sesión"
        except urllib.error.HTTPError as e:
            snap.error = "sesión caducada" if e.code in (401, 403) else f"HTTP {e.code}"
        except urllib.error.URLError:
            snap.error = "sin red"
        except Exception as e:
            snap.error = type(e).__name__
        snaps.append(snap)
    return snaps


# ---------------------------------------------------------------------------
# Formato

def fmt_reset(epoch):
    if not epoch:
        return "?"
    secs = int(epoch - time.time())
    if secs <= 0:
        return "ahora"
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    if d:
        return f"{d} d {h} h"
    return f"{h} h {m} min" if h else f"{m} min"


def tooltip_text(snaps):
    blocks = []
    for snap in snaps:
        head = snap.name + (f" · {snap.plan}" if snap.plan else "")
        if snap.error:
            hint = PROVIDERS[snap.key]["hint"]
            blocks.append(f"{head}\n  error: {snap.error} ({hint})")
            continue
        lines = [head]
        rows = [("Sesión (5 h)", snap.session), ("Semanal (7 d)", snap.weekly)]
        rows += [(label, win) for label, win in snap.extra]
        for label, win in rows:
            if win is None:
                continue
            lines.append(f"  {label}: {win.pct} %  ·  reinicia en {fmt_reset(win.resets_at)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "Sin servicios configurados"


def bar_color(pct):
    if pct >= 90:
        return (0.96, 0.26, 0.21)
    if pct >= 70:
        return (1.00, 0.60, 0.00)
    return (0.30, 0.69, 0.31)


# ---------------------------------------------------------------------------
# Dibujo (cairo puro: no necesita GTK ni pantalla, así se puede previsualizar)

class Renderer:
    def __init__(self, cfg):
        self.cfg = cfg

    def columns(self, snaps, rotate_index):
        if self.cfg["layout"] == "rotate" and snaps:
            return [snaps[rotate_index % len(snaps)]]
        return snaps

    def natural_width(self, snaps, rotate_index=0):
        cols = self.columns(snaps, rotate_index)
        n = max(1, len(cols))
        if self.cfg["layout"] == "compact":
            return 130
        return n * self.cfg["column_width"] + (n - 1) * self.cfg["gap"]

    # -- primitivas ---------------------------------------------------------
    def _layout(self, ctx, text, font):
        layout = PangoCairo.create_layout(ctx)
        layout.set_font_description(font)
        layout.set_text(text, -1)
        return layout

    def _text(self, ctx, font, text, x, cy, rgba, align=0):
        layout = self._layout(ctx, text, font)
        tw, th = layout.get_pixel_size()
        if align == 2:
            x -= tw
        elif align == 1:
            x -= tw / 2
        ctx.move_to(x, cy - th / 2)
        ctx.set_source_rgba(*rgba)
        PangoCairo.show_layout(ctx, layout)
        return tw

    def _width_of(self, ctx, font, text):
        return self._layout(ctx, text, font).get_pixel_size()[0]

    def _rounded(self, ctx, x, y, w, h, r):
        r = min(r, w / 2, h / 2)
        ctx.new_sub_path()
        ctx.arc(x + w - r, y + r, r, -1.5708, 0)
        ctx.arc(x + w - r, y + h - r, r, 0, 1.5708)
        ctx.arc(x + r, y + h - r, r, 1.5708, 3.1416)
        ctx.arc(x + r, y + r, r, 3.1416, 4.7124)
        ctx.close_path()

    # -- composición --------------------------------------------------------
    def draw(self, ctx, w, h, fg, snaps, rotate_index=0):
        """fg es (r, g, b, a) del color de texto del tema."""
        font = Pango.FontDescription(self.cfg["font"])
        if h < 24:
            font = Pango.FontDescription("Sans 7")
        if self.cfg["layout"] == "compact":
            self._draw_compact(ctx, w, h, fg, font, snaps)
            return
        cols = self.columns(snaps, rotate_index)
        if not cols:
            self._text(ctx, font, "sin servicios", 2, h / 2, fg)
            return
        gap = self.cfg["gap"]
        col_w = (w - gap * (len(cols) - 1)) / len(cols)
        for i, snap in enumerate(cols):
            self._draw_column(ctx, gap * i + col_w * i, col_w, h, fg, font, snap)

    def _draw_column(self, ctx, x0, cw, h, fg, font, snap):
        rows = (("5h", snap.session), ("7d", snap.weekly))
        row_h = h / 2
        bar_h = max(5, min(11, row_h - 4))
        label_w = max(self._width_of(ctx, font, f"{snap.short} {n}") for n, _ in rows)
        pct_w = self._width_of(ctx, font, "100%")
        bx = x0 + label_w + 4
        bw = max(8, cw - (label_w + 4) - (pct_w + 4))
        brand = snap.color + (fg[3],)

        if snap.error:                      # una sola línea centrada, sin barras
            cy = h / 2
            short_w = self._text(ctx, font, snap.short, x0, cy, brand)
            self._text(ctx, font, f"⚠ {snap.error}", x0 + short_w + 6, cy,
                       (0.96, 0.26, 0.21, fg[3]))
            return

        for i, (name, win) in enumerate(rows):
            cy = row_h * i + row_h / 2
            self._text(ctx, font, snap.short, x0, cy, brand)
            self._text(ctx, font, name, x0 + label_w, cy, fg, align=2)

            by = cy - bar_h / 2
            self._rounded(ctx, bx, by, bw, bar_h, bar_h / 2)
            ctx.set_source_rgba(fg[0], fg[1], fg[2], 0.18 * fg[3])
            ctx.fill()
            pct = win.pct if win else 0
            if pct > 0:
                fill_w = max(bar_h, bw * pct / 100.0)
                self._rounded(ctx, bx, by, fill_w, bar_h, bar_h / 2)
                ctx.set_source_rgb(*bar_color(pct))
                ctx.fill()
            self._text(ctx, font, f"{pct}%", x0 + cw, cy, fg, align=2)

    def _draw_compact(self, ctx, w, h, fg, font, snaps):
        if not snaps:
            self._text(ctx, font, "sin servicios", 2, h / 2, fg)
            return
        row_h = h / len(snaps)
        short_w = max(self._width_of(ctx, font, s.short) for s in snaps)
        for i, snap in enumerate(snaps):
            cy = row_h * i + row_h / 2
            self._text(ctx, font, snap.short, 0, cy, snap.color + (fg[3],))
            if snap.error:
                self._text(ctx, font, f"⚠ {snap.error}", short_w + 6, cy,
                           (0.96, 0.26, 0.21, fg[3]))
                continue
            s_pct = snap.session.pct if snap.session else 0
            wk_pct = snap.weekly.pct if snap.weekly else 0
            x = w
            x -= self._text(ctx, font, f"{wk_pct}%", x, cy,
                            bar_color(wk_pct) + (fg[3],), align=2)
            x -= self._text(ctx, font, " / ", x, cy, fg, align=2)
            self._text(ctx, font, f"{s_pct}%", x, cy,
                       bar_color(s_pct) + (fg[3],), align=2)


# ---------------------------------------------------------------------------
# Modos auxiliares (sin panel)

def cli_check():
    cfg = load_config()
    snaps = poll(cfg["providers"])
    print(tooltip_text(snaps))
    return 0 if all(s.error is None for s in snaps) else 1


def demo_snapshots(keys):
    """Datos de ejemplo, para capturas y para probar sin credenciales."""
    values = {"claude": (35, 24), "chatgpt": (61, 28)}
    snaps = []
    for key in keys:
        spec = PROVIDERS[key]
        snap = Snapshot(key, spec["name"], spec["short"], spec["color"])
        session, weekly = values.get(key, (42, 17))
        now = time.time()
        snap.session = Window(session, now + 3600)
        snap.weekly = Window(weekly, now + 4 * 86400)
        snaps.append(snap)
    return snaps


def cli_preview(path="preview.png", dark=True, width=None, demo=False):
    cfg = load_config()
    snaps = demo_snapshots(cfg["providers"]) if demo else poll(cfg["providers"])
    renderer = Renderer(cfg)
    h = 27
    w = int(width or renderer.natural_width(snaps))
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
    ctx = cairo.Context(surface)
    bg = (0.16, 0.16, 0.16) if dark else (0.93, 0.93, 0.93)
    fg = (0.90, 0.90, 0.90, 1.0) if dark else (0.12, 0.12, 0.12, 1.0)
    ctx.set_source_rgb(*bg)
    ctx.paint()
    renderer.draw(ctx, w, h, fg, snaps)
    surface.write_to_png(path)
    print(f"{path} ({w}×{h})")
    return 0


# ---------------------------------------------------------------------------
# Applet de panel

def build_widget_class():
    """Define el widget al vuelo: así --check y --preview no necesitan GTK."""
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GLib                # noqa: E402

    class UsageWidget(Gtk.DrawingArea):
        def __init__(self, cfg):
            super().__init__()
            self.cfg = cfg
            self.renderer = Renderer(cfg)
            self.snaps = [
                Snapshot(k, PROVIDERS[k]["name"], PROVIDERS[k]["short"],
                         PROVIDERS[k]["color"])
                for k in cfg["providers"]
            ]
            for snap in self.snaps:
                snap.error = "…"
            self.rotate_index = 0
            self.busy = False
            self.set_size_request(int(self.renderer.natural_width(self.snaps)), -1)
            self.set_has_tooltip(True)
            self.connect("draw", self.on_draw)
            self.connect("query-tooltip", self.on_tooltip)
            self.refresh()
            GLib.timeout_add_seconds(max(30, int(cfg["poll_seconds"])), self._tick)
            if cfg["layout"] == "rotate":
                GLib.timeout_add_seconds(max(2, int(cfg["rotate_seconds"])),
                                         self._rotate)

        # -- datos ----------------------------------------------------------
        def refresh(self):
            """Consulta en segundo plano: el panel nunca se queda congelado."""
            if self.busy:
                return
            self.busy = True
            keys = list(self.cfg["providers"])

            def work():
                snaps = poll(keys)
                GLib.idle_add(self._apply, snaps)

            threading.Thread(target=work, daemon=True).start()

        def _apply(self, snaps):
            self.snaps = snaps
            self.busy = False
            self.queue_draw()
            return False

        def _tick(self):
            self.refresh()
            return True

        def _rotate(self):
            self.rotate_index += 1
            self.queue_draw()
            return True

        # -- presentación ---------------------------------------------------
        def on_draw(self, widget, ctx):
            alloc = widget.get_allocation()
            color = widget.get_style_context().get_color(Gtk.StateFlags.NORMAL)
            fg = (color.red, color.green, color.blue, color.alpha)
            self.renderer.draw(ctx, alloc.width, alloc.height, fg,
                               self.snaps, self.rotate_index)

        def on_tooltip(self, _w, _x, _y, _kbd, tip):
            tip.set_text(tooltip_text(self.snaps))
            return True

        def on_click(self, _w, event):
            if event.button != 1:
                return False
            self.rotate_index += 1      # en modo «rotate», pasa al siguiente
            self.refresh()
            return True

    return UsageWidget, Gtk


def _wrap_in_event_box(Gtk, widget):
    """Un DrawingArea no recibe clics por sí solo."""
    box = Gtk.EventBox()
    box.set_visible_window(False)
    box.add(widget)
    box.connect("button-press-event", widget.on_click)
    return box


def cli_window():
    """Ventana suelta con el applet, para probarlo sin panel."""
    UsageWidget, Gtk = build_widget_class()
    cfg = load_config()
    widget = UsageWidget(cfg)
    win = Gtk.Window(title="Uso de IA")
    win.set_default_size(int(Renderer(cfg).natural_width(widget.snaps)) + 8, 27)
    win.add(_wrap_in_event_box(Gtk, widget))
    win.connect("destroy", Gtk.main_quit)
    win.show_all()
    Gtk.main()
    return 0


def run_applet():
    UsageWidget, Gtk = build_widget_class()
    gi.require_version("MatePanelApplet", "4.0")
    from gi.repository import MatePanelApplet          # noqa: E402

    def applet_fill(applet):
        widget = UsageWidget(load_config())
        applet.add(_wrap_in_event_box(Gtk, widget))
        applet.set_flags(MatePanelApplet.AppletFlags.EXPAND_MINOR)
        applet.show_all()
        return True

    def applet_factory(applet, iid, data):
        return applet_fill(applet)

    MatePanelApplet.Applet.factory_main(
        "AiUsageFactory", True, MatePanelApplet.Applet.__gtype__,
        applet_factory, None)


def main(argv):
    if "--check" in argv:
        return cli_check()
    if "--window" in argv:
        return cli_window()
    if "--preview" in argv:
        rest = [a for a in argv[argv.index("--preview") + 1:]
                if not a.startswith("-")]
        return cli_preview(rest[0] if rest else "preview.png",
                           dark="--light" not in argv,
                           demo="--demo" in argv)
    return run_applet()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]) or 0)
