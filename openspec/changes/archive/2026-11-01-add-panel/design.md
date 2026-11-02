# Design

## Context

Motivación: ver `proposal.md`. Requisitos: ver `specs/token-usage`, `specs/review-hooks` y `specs/observability-panel`.

**Estado actual (observado en este repo):**
- Los loops registran en `.factory/runs/<run-id>/events.jsonl` un evento `agent` por invocación, con `role`, `model`, `cost_usd`, `input_tokens`, `output_tokens` y `num_turns`. `state.json` guarda las rondas con `criteria`, `score`, `checker_verdict` y `findings` (con `severity`). `.factory/results.tsv` resume las rondas. `.factory/` está en `.gitignore`.
- Claude Code guarda cada sesión en `~/.claude/projects/<slug>/<session>.jsonl`. El slug es la ruta absoluta del cwd con cada carácter no alfanumérico cambiado por `-`. Los subagentes van en `<slug>/<session>/subagents/agent-<id>.jsonl` y, al lado, `agent-<id>.meta.json` con `agentType`, `description` y `toolUseId`.
- En las transcripciones, cada bloque de contenido de una respuesta es una fila con el mismo `message.id` y el mismo `usage`: en 1.952 filas reales no hubo ningún id con `usage` distinto. Sumar por fila cuenta varias veces cada mensaje.
- Los subagentes se lanzan a menudo en segundo plano. El resultado de la herramienta `Agent` es entonces `{"status": "async_launched", "agentId": …}`, así que el veredicto no llega en `PostToolUse`, sino cuando el subagente termina (`SubagentStop`).
- El `checker` responde con `## Veredicto` seguido de `✅ pass`, `❌ fail` o `⚠️ pass_with_minor`, y sus hallazgos con `### N. [critical|medium|minor] Título`. Los jugadores de `add-equipo-ideal` usan el mismo formato, precedido de `## Jugador: <name> (#<dorsal>)`.
- Hay otra sesión con `add-equipo-ideal` en `.claude/worktrees/*`, que edita `cli.py`, `doctor.py`, `protection.py`, `AGENTS.md` y `README.md`. Este cambio no toca `doctor.py` ni `protection.py`, y en `cli.py` solo registra dos subcomandos.

## Goals / Non-Goals

**Goals:**
- Cero dependencias nuevas y cero coste de API: stdlib y archivos que ya existen.
- Solo lectura en el panel. La única escritura del cambio es el registro que añade el hook.
- Tolerancia a formatos internos de Claude Code: un campo ausente degrada una sección, nunca el panel entero.
- Tiempo real "suficiente": el panel refleja un cambio en unos 1–2 s.

**Non-Goals:**
- Una base de datos o un histórico propio: el panel recalcula desde los archivos.
- Autenticación de usuarios: el servidor solo escucha en loopback.
- Integrar `factory status` con el panel o sustituirlo.

## Decisions

### D1. Panel local servido por `factory`, no un Artifact ni un framework web

`http.server.ThreadingHTTPServer` (con `daemon_threads`) en `127.0.0.1`, con una página estática empaquetada en `src/factory/panel/static/index.html` y leída con `importlib.resources`.

- **Alternativa: un Artifact de claude.ai.** Se descarta porque no puede leer `.factory/` ni `~/.claude/projects/` en vivo.
- **Alternativa: Streamlit, Flask o Dash.** Se descartan porque añaden dependencias pesadas a un paquete que solo depende de `pyyaml`.
- **Alternativa: una TUI.** Se descarta porque se pidió un sistema gráfico, y SVG en el navegador da gráficos reales sin librerías.

### D2. Módulos

