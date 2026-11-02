# Loops

El harness hace fiable cada ejecución. El loop hace que las ejecuciones continuas no necesiten que un humano dé cada instrucción (L13). Loop engineering no sustituye al harness: se construye encima.

`factory` ofrece dos formas de loop:

| | `factory goal run` | `factory tick` |
|---|---|---|
| Para | una tarea **finita** con línea de meta | **vigilancia** periódica sin fin definido |
| `mode` en goal.md | `finite` | `monitor` |
| Se detiene | al cumplir los criterios o por un límite | en cada tick (verifica primero; solo invoca agentes si algo falla) |

**Anti-patrón**: programar una tarea finita como tick. El loop repetiría el mismo trabajo cada vez sin acumular progreso. Por eso `tick` rechaza los objetivos `finite`.

## Formato de `goal.md`

Un objetivo es Markdown con **frontmatter YAML**. Los metadatos verificables van arriba y la metodología en lenguaje natural va en el cuerpo, al estilo de `program.md` de autoresearch. La plantilla está en `goals/_template.md`. Ejemplo:

<!-- ejemplo-goal: este bloque se valida en tests/test_goal.py -->
```markdown
---
id: validacion-config
objective: Los errores de factory.toml indican sección, clave y cómo corregirlos
mode: finite
feature: loop-config
acceptance:
  - name: tests-config
    run: python -m pytest -q tests/test_config.py
  - name: lint
    run: python -m ruff check src tests
scope:
  allow: ["src/factory/config.py", "tests/test_config.py"]
  deny: ["pyproject.toml"]
stop:
  max_rounds: 4
  max_budget_usd: 1.5
roles:
  maker: {model: sonnet}
---
Revisa cada `ConfigError` de `src/factory/config.py` y añade un test por mensaje.
```

