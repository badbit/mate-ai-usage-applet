# Barra de estado para Codex CLI

Configura el pie nativo de Codex con información equivalente a la barra de
Claude Code de este repositorio:

```text
modelo (esfuerzo) | directorio | rama | contexto | límite 5 h | semanal | créditos | coste
```

Codex no ejecuta un comando externo para dibujar la barra. En su lugar acepta
una lista ordenada de campos nativos mediante `tui.status_line` en
`~/.codex/config.toml`. Esto permite mostrar los límites reales de la cuenta sin
consultar el endpoint por separado ni entregar las credenciales a otro proceso.

## Instalación

```bash
cd codex
bash instalar-statusline.sh
```

El instalador:

- conserva todas las demás opciones y comentarios de `config.toml`;
- reemplaza solamente `tui.status_line` si ya existe;
- guarda `config.toml.bak-<fecha>` antes de cualquier cambio;
- es idempotente: ejecutarlo de nuevo con la misma configuración no modifica nada.

Abre una sesión nueva de Codex para aplicar el cambio. También puedes ejecutar
`/statusline` dentro del TUI para modificar los campos interactivamente.

## Campos instalados

| Identificador | Información |
|---|---|
| `model-with-reasoning` | Modelo y nivel de razonamiento. |
| `current-dir` | Directorio de trabajo. |
| `git-branch` | Rama Git actual. |
| `context-used` | Porcentaje de contexto consumido. |
| `five-hour-limit` | Ventana de uso de cinco horas. |
| `weekly-limit` | Ventana semanal. |
| `thread-credits` | Créditos consumidos por el hilo, cuando aplican. |
| `estimated-thread-cost` | Coste estimado del hilo, cuando está disponible. |

Codex adapta la barra al ancho de la terminal. Algunos campos, especialmente
créditos y coste, pueden quedar vacíos según el tipo de inicio de sesión y plan.

## Desinstalación

```bash
bash instalar-statusline.sh --uninstall
```

Esto elimina solamente la clave `status_line`; no borra la tabla `[tui]` ni
ninguna otra configuración.
