# Registro de progreso

## Estado verificado actual

- Raíz del repositorio: `factory-yate/`, la que contiene `AGENTS.md`.
- Arranque estándar: `./init.sh`.
- Verificación estándar: `./scripts/check.sh`.
- Cambio OpenSpec en curso: `openspec/changes/add-harness-loop-engine/`. Progreso en su `tasks.md`.
- Feature activa / siguiente: ver `.venv/bin/factory features list`.
- Commits: `d7c3d5b` (commit inicial) y `9d74594` (evidencia de las features con hash real).
- Bloqueos actuales: la prueba live (9.2) no está aprobada. El contrato de `--json-schema` se valida con el dogfooding (9.3).

## Registro de sesiones

### Sesión 001 — 2026-10-27

- Objetivo: fase 1 del cambio `add-harness-loop-engine`, es decir, la base Python y el harness del repo.
- Completado:
  - `.gitignore`.
  - `pyproject.toml` (paquete `factory`, Python ≥ 3.12, `pyyaml`; dev: `pytest`, `ruff`).
  - `init.sh` y `scripts/check.sh`.
  - `factory features validate|list|start|verify` y `factory doctor [--json]`.
  - `AGENTS.md`, `CLAUDE.md` y `docs/harness/` (verificación, features, sesiones, roles, checklist de clean state).
  - `session-handoff.md`.
  - Se eliminó el `main.py` de ejemplo de PyCharm.
- Verificación ejecutada:
  - `rm -rf .venv && ./init.sh` → código 0.
  - `./scripts/check.sh` → código 0. Desde la tarea 3.7 incluye `factory doctor`.
  - Una copia limpia del árbol (sin `.venv` ni `.git`) en el scratchpad con `./init.sh` → código 0.
- Evidencia:
  - `factory features verify harness-core` → `passing`. El commit de la evidencia es `sin-commit` porque aún no hay commits.
  - Poner a mano `loop-config` en `passing` hace fallar `./scripts/check.sh` (paso `harness`), y al revertirlo vuelve a verde.
  - Tarea 3.2: `claude -p` (haiku, sin herramientas de lectura) respondió `./scripts/check.sh` en 1 turno (0,0035 USD).
  - Tarea 3.5: con un diff de prueba que relajaba WIP a 2 y modificaba su test, `claude -p --agent checker` (sonnet) devolvió `fail` con dos hallazgos `critical` (regresión WIP y test debilitado), ambos con ubicación y evidencia. `git status --porcelain` quedó idéntico antes y después (0,05 USD, 2 turnos).
  - Tarea 3.10, parcial: una sesión nueva (haiku, solo Read/Glob/Grep) respondió con artefactos del repo las 5 preguntas de arranque en frío. Identificó `loop-config` como siguiente feature y los bloqueos de commit y de la prueba live (0,006 USD). Falta repetirlo desde un `git clone`, que requiere el commit inicial.
  - El JSON de `claude -p --output-format json` incluye `permission_denials`, `total_cost_usd`, `usage` y `num_turns`. Este dato adelanta parte de la pregunta abierta de la tarea 9.2.
- Riesgos / pendientes: el commit inicial (3.9) y la prueba live (9.2) no están aprobados.
- Mejor próximo paso: continuar `tasks.md` del cambio OpenSpec.

### Sesión 002 — 2026-10-27

- Objetivo: fase 2 del cambio `add-harness-loop-engine` (grupos 4–8) y la validación 9.1.
- Completado:
  - `factory.toml` y `goal.md` (frontmatter YAML, globs de alcance, límites por defecto).
  - Adaptadores `ClaudeCodeRunner` (`claude -p`) y `FakeRunner`.
  - Esquemas y validación del informe del maker y del veredicto del checker.
  - Prompts de los roles.
  - Estado externo: `state.json`, `loop-state.md`, `events.jsonl`, `results.tsv` y la bandeja.
  - `factory status` con los cuatro costes silenciosos.
  - Worktrees fuera del repo.
  - Motor maker-checker con ratchet y condiciones de parada.
  - `factory goal run [--dry-run]`.
  - `factory tick`: bloqueo, guardas, cortacircuitos y presupuesto diario.
  - `factory schedule`.
  - `factory init` con plantillas empaquetadas.
  - Documentos `docs/harness/loops.md` y `observabilidad.md`.
- Verificación ejecutada:
  - `./scripts/check.sh` → código 0 (194 tests, ruff y doctor).
  - `openspec validate add-harness-loop-engine --strict` → válido.
  - `factory tick goals/vigilancia-check.md` → `noop`, coste 0.
  - Las plantillas aparecen en el wheel (`pip wheel`).
- Evidencia: `factory features verify` en `loop-config`, `loop-state`, `maker-checker-engine`, `scheduled-loop` y `harness-scaffolding` → `passing`.
- Hallazgo de diseño resuelto: en un worktree, `python -m pytest` importaría `factory` desde la instalación editable del repo principal. Se resolvió anteponiendo `<cwd>/src` a `PYTHONPATH` en los comandos de verificación y en el entorno del maker (`util.command_env`).
- Riesgos / pendientes:
  - 3.9 (commit inicial) y 9.2 (prueba live) no están aprobados.
  - 9.3 (dogfooding) está aprobada, pero depende de 3.9.
  - La revisión independiente del `checker` se hizo una sola vez sobre toda la fase 2 (ver abajo), no feature a feature.