| Clave | Obligatoria | Significado |
|---|---|---|
| `id` | no (nombre del archivo) | minúsculas, dígitos y guiones |
| `objective` | sí | qué cuenta como terminado, en una frase |
| `mode` | no (`finite`) | `finite` o `monitor` |
| `feature` | no | id de `feature_list.json` que se promueve al completar |
| `acceptance` | sí | lista de `{name, run}`. **Al menos un comando**; si no, se rechaza |
| `scope.allow` | no (`**`) | globs que el maker puede tocar (`**`, `*`, `?`, anclados a la raíz) |
| `scope.deny` | no | globs prohibidos. `feature_list.json` se añade siempre |
| `stop` | no | `max_rounds`, `max_budget_usd`, `no_progress_rounds`, `consecutive_passes`, `round_timeout_min` |
| `roles` | no | overrides por rol: `model`, `permission_mode`, `allowed_tools`, `denied_tools` |
| `knowledge` | no | `queries`: consultas **en inglés** para el cerebro principal; `enabled: false` desactiva la inyección. Ver [Cerebros](cerebros.md#recuperación-e-inyección) |

### Rutas protegidas

Tras cada ronda, si un archivo **que ya existía en la base** y es protegido aparece modificado, borrado o renombrado, la ronda se revierte y se marca `protected_revert`. Crear archivos nuevos en esas rutas sí está permitido; así el maker puede añadir tests pero no debilitar los existentes.

- **Siempre protegidos:** `feature_list.json`, `factory.toml`, `prompts/**`, `.claude/agents/**`, `.claude/skills/**`, `.claude/commands/**`, `.claude/hooks/**` y `.claude/settings.json` (la configuración de Claude Code, como las definiciones del equipo), el script de `verify_command` y los scripts relativos de `acceptance` (por ejemplo `./scripts/check.sh` o `bash tools/x.sh`). Nadie puede liberarlos: una rama nunca cambia las reglas con las que se la juzga.
- **Configurables:** `[loop] protected_paths` en `factory.toml` (en este repo, `tests/**`) y `scope.protected` en `goal.md`.
- **Liberación explícita:** `scope.allow_modify` en un objetivo que de verdad debe cambiar un archivo protegido no crítico, por ejemplo un test cuyo comportamiento cambia. `goal validate` y `goal run --dry-run` muestran la protección efectiva.

Lo que omitas en `stop` toma el valor de `[loop]` en `factory.toml`. Todos los límites son finitos. `factory goal validate goals/x.md` muestra los límites efectivos y marca cuáles vienen por defecto.

Los criterios los ejecuta **el orquestador** en el worktree de la ejecución. Lo que diga el agente sobre su trabajo nunca basta para declarar éxito.

## Roles y configuración (`factory.toml`)

```toml
[roles.maker]
model = "sonnet"
prompt = "prompts/maker.md"
permission_mode = "acceptEdits"

[roles.checker]
model = "opus"
prompt = "prompts/checker.md"
permission_mode = "dontAsk"
```

- Por defecto se usan modelos distintos en cada rol: el maker itera rápido y el checker juzga con más capacidad.
- El `prompt` de cada rol se añade al system prompt (`--append-system-prompt`). El maker recibe el objetivo, un resumen acotado del estado y la retroalimentación. El checker recibe criterios, diff acumulado y resultados de verificación.
- Los permisos detallados de cada rol están en [roles.md](roles.md#permisos-por-rol-en-los-loops).
- `permission_mode = "bypassPermissions"` se rechaza al cargar la configuración y al validar un objetivo.

Valores por defecto de `[loop]`: `max_rounds = 8`, `max_budget_usd = 5`, `no_progress_rounds = 3`, `consecutive_passes = 1`, `round_timeout_min = 20`, `agent_error_rounds = 2` y `summary_max_chars = 4000`. Los worktrees se crean fuera del repo (`../<repo>.factory-worktrees/`).

## Backends de agentes

`[agent] backend` elige quién ejecuta a los agentes de `goal run`, `goal rework`, `tick` e `intake`:

- `claude-code` (por defecto): `claude -p` en modo headless, como hasta ahora.
- `strands`: la librería Python [`strands-harness`](https://pypi.org/project/strands-harness/), equivalente de `@strands-agents/harness`, ejecutada dentro del proceso.

```toml
[agent]
backend = "strands"

[agent.strands]
provider = "anthropic"             # prefijo de los modelos sin proveedor

[agent.strands.models]             # alias de los roles -> id de Strands
sonnet = "anthropic/claude-sonnet-5-5"

[agent.strands.prices."anthropic/claude-sonnet-5-5"]   # USD por millón de tokens
input = 2.0
output = 10.0
cache_read = 0.2                   # opcional; si falta, igual que input
cache_write = 2.5                  # opcional; si falta, 1,25 × input
```

- **Instalación:** `.venv/bin/pip install -e '.[strands]'`. Sin el extra, cada invocación falla como error de agente con ese mismo comando en el mensaje, y el loop aplica su regla de fallos consecutivos.
- **Credenciales:** son las del proveedor, en sus variables estándar. Por ejemplo, `ANTHROPIC_API_KEY` para `anthropic/…` o las de AWS para `bedrock/…`.
- **Coste:** Strands solo informa de tokens, así que el coste se calcula con la tabla de precios. Si una invocación se corta por tiempo, el turno en curso se carga como estimación (su contexto y 4.096 tokens de salida, con el presupuesto de la llamada como tope), porque sus tokens no llegan a registrarse. Hay precios por defecto para Opus, Sonnet y Haiku 5.5 en la API de Anthropic. Un modelo sin precio hace fallar la invocación, para no desactivar en silencio el presupuesto ni los cortacircuitos.
- **Garantías:**
  - Cada invocación es un agente nuevo, sin sesión, memoria, skills ni subagentes.
  - Las herramientas de archivos (`read`, `glob`, `grep`, `edit` y `write`) solo actúan dentro del worktree. Los cerebros son de solo lectura y `.git` no se puede escribir.
  - Una herramienta sin equivalente hace fallar la invocación.
  - El shell solo admite los prefijos `Bash(...)` permitidos al rol. Un comando con `; & | < > ` + "`" + ` $` o saltos de línea se rechaza aunque vaya entre comillas, así que un criterio de aceptación con esos caracteres no lo puede ejecutar el maker (lo ejecuta el orquestador igualmente).
  - Al agotarse el tiempo de la invocación o con Ctrl-C, se mata el comando en curso. Las búsquedas de `grep` y `glob` corren en un proceso hijo con 30 s como máximo, y un patrón demasiado costoso devuelve un error al agente. Con `SIGTERM` o `SIGHUP` esos límites no se aplican: `factory` muere y el comando o la búsqueda en curso quedan huérfanos hasta que terminen.
  - Los comandos no reciben las variables de credenciales de los proveedores: `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS` y todas las `AWS_*`. Otras variables sí pasan, y un comando sigue pudiendo leer archivos como `~/.aws/credentials`.
- **Límites:** los comandos permitidos pueden leer o escribir fuera del worktree con sus propios argumentos, igual que con Claude Code: por ejemplo, `git diff --output=/ruta` o `python -m pytest`, que ejecuta código del repo. Concede prefijos estrechos.
- **Volver atrás:** borra la línea `backend` o pon `backend = "claude-code"`.

## Ejecutar un objetivo: `factory goal run`

```bash
.venv/bin/factory goal validate goals/_template.md          # valida y muestra límites efectivos
.venv/bin/factory goal run goals/_template.md --dry-run     # plan completo, sin agentes ni ramas (0 USD)
.venv/bin/factory goal run goals/<id>.md                    # ejecución real (cuesta dinero)
```

Requisitos de una ejecución real: el CLI `claude` en el `PATH` y **al menos un commit en `main`**. El worktree de cada ejecución parte de ese commit.

Qué pasa en cada ronda:

1. El **maker** trabaja en una sesión nueva dentro del worktree `../<repo>.factory-worktrees/<run-id>`, en la rama `factory/<run-id>`.
2. Si toca rutas fuera de `scope`, la ronda se **revierte**.
3. El orquestador hace un commit de instantánea y ejecuta los criterios por su cuenta.
4. El **checker** revisa en solo lectura el diff **acumulado** y los resultados de la verificación.
5. Una ronda se aprueba solo con criterios al 100 % y checker en `pass`, o en `pass_with_minor` sin hallazgos `critical` ni `medium`.
6. **Ratchet**: si la ronda empeora la puntuación, la rama vuelve a la mejor ronda.

### Códigos de salida

| Código | Resultado | Significado |
|---|---|---|
| 0 | `completed` | criterios y checker aprobados en `consecutive_passes` rondas seguidas |
| 2 | — | `goal.md` o configuración inválidos, o repo sin commits |
| 3 | `stalled` | la misma firma de fallo durante `no_progress_rounds` rondas |
| 4 | `max_rounds` | se agotaron las rondas |
| 5 | `budget_exhausted` | se alcanzó `max_budget_usd`; no se inicia ninguna ronda más |
| 6 | `blocked` | el maker pidió una decisión humana (`status: needs_human`); la pregunta va a la bandeja |
| 7 | `agent_error` | `agent_error_rounds` rondas seguidas con error del CLI (no instalado, timeout, salida ilegible) |
| 130 | `interrupted` | Ctrl+C: el estado queda legible y marcado como interrumpido |

### Revisar, retrabajar e integrar

Cómo leer el resultado, continuar una ejecución atascada con `factory goal rework` e integrarla con `factory land`: ver [revision.md](revision.md).

## Peticiones: `factory intake`

Triaje de peticiones en lenguaje natural (aceptar con borrador, pedir información o rechazar) y promoción explícita de borradores: ver [intake.md](intake.md).

## Vigilancia: `factory tick`

Objetivos `mode: monitor`: verifican sin coste y solo lanzan un loop acotado si algo falla. Bloqueo, guardas, cortacircuitos y programación: ver [vigilancia.md](vigilancia.md).

## Anti-patrones (L13)

- **Usar un loop por tiempo para una tarea finita**: repite el mismo trabajo sin acumular progreso. Usa `goal run`.
- **Que el maker sea también el checker**: la autoevaluación no es fiable. Aquí son sesiones, permisos y modelos distintos.
- **Saltarse la verificación** porque "se ve bien": solo cuentan los comandos de `acceptance`.
- **Rendición cognitiva**: dejar de revisar porque "está automatizado". Vigila `factory status`.
- **Ignorar la explosión de tokens**: cada ronda es una sesión nueva con un resumen acotado; si el aviso aparece, simplifica el objetivo.
- **Loops sin estado externo**: cada ronda empezaría de cero. Todo queda en `.factory/`.
- **Goodhart**: el loop optimiza los comandos, no la intención. Protege los tests existentes con `scope.deny` cuando proceda y revisa el diff.

## Seguridad en ejecuciones desatendidas

Las listas de herramientas de Claude Code funcionan por **prefijo** y no son un sandbox. Las defensas de factory son:

- un worktree fuera del repo;
- reversión de lo que queda fuera del alcance;
- un checker de solo lectura con guarda de árbol;
- comandos de publicación denegados;
- nunca `bypassPermissions`;
- presupuesto por invocación y por ejecución;
- cerebros de conocimiento en solo lectura (`--add-dir` con denegaciones de `Edit`/`Write` obligatorias y una huella que avisa si cambian).

Reducen el riesgo, pero no aíslan el sistema. Para ejecuciones largas o desatendidas, usa un **contenedor o una VM** sin credenciales de publicación, con el repo montado y sin acceso a secretos.

## Estado y observabilidad

Dónde queda la memoria de cada ejecución, la bandeja de revisión y los indicadores de costes silenciosos: ver [observabilidad.md](observabilidad.md).

---
Adaptado de walkinglabs/learn-harness-engineering (MIT), lección 13 y proyecto 07.
