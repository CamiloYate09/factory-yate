# Proposal

## Why

`factory-yate` está vacío (solo el `main.py` de ejemplo de PyCharm). Queremos que sea una "fábrica" donde los agentes de codificación trabajen de forma fiable y, después, de forma autónoma. Según el curso *Learn Harness Engineering* (lecciones 1–13, proyecto 07), eso exige dos capas, en este orden:

1. Un **harness**: instrucciones, estado, verificación, alcance y ciclo de vida. Hace fiable cada ejecución individual.
2. Un **loop**: objetivo + verificación + condición de parada, con maker y checker separados y estado externo. Hace que las ejecuciones continuas no necesiten que un humano dé cada instrucción.

Hoy no existe ninguna de las dos. Además, en esta instalación de Claude Code no hay un `/goal` nativo, así que el loop debe ser propio, determinista y auditable.

## What Changes

**Fase 1: harness del repositorio** (prerrequisito; L03–L12)
- Archivo de instrucciones que actúa como router corto (`AGENTS.md`, importado desde `CLAUDE.md`) y documentos temáticos en `docs/harness/`.
- Entorno Python reproducible (`pyproject.toml`, paquete `src/factory/`, pytest, ruff). Se elimina el `main.py` de ejemplo de PyCharm; el punto de entrada pasa a ser `src/factory/__main__.py`.
- Una ruta de arranque estándar (`init.sh`) y una ruta de verificación única (`scripts/check.sh`).
- Estado durable en el repo:
  - `feature_list.json`: cada feature tiene comportamiento, verificación y estado, con WIP=1.
  - `progress.md` y `session-handoff.md`.
- Reglas de completitud: una feature solo pasa a `passing` con evidencia de verificación ejecutada. Toda sesión cierra en *clean state*.
- Subagente `checker` de solo lectura en `.claude/agents/` para separar generador y evaluador también en sesiones interactivas.

**Fase 2: motor de loops `factory`** (CLI Python que orquesta `claude -p`; L13, P07)
- `factory goal run <goal.md>`: loop de objetivo. Itera hasta que pasan los criterios de aceptación verificables por máquina o salta una condición de parada (rondas máximas, presupuesto en USD, sin progreso durante K rondas, bloqueo).
- Loop maker-checker: el maker y el checker son invocaciones separadas, con contexto nuevo, herramientas y modelo distintos. El checker es de solo lectura y emite un veredicto estructurado. El orquestador ejecuta la verificación determinista y decide; el agente nunca se autoaprueba.
- Aislamiento por `git worktree` y rama propia por ejecución. Ratchet: se revierte la ronda que empeora la verificación. Nunca se hace merge ni push automático.
- Estado externo y observabilidad por ejecución:
  - `loop-state.md`, `events.jsonl` y un `results.tsv` acumulado.
  - Una bandeja de revisión humana (*inbox*).
  - Métricas para vigilar los cuatro costes silenciosos.
- `factory tick <goal.md>`: loop por tiempo, idempotente y con bloqueo. Primero ejecuta la verificación, que no gasta tokens, y solo lanza un loop acotado si algo falla. Se programa con cron/launchd o con `/loop` de Claude Code.
- `factory init` / `factory doctor`: aplican y auditan el harness en este o en otro repositorio, para software o para cualquier flujo de trabajo cuyo éxito se pueda comprobar con comandos.

**Fuera de alcance**:
- Niveles 4–5 de la escalera de madurez: loops auto-alimentados que eligen la siguiente tarea y orquestación de flotas.
- Grafos (L14), disparadores por eventos (webhooks/GitHub Actions) y connectors MCP.
- Adaptadores para agentes distintos de Claude Code.

## Capabilities

### New Capabilities
- `agent-harness`: contrato del harness del repositorio. Cubre el archivo de instrucciones router, la lista de features con su máquina de estados, las rutas estándar de arranque y verificación, el progreso, el handoff y el clean state.
- `harness-scaffolding`: generación (`factory init`) y auditoría (`factory doctor`) del harness en un repositorio destino.
- `goal-loop`: definición de objetivos en `goal.md` y su ejecución iterativa con condiciones de parada verificables por máquina y presupuesto.
- `maker-checker-loop`: separación generador/evaluador. Cubre los roles con contexto y permisos independientes, el veredicto estructurado, la retroalimentación entre rondas, el aislamiento por worktree y el ratchet.
- `loop-state`: estado externo y observabilidad de los loops (estado por ejecución, registro de resultados, eventos, coste, inbox de revisión humana).
- `scheduled-loop`: ejecución periódica idempotente (`factory tick`) con bloqueo, verificación previa sin coste y escalado a humano.

### Modified Capabilities
<!-- Ninguna: el proyecto aún no tiene specs. -->

## Impact

- **Código nuevo**: paquete `src/factory/` (CLI, adaptador de agentes, loops, estado), `tests/`, `scripts/check.sh`, `init.sh`.
- **Archivo eliminado**: el `main.py` de ejemplo de PyCharm, que hoy está en el índice de git (`AM`). Lo reemplaza `src/factory/__main__.py` (`python -m factory`).
- **Archivos de harness nuevos**: `AGENTS.md`, `CLAUDE.md`, `feature_list.json`, `progress.md`, `session-handoff.md`, `docs/harness/`, `.claude/agents/checker.md`, `goals/`, `factory.toml`, `.gitignore`.
- **Dependencias**:
  - Python ≥ 3.11; `pyyaml` en tiempo de ejecución; `pytest` y `ruff` para desarrollo.
  - CLI `claude` (Claude Code ≥ 2.1) en el `PATH` para los loops reales.
  - `git` con al menos un commit en `main`, porque los worktrees lo necesitan y hoy no hay ninguno.
- **Coste**: los loops reales consumen API. Por eso cada ejecución está acotada por presupuesto y número de rondas, y los tests usan un agente simulado.
- **Atribución**: las plantillas (goal, loop-state, prompts maker/checker, feature list, checklists) se adaptan del curso walkinglabs/learn-harness-engineering (licencia MIT).
