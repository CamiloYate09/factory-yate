# Proposal

## Why

factory-yate ya combina harness, motor de loops, OpenSpec, cerebros y un equipo de hasta 11 jugadores. La información para seguirlos está repartida: el coste de los loops en `.factory/runs/*/events.jsonl`, el de las sesiones interactivas y sus subagentes en las transcripciones de Claude Code, las revisiones en la salida de cada subagente y el avance en `feature_list.json` y los `tasks.md`. Hoy nadie ve de un vistazo cuántos tokens se gastan ni en qué, qué revisión está en marcha o qué dictaminó, ni cuánto le falta a una tarea. `factory status` solo cubre los loops, en texto y sin tiempo real.

## What Changes

**`factory panel`: panel gráfico local**
- Servidor HTTP de la stdlib en `127.0.0.1` que sirve una página estática empaquetada (HTML, CSS y JS en línea, gráficos SVG propios, sin CDN ni dependencias).
- `/api/snapshot` devuelve todo el estado en JSON. `/api/stream` (SSE) avisa cuando cambia algún archivo vigilado y la página se actualiza sola.
- `factory panel --json` imprime la misma instantánea y termina, para scripts y tests.
- Solo lectura: no escribe en el repo ni en `.factory/`. Rechaza peticiones con una cabecera `Host` ajena (protección contra *DNS rebinding*).

**Consumo de tokens**
- Loops de factory: tokens de entrada y salida, turnos y coste en USD por ejecución, rol y modelo, desde los eventos `agent` de `events.jsonl`.
- Sesiones de Claude Code del repo y de sus worktrees `.claude/worktrees/*`, incluidos los subagentes (con su tipo: `checker`, jugadores…): entrada, escritura y lectura de caché y salida, por día, modelo, tipo de agente y sesión. Se deduplica por id de mensaje, porque cada bloque de contenido repite el `usage`.
- El USD solo aparece donde se registró (los loops). Para las sesiones interactivas se muestran tokens, sin precios estimados.
- De las transcripciones solo se extraen modelo, `usage`, marca de tiempo e identificadores. Nunca el texto de los mensajes.

**Revisiones en tiempo real con hooks**
- `factory hook`: lee el JSON de un hook de Claude Code por stdin y añade una línea a `.factory/hooks/events.jsonl` del repo principal (también desde un worktree). Siempre termina en 0, no escribe en stdout y nunca bloquea una herramienta.
- `.claude/settings.json` registra el hook en `PreToolUse` (matcher `Agent|Task`: lanzamiento de un subagente) y en `SubagentStop` (fin, con el veredicto y el recuento de hallazgos por severidad extraídos de la última respuesta del subagente).
- Cuentan como revisores el `checker` (árbitro) y los agentes de `.claude/agents/` con `tipo: revisor`.
- El panel une esos eventos con los veredictos del checker de los loops (`state.json`) en un único feed de revisiones: en curso, aprobadas, con menores o fallidas.

**Estado de implementación de una tarea**
- Features de `feature_list.json` por estado, con WIP, comandos de verificación y evidencia.
- Cambios OpenSpec activos con el avance de `tasks.md` por grupo, enlazado a su feature cuando el título del grupo la nombra entre comillas invertidas.
- Ejecuciones de factory: estado, ronda, criterios, último veredicto, coste y si siguen vivas; bandeja pendiente.
- Vista de detalle de una feature: tareas de su grupo, evidencia, ejecuciones y revisiones relacionadas.

**Fuera de alcance**
- Pull requests de GitHub (`gh`): los agentes de este repo no hacen push ni PRs. "Revisión de PR" significa aquí la revisión de un diff o de una rama local por el `checker` o un jugador revisor.
- Precios estimados de las sesiones interactivas.
- Escribir desde el panel: no inicia, verifica ni aprueba nada.
- Proteger `.claude/settings.json` y `.claude/hooks/**` frente a los makers de los loops. Encaja con la D7 de `add-equipo-ideal`, que ya modifica las rutas críticas de `protection.py`, y se les propone como seguimiento para no editar ese archivo en paralelo.
- Exponer el panel fuera de la máquina local.

## Capabilities

### New Capabilities
- `token-usage`: agregación del consumo de tokens de los loops y de las sesiones de Claude Code (incluidos subagentes), con deduplicación, privacidad y coste solo donde se registró.
- `review-hooks`: captura con hooks de Claude Code del inicio y el fin de cada revisión de subagente, extracción del veredicto y feed unificado con las revisiones de los loops.
- `observability-panel`: el panel local (`factory panel`): instantánea JSON, actualización en vivo, página gráfica y estado de implementación de features, cambios OpenSpec y ejecuciones.

### Modified Capabilities
<!-- Ninguna: el panel solo lee el estado que ya definen `loop-state` y `agent-harness`. -->

## Impact

- **Código:** paquete nuevo `src/factory/panel/` (`tokens.py`, `hooks.py`, `reviews.py`, `tasks.py`, `snapshot.py`, `server.py` y `static/index.html`) y dos subcomandos, `panel` y `hook`, registrados en `cli.py` con import dentro del handler. Es un diff pequeño para no chocar con `add-equipo-ideal`, que también edita `cli.py`.
- **Archivos:**
  - `.claude/settings.json` (nuevo) y `.claude/hooks/panel-hook.sh`;
  - `docs/harness/panel.md` y un enlace en `AGENTS.md`;
  - tres features nuevas en `feature_list.json` (prioridades 24–26).
- **Dependencias:** ninguna.
- **Coste:** el panel y el hook no llaman a la API. El hook añade unos milisegundos a cada lanzamiento y fin de subagente.
- **Privacidad:** el panel lee transcripciones locales de `~/.claude/projects/` (o `$CLAUDE_CONFIG_DIR/projects/`), pero solo expone recuentos y metadatos. El feed de revisiones guarda el veredicto y un extracto acotado de la respuesta del revisor.