| Módulo | Responsabilidad |
|---|---|
| `panel/__init__.py` | `PanelError` y la resolución del repo principal (`git rev-parse --git-common-dir`; si no hay git, `find_root`) |
| `panel/tokens.py` | consumo de los loops y de las transcripciones (D3) |
| `panel/hooks.py` | `factory hook`: normaliza el evento y lo añade al registro (D4) |
| `panel/reviews.py` | feed de revisiones: hooks y loops (D5) |
| `panel/tasks.py` | features, `tasks.md`, ejecuciones y bandeja (D6) |
| `panel/snapshot.py` | instantánea `{generated, repo, tokens, reviews, tasks, warnings}` |
| `panel/server.py` | rutas HTTP, cabecera `Host`, SSE y vigilante (D7, D8) |

Cada función de lectura recibe sus rutas (raíz del repo, directorio de proyectos de Claude Code), así que los tests usan directorios temporales y nunca el `~/.claude` real.

### D3. Tokens: descubrimiento, deduplicación y caché incremental

- **Directorio de proyectos:** `--projects-dir`, si no `$CLAUDE_CONFIG_DIR/projects` y, si no, `~/.claude/projects`.
- **Directorios del proyecto:** `slug(root)` y los que empiezan por `slug(root) + "--claude-worktrees-"`. Los de los loops (`<repo>.factory-worktrees/…`) no coinciden con ese prefijo y quedan fuera solos, así que no hace falta una lista de exclusión.
- **Fila útil:** `type == "assistant"`, con `message.usage` y un `message.model` distinto de `<synthetic>`. La clave es `message.id`; si falta, `requestId`; y si falta, `uuid`. Se conserva la última fila de cada clave.
- **Datos extraídos:** del `usage` solo `input_tokens`, `cache_creation_input_tokens`, `cache_read_input_tokens` y `output_tokens`, más `timestamp`, `sessionId` y el agente. Nada de `content`. Los tests lo comprueban con un mensaje que contiene un secreto.
- **Tipo de agente:**
  - `principal` en la transcripción de la sesión;
  - el `agentType` del `meta.json` en la de un subagente;
  - `subagente` si no hay `meta.json`.
- **Día:** el día UTC de la marca de tiempo, como en `results.tsv`.
- **Caché incremental en el servidor:** por archivo se guardan el desplazamiento leído, el tamaño y las filas por clave. Si el archivo crece, se lee solo lo nuevo. Si encoge o cambia de inodo, se relee entero. Las transcripciones solo crecen, así que el coste de cada refresco es proporcional a lo añadido. `--json` hace una lectura completa sin caché.
- **Loops:** los eventos `agent` de cada `events.jsonl`. El USD sale del `cost_usd` registrado y no se estima ningún precio (ver la spec).

**Alternativa descartada:** pedir el consumo a los hooks (`Stop`). Los hooks no traen `usage` y obligarían a reabrir la transcripción en cada turno, en la ruta crítica de la sesión.

### D4. `factory hook`: qué se registra y cómo

- **Entrada:** el JSON del hook por stdin.
- **Eventos atendidos:** `PreToolUse` con `tool_name` `Agent` o `Task` y `SubagentStop`. Cualquier otro evento se ignora sin registrar nada.
- **Línea común:** `ts`, `event`, `session_id` y `cwd`.
- **`PreToolUse`:** `tool_use_id`, `subagent_type`, `description` y `review` (booleano). Nunca el `prompt`.
- **`SubagentStop`:** `agent_id`, `agent_type` (del payload o del `meta.json`), `tool_use_id` (del `meta.json`), `verdict`, `severities` (`{critical, medium, minor, low}`), `excerpt` (≤ 4.000 caracteres) y `review`.
- **Transcripción del subagente:**
  - `agent_transcript_path` si viene en el payload;
  - si no, `<dir de transcript_path>/<session_id>/subagents/agent-<agent_id>.jsonl`.

  La respuesta final es el `message` de la llamada a `SubagentHandback`, si la hay. Si no, la última fila `assistant` que tenga texto y, si la transcripción no acabó, `last_assistant_message` del payload.
