# Utilidades de IA

Colección personal de herramientas para trabajar con Claude y ChatGPT.

## Proyectos

### [`mate-ai-usage-applet/`](mate-ai-usage-applet/)

Applet para el panel de MATE que muestra el uso de Claude y ChatGPT (ventana de
sesión de 5 h y semanal de 7 d), leyendo las credenciales locales de Claude Code
y Codex CLI.

```bash
cd mate-ai-usage-applet
bash install.sh
```

### [`claude-skills/`](claude-skills/)

Skills y scripts de Claude Code: el skill `hoy` (resumen del día a partir de
Calendar, correo, TickTick y memoria de Claude) y dos barras de estado
(`context-bar.sh` y `statusline.py`).

```bash
cd claude-skills
bash instalar-skills.sh
```

### [`codex/`](codex/)

Instalador idempotente para la barra de estado nativa de Codex CLI. Muestra
modelo y esfuerzo, directorio, rama Git, contexto, límites de 5 horas/semanal,
créditos y coste estimado, preservando el resto de `~/.codex/config.toml`.

```bash
cd codex
bash instalar-statusline.sh
```

## Licencia

MIT — ver [LICENSE](LICENSE).