- Revisión independiente de la fase 2 (aprobada; `claude -p --agent checker`, sonnet, 0,42 USD, 24 turnos, `git status` sin cambios). Veredicto `fail` con 3 hallazgos `medium` y 5 `minor`. Todos se corrigieron con tests, salvo uno que se documentó:
  - medium: carrera en el bloqueo del tick → `flock` sobre un archivo guarda, `pid <= 0` no cuenta como vivo, un bloqueo vacío y reciente cuenta como ocupado. Hay un test con 8 procesos concurrentes.
  - medium: `goal.md` o `factory.toml` podían vaciar `denied_tools` → `enforce_role_policy` impone las denegaciones obligatorias y limita el checker a lectura.
  - medium: un tick cuyo motor lanzaba una excepción no se registraba → ahora se registra con `run_status=error`, suma el gasto y cuenta para el cortacircuitos.
  - minor: promoción fallida sin aviso → aviso en `stop_reason` y sección "Bloqueos y avisos" en la bandeja; además, timeout en la verificación de la feature.
  - minor: sin presupuesto tras el maker → el checker no se invoca.
  - minor: un fallo de `create_worktree` dejaba `running` → ahora queda `interrupted` y va a la bandeja.
  - minor: el test de push ahora comprueba el argv real del CLI.
  - minor: la guarda no ve archivos ignorados por git → documentado en `roles.md`.
- Mejor próximo paso:
  - con aprobación, hacer el commit inicial;
  - repetir `factory features verify` para registrar los hashes;
  - ejecutar 3.10 desde un clon;
  - lanzar el dogfooding (9.3).

### Sesión 003 — 2026-10-27

- Objetivo: tareas 3.9, 3.10 y 9.3 (aprobadas).
- Completado:
  - commit inicial `d7c3d5b`;
  - repetición de `factory features verify` en las 6 features (la evidencia apunta a `d7c3d5b`) y commit `9d74594`.
- Verificación ejecutada:
  - `git clone` en el scratchpad y `./init.sh` → código 0 (doctor sin fallos).
  - Sesión nueva (haiku, solo lectura) sobre el clon: respondió las 5 preguntas (0,008 USD). Detectó que este `progress.md` decía "sin commits" → corregido aquí.
- Dogfooding 9.3 (`goals/dogfood-cli-help.md`), ejecución `20261028-040428-dogfood-cli-help-90b9`:
  - Resultado: `completed` en 1 ronda y 41 s, por 0,4468 USD (tope 1,00 USD). Maker `claude-sonnet-5-5` con 0,13 USD y 4 turnos; checker `claude-opus-5-5` con 0,31 USD y 6 turnos.
  - Base: 1 de 3 criterios fallaba (el test no existía). Ronda 1: 3 de 3, checker `pass_with_minor`, decisión `keep`.
  - Rama: `factory/20261028-040428-dogfood-cli-help-90b9` (commit `ed18856`, añade `tests/test_cli_help.py`, +16 líneas). `main` sigue en `9d74594`. El worktree hermano se eliminó y queda una entrada pendiente en la bandeja.
  - Contrato del CLI confirmado con una ejecución real: `--json-schema` devolvió una salida estructurada válida para ambos roles. No hubo `permission_denials` ni bloqueos por confianza en el worktree fuera del repo. `modelUsage` confirma modelos distintos por rol. No se registró en qué clave exacta llegó la salida (campo estructurado o JSON en `result`); el adaptador acepta las dos.
- Retrospectiva (proyecto 07):
  - Intervenciones humanas durante la ejecución: 0.
  - El checker detectó 2 problemas `minor`, ambos válidos:
    - la lista de subcomandos está escrita a mano y no se contrasta con `build_parser`;
    - la comprobación `"  nombre" in texto` es una subcadena laxa.
  - El checker no pasó por alto ningún problema mayor visible: el test es pequeño y correcto.
  - Límite observado: `pass_with_minor` aprueba la ronda, así que los `minor` no generan una segunda ronda. Corregirlos queda a criterio humano al revisar la rama. Si se quieren corregir automáticamente, sube `consecutive_passes` o trata `minor` como bloqueante en un objetivo concreto.
  - Techo de calidad del loop: lo marca el criterio del checker, más que la capacidad del maker. Con criterios deterministas más finos (por ejemplo, contrastar con los subparsers) el maker habría tenido que hacerlo así.
  - Coste vs. valor: 0,45 USD y unos 40 s por un test pequeño. Para tareas triviales sale más caro que hacerlo a mano. Rinde en tareas medianas con criterios claros.
- Pendiente para el humano:
  - revisar y decidir la rama del dogfooding (`factory inbox ack <run-id>` al terminar);
  - hacer commit de `progress.md`, `tasks.md` y `goals/dogfood-cli-help.md`, que no están commiteados;
  - decidir la prueba live 9.2, que no está aprobada.