- **Veredicto:**
  - se toma la primera palabra `pass_with_minor`, `pass` o `fail` de la línea de la cabecera `Veredicto` o de las siguientes, leyendo de izquierda a derecha (`fail (antes era pass)` es `fail`);
  - si no hay cabecera, en una clave JSON `"verdict"`;
  - si no, `sin_veredicto`.
- **Severidades:** recuento de `[critical]`, `[medium]`, `[minor]` y `[low]` en los títulos y viñetas de hallazgo (una línea que empieza por `##` a `######`, `-`, `*` o `N.`) de la sección `Hallazgos` (hasta la siguiente cabecera de su nivel; todo el texto si no la hay), sin distinguir mayúsculas. Así no se suman los hallazgos anteriores que repasa una segunda revisión.
- **¿Es una revisión?** Si el tipo es `checker`, o si `.claude/agents/<tipo>.md` del checkout de la sesión (si no, del repo principal) declara `tipo: revisor` en su frontmatter. El frontmatter se lee con pyyaml directamente, sin depender del paquete `team` de la otra sesión.
- **Escritura:** `os.open(O_APPEND|O_CREAT|O_WRONLY)`, `fcntl.flock` exclusivo y un solo `os.write` de la línea. Los subagentes terminan en paralelo y así no se mezclan líneas.
- **Salida:** todo va dentro de un `try/except BaseException`, que escribe en stderr y devuelve 0. Nunca se imprime en stdout, porque Claude Code interpreta como JSON de control la salida de algunos hooks.

**Script del hook:** `.claude/hooks/panel-hook.sh` resuelve el repo principal con `git -C "${CLAUDE_PROJECT_DIR:-.}" rev-parse --path-format=absolute --git-common-dir` y ejecuta `<principal>/.venv/bin/python -m factory.panel.hooks` si existe. Es el mismo código que `factory hook`, pero no carga todo el CLI: arranca antes y no depende de que importen módulos ajenos al hook. Siempre termina con `exit 0`. Así los worktrees del equipo, que no tienen `.venv`, también registran. `.claude/settings.json` lo llama con `timeout: 10` y `async: true`, de modo que la herramienta no espera al hook.

**Alternativa descartada:** registrar desde `PostToolUse` de `Agent`. Con agentes en segundo plano llega `async_launched` sin veredicto.

### D5. Feed de revisiones

- **Unión de inicio y fin:**
  - un `SubagentStop` se une a su `PreToolUse` por `tool_use_id`, que sale del `meta.json`;
  - si falta, se une al inicio más reciente sin cerrar de la misma sesión y del mismo tipo;
  - un inicio sin fin queda `en_curso`, con el tiempo transcurrido. Pasadas 2 horas queda `sin_cierre`, sin duración. La prueba con datos reales encontró inicios cuyo fin nunca llegó: el de una sesión cerrada con el revisor trabajando, y cuatro lanzamientos de jugadores que no crearon subagente, porque la sesión aún no conocía esos tipos. Una revisión real dura minutos;
  - un fin sin inicio (hook instalado a mitad de una revisión) aparece igual, sin duración.
- **Revisiones de los loops:** cada ronda con `checker_verdict` en `state.json` aporta una entrada con origen `loop`, `run_id`, ronda, veredicto y severidades de sus `findings`. La marca de tiempo es el `finished` de la ronda.
- **Orden:** de la más reciente a la más antigua, con un límite de 200 entradas. Solo cuentan los eventos con `review: true`. Los demás subagentes no salen en el feed, pero sí en los tokens.

### D6. Estado de implementación

- **Features:** de `feature_list.json`, con la última evidencia de cada comando (código y commit), las ejecuciones con `state.feature == id` y las revisiones cuyo texto menciona el id.
- **Cambios OpenSpec activos:**
  - se leen `openspec/changes/*/tasks.md`, salvo `archive/`;
  - cada `## N. Título` abre un grupo y cada `- [x]` / `- [ ]` cuenta como tarea;
  - el primer `` `id` `` del título que coincida con una feature enlaza el grupo con ella.
- **Ejecuciones:**
  - de `state.json`: estado, ronda actual, `score/criteria_total` y último veredicto;
  - el coste es la suma del `cost_usd` de sus eventos;
  - un proceso cuenta como vivo si `os.kill(pid, 0)` no falla, con `pid > 0`, el mismo criterio que el bloqueo del tick.
- **Bandeja:** número de entradas pendientes, con la API existente de `Inbox`.

### D7. Tiempo real: sondeo de huellas y SSE

- **Vigilante:** un único hilo calcula cada segundo una huella por sección, con el `(mtime_ns, size)` de los archivos vigilados:
  - `tasks`: `feature_list.json`, los `tasks.md`, `state.json` y la bandeja;
  - `reviews`: el registro de hooks y `state.json`;
  - `tokens`: los `events.jsonl` y las transcripciones del proyecto.
- **Avisos:** si cambia alguna sección, envía `event: change` con `{"sections": [...]}` a cada cliente (una cola por cliente) y un comentario `: ping` cada 15 s.
- **Cliente:** el navegador vuelve a pedir `/api/snapshot`, sin recibir datos por el stream. La instantánea es una sola, el stream es trivial y una reconexión de `EventSource` no pierde estado.
- **Alternativa descartada:** FSEvents, inotify o `watchdog`, que son dependencias o código por plataforma. Sondear unos cientos de `stat` por segundo es despreciable.

### D8. Seguridad del servidor

- **Escucha:** solo `127.0.0.1`. No hay opción `--host`, porque exponer el panel está fuera de alcance.
- **Cabecera `Host`:** debe ser `127.0.0.1`, `localhost` o `[::1]` (con o sin puerto). Si no, responde 403, contra el *DNS rebinding*: una web ajena no puede leer el panel a través de un dominio que resuelve a loopback.
- **Métodos:** solo `GET` y `HEAD`; cualquier otro, 405.
- **Cabeceras de respuesta:** ninguna CORS. Además, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` y una CSP `default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'` (CSS y JS en línea en una sola página).
- **XSS:** la página inserta los datos con `textContent` y atributos SVG, nunca con `innerHTML`. Los extractos de las revisiones y las descripciones vienen de agentes y podrían contener HTML.

### D9. Página

Un solo archivo con CSS y JS en línea, sin `fetch` a otros orígenes. Los tokens de color están en `:root`, con variante oscura en `prefers-color-scheme`. Tiene tres pestañas:

- **Tokens:**
  - KPIs: tokens de hoy, total registrado en USD (loops) y proporción de caché;
  - barras apiladas por día (entrada, escritura de caché, lectura de caché y salida);
  - barras horizontales por tipo de agente y por modelo;
  - coste por ejecución de los loops.
- **Revisiones:** feed vivo con un chip de estado (`en_curso`, `pass`, `pass_with_minor`, `fail`, `sin_veredicto` o `sin_cierre`), origen, revisor, duración, severidades y el extracto plegable.
- **Tareas:**
  - tablero de features por estado, con WIP;
  - barras de progreso de cada cambio OpenSpec por grupo;
  - tabla de ejecuciones;
  - al hacer clic en una feature, su detalle: tareas del grupo, verificación, evidencia, ejecuciones y revisiones.

Los gráficos se dibujan como SVG desde JS. Antes de escribirlos se aplica la skill `dataviz` (paleta validada, ejes y leyendas). Un indicador muestra si el stream está conectado.

### D10. CLI

- `factory panel [--port 8765] [--json] [--open] [--projects-dir DIR]`: `--json` imprime la instantánea y sale; sin él, sirve hasta `Ctrl+C` e imprime la URL. `--open` abre el navegador con `webbrowser`.
- `factory hook`: sin argumentos.

Los dos handlers importan `factory.panel` dentro de la función, igual que propone `add-equipo-ideal` para `team`, para que `cli.py` cambie en pocas líneas y el arranque del hook no cargue módulos de más.

## Risks / Trade-offs

- **[Los campos del payload de `SubagentStop` difieren de los supuestos]** → El handler acepta campos ausentes y recurre al `meta.json` y a la ruta derivada de `transcript_path`. Tarea de validación: la propia revisión del `checker` de este cambio, con el hook instalado, deja un evento real sin coste extra. Su forma se compara con los fixtures y, si difiere, se ajustan los fixtures y el código.
- **[El formato interno de las transcripciones cambia]** → El parser ignora las filas que no entiende. Si un archivo existe pero no se puede leer, añade un aviso en `warnings` que lo nombra. Los tests fijan el formato observado. Lo peor que pasa es que la sección de tokens de las sesiones queda vacía.
- **[Transcripciones grandes hacen lento el refresco]** → Caché incremental por desplazamiento (D3). Tarea de medida con los datos reales: tiempo de `factory panel --json` y de un refresco incremental.
- **[El hook añade latencia a cada subagente]** → Solo se registra en el lanzamiento de `Agent`/`Task` y en `SubagentStop`, no en cada herramienta. Tarea de medida: tiempo del hook; si supera ~300 ms, el script llama directamente a `python -m factory.panel.hooks`.
- **[Un maker de un loop reescribe `.claude/settings.json` o el script del hook]** → El script del hook se ejecuta en las sesiones humanas. `add-equipo-ideal` (D7) ya protege `.claude/settings.json` y `.claude/hooks/**` como rutas críticas (`src/factory/protection.py`): la rama de un loop no puede modificarlos y ningún objetivo puede liberarlos.
- **[El extracto de una revisión contiene datos sensibles]** → Se guarda solo en `.factory/` (ignorado por git), con 4.000 caracteres como máximo, y se sirve únicamente en loopback.
- **[Conflictos con `add-equipo-ideal`]** → Los archivos compartidos (`cli.py`, `AGENTS.md`, `feature_list.json`) reciben diffs mínimos. Las prioridades 24–26 son únicas. Se commitea con pathspec explícito y se avisa a la otra sesión antes de integrar.
- **[Sondear cada segundo gasta CPU con el panel abierto]** → Unos cientos de `stat` por segundo. Si hiciera falta, el intervalo es una constante.

## Migration Plan

- **Despliegue:** sin migración. El panel solo lee archivos existentes y el registro de hooks empieza vacío.
- **Vuelta atrás:**
  - quitar las entradas del hook de `.claude/settings.json`, para dejar de registrar;
  - borrar `.factory/hooks/`, para eliminar el histórico;
  - ningún otro componente depende del panel.

## Open Questions

- ¿El `SubagentStop` de esta versión de Claude Code trae `agent_type` y `agent_transcript_path`? La captura real lo dirá. El diseño funciona con o sin ellos.
  - **Respuesta (captura real, 2026-10-30):** sí. `SubagentStop` trae `agent_id`, `agent_transcript_path`, `agent_type`, `background_tasks`, `cwd`, `effort`, `hook_event_name`, `last_assistant_message`, `permission_mode`, `prompt_id`, `scratchpad_dir`, `session_crons`, `session_id`, `stop_hook_active` y `transcript_path`. `PreToolUse` trae `cwd`, `effort`, `hook_event_name`, `permission_mode`, `prompt_id`, `scratchpad_dir`, `session_id`, `tool_input`, `tool_name`, `tool_use_id` y `transcript_path`.
  - **Diferencia con el supuesto:** el subagente no termina con un mensaje de texto, sino con una llamada a la herramienta `SubagentHandback` cuyo `input.message` es la respuesta final. Le sigue un `tool_result`. Las cinco primeras revisiones reales quedaron como `sin_veredicto` con un extracto intermedio. Ahora el parser toma el `SubagentHandback` como respuesta final y, si la transcripción no la tiene, recurre a `last_assistant_message`. Con las transcripciones reales, las cinco dan su veredicto y sus severidades.
