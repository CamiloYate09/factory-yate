# Registro de progreso

## Estado verificado actual

- Raíz del repositorio: `factory-yate/`, la que contiene `AGENTS.md`.
- Arranque estándar: `./init.sh`.
- Verificación estándar: `./scripts/check.sh`.
- OpenSpec: specs principales en `openspec/specs/` (11 capacidades). Cambios archivados: `2026-10-27-add-harness-loop-engine`, `2026-10-28-extend-factory-pipeline` y `2026-10-28-add-knowledge-brains`. No hay cambios activos.
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

### Sesión 004 — 2026-10-28

- Objetivo: archivar `add-harness-loop-engine` y aplicar `extend-factory-pipeline`, que adapta patrones de *Software Factory v2* (ZazenCodes, GPLv3) sin copiar código.
- Completado:
  - Archivo del cambio anterior, con las 6 specs principales sincronizadas.
  - Rutas protegidas: críticas siempre protegidas, `tests/**` en este repo y `scope.allow_modify`.
  - Artefactos por ronda: `rounds/<n>/{maker,checks,review}.md` y `decision.md`.
  - `factory goal rework`.
  - `factory land`: merge exacto verificado, `--ff-only`, sin push.
  - `factory intake` y `factory goal promote`, con borradores no ejecutables.
  - README: guía paso a paso con requisitos y pasos A–F.
  - Documentos temáticos nuevos: `intake.md`, `revision.md` y `vigilancia.md`.
- Verificación ejecutada:
  - `./scripts/check.sh` → código 0 (272 tests, ruff y doctor).
  - `openspec validate extend-factory-pipeline --strict` → válido.
  - Pasos B–D del README sobre un proyecto nuevo, con instalación no editable → en verde.
- Evidencia: `factory features verify` → `passing` en `protected-paths`, `round-artifacts`, `run-rework`, `run-landing` y `request-intake`. El commit de la evidencia es `7563c8f` porque los cambios aún no están commiteados.
- Tarea 7.2 (aprobada, 1 USD como máximo): intake real de la petición "init.sh de factory init con .venv en proyectos Python".
  - Resultado: `ACCEPT`, riesgo `medium`, superficie `harness`, sin recorte. `claude-opus-5-5`, 12 turnos, **0,4389 USD**, sin denegaciones de permisos.
  - El borrador cita `scaffold.py:68-74` y propone 3 criterios ejecutables.
  - En la revisión de `goal promote`, el plan mostró que `tests/**` está protegido, mientras el borrador pedía añadir tests a `tests/test_init.py`, que ya existe. Se añadió `allow_modify: [tests/test_init.py]`, después `promote --yes` y luego `goal run --dry-run` → en verde. Petición en `promoted`; objetivo en `goals/en-repos-con-pyproject-toml-factory.md`, listo para un `goal run` real.
  - Hallazgo: el intake no conoce `protected_paths`. Mejora propuesta: dárselos en el prompt y admitir `scope.allow_modify` en su esquema.
- Riesgos / pendientes:
  - Ningún cambio de esta sesión está commiteado.
  - El `init.sh` que genera `factory init` en proyectos Python instala con pip en el Python global; queda como mejora fuera de alcance (avisado en el README).
- Archivado: `extend-factory-pipeline` en `openspec/changes/archive/2026-10-28-extend-factory-pipeline/`, con specs sincronizadas (goal-loop +4, loop-state +2, run-landing y request-intake nuevas).
- Mejor próximo paso: opcionalmente, `factory goal run goals/en-repos-con-pyproject-toml-factory.md` (real, con coste) y `factory land`.

### Sesión 005 — 2026-10-28

- Objetivo: aplicar `add-knowledge-brains`: cerebro principal (copia de los libros, fuera de git) y cerebro diario (versionado), con búsqueda e inyección acotada en los loops. Indicación del usuario: solo archivos `.md`; los `.pdf` se descartan en `.gitignore`.
- Completado:
  - `factory brain import|status|search|learn|reindex|commit|pending|accept|reject`.
  - Importación filtrada (`.md` + índices), atómica y validada; `/brain-principal/` y `*.pdf` en `.gitignore`; check crítico de `doctor` si el principal llega a git.
  - Cerebro diario con catálogo e índices propios; ruta prohibida en todo objetivo; `factory brain commit` solo de `brain-diario/`.
  - Capturas deterministas al terminar cada ejecución, pendientes de revisión, con salvaguarda de 8-gramas contra texto de libros.
  - Búsqueda por palabras clave (sin dependencias) e inyección citada en el prompt de usuario del maker (una selección por ejecución, presupuesto `inject_max_tokens`, evento `knowledge`); el intake recibe notas del diario y las rutas de los catálogos; el checker no recibe nada.
  - Acceso de lectura: `--add-dir` por cerebro, denegaciones `Edit/Write(//<ruta>/**)` añadidas en cada invocación y huella de integridad al inicio y al final con aviso en `decision.md` y la bandeja.
  - Documentación: `docs/harness/cerebros.md`, `loops.md` (`knowledge`) y paso G del README.
- Ajustes de diseño tras medir con el vault real (registrados en `design.md`, D3 y D4):
  - **Cobertura en la puntuación.** Para "rate limiting", 5 de las 8 mejores notas solo contenían "rate" ("Rate of Change", "Learning Rate Scheduling"). Ahora la puntuación se multiplica por la fracción de términos encontrados.
  - **Fusión intercalada.** Con `["rate limiting", "api gateway"]`, ordenar solo por puntuación daba las 8 plazas a "api gateway". Ahora se intercala la mejor nota de cada consulta.
- Verificación ejecutada:
  - `./scripts/check.sh` → código 0 (330 tests, ruff y doctor sin fallos).
  - `openspec validate add-knowledge-brains --strict` → válido.
  - `factory features verify` → `passing` en `main-brain`, `daily-brain`, `brain-captures` y `brain-retrieval`.
- Tarea 6.2 (sin coste de API), vault real `/Users/camiloyateyara/PycharmProjects/redPDF/book/obsidian-vault`:
  - `factory brain import` → 11.245 notas, 82 libros, ~13,0 M tokens, en ~3 s. Copiados 11.330 `.md` (notas + guías) y 4 índices; ningún PDF.
  - `git status` → nada de `brain-principal/` (`git check-ignore` lo confirma); `factory doctor` → `brain-principal-untracked` en PASS.
  - `factory brain search "rate limiting"` → primeros resultados *Defending APIs* · cap. 9 · pp. 259–260 y *Privacy and Security for LLMs* · cap. 5.
  - Selección simulada para `["rate limiting", "api gateway"]` → 8 notas en 0,42 s, 3 en texto completo (2.659/3.000 tokens) y 5 como referencia, con ambas consultas representadas.
- Tarea 6.3 (aprobada, ≤ 0,50 USD): dos invocaciones reales vía `ClaudeCodeRunner` (mismos argumentos que el motor), `claude-haiku-5-5`, `acceptEdits`, en directorios temporales del scratchpad (no sobre `brain-principal/`):
  - `Write` de `brain/probe.txt` → en `permission_denials`, archivo inexistente (0,0061 USD, 4 turnos).
  - `Edit` de `brain/nota.md` existente → en `permission_denials`, contenido intacto (0,0040 USD, 5 turnos).
  - En ambas, escribir en el cwd y leer/`Glob` del cerebro funcionó; la sintaxis `Edit(//<ruta absoluta>/**)` es correcta y no hubo que ajustarla.
  - El `CLAUDE.md` del cerebro (con una palabra de control) **no** se cargó en el contexto vía `--add-dir`: la palabra no apareció y el agente lo confirmó.
  - Coste total: **0,0101 USD**.
  - Ajuste derivado: `Config._abs` ahora resuelve también las rutas absolutas, para que `--add-dir` y las denegaciones coincidan si la ruta tiene enlaces (`/tmp` → `/private/tmp`). Test `test_ruta_absoluta_con_enlace_se_resuelve`.
- Revisión independiente (subagente `checker`), primera pasada: `fail`, con 4 `medium` y 6 `low`. Todos corregidos con tests:
  - un catálogo roto ya no deja una ejecución huérfana ni tumba el intake (queda como aviso);
  - el presupuesto mide el texto que de verdad se inyecta;
  - la fusión agrupa por consulta (el diario ya no recibe plazas de más);
  - la salvaguarda de capturas cubre también el `abstract` de las notas solo citadas;
  - la huella ignora archivos ocultos (`.DS_Store`, `.obsidian/`) y avisa si aparece un cerebro;
  - las denegaciones se emiten aunque el cerebro aún no exista;
  - la integridad se comprueba después de la promoción;
  - las cabeceras de cita se reducen a una línea;
  - se quitó el gancho de test del motor.
  - D4 y `cerebros.md` actualizados. `./scripts/check.sh` → código 0 (339 tests).
- Segunda pasada del `checker`: `pass_with_minor`, con los 10 hallazgos cerrados y 3 `low` nuevos, también corregidos:
  - un `chapter_title` no textual en el catálogo ya no rompe el loop ni el intake;
  - un fallo de la huella inicial ya no produce un falso aviso de integridad;
  - D5 y D7 describen lo implementado.
- Incidencia: durante la sesión apareció `/ba` delante de la primera línea de `factory.toml` (tecleo accidental, no generado por factory), lo que rompía el TOML. Se quitó con el visto bueno del usuario.
- Riesgos / pendientes:
- Archivado: `add-knowledge-brains` en `openspec/changes/archive/2026-10-28-add-knowledge-brains/`, con specs sincronizadas (`main-brain`, `daily-brain` y `brain-retrieval`, nuevas; 21 requisitos).
- Integrada con `factory land` (a petición del usuario) la ejecución `20261028-052249-en-repos-con-pyproject-toml-factory-a254` (objetivo `en-repos-con-pyproject-toml-factory`, 2 rondas, 2,14 USD): merge `1fa6e05` sobre `31423c1`, verificado antes de mover `main`, sin push. El `init.sh` de `factory init` en proyectos Python crea e instala en un `.venv` propio; se quitó del README el aviso sobre pip global. La rama `factory/20261028-052249-…-a254` se conserva.
- Mejor próximo paso: empezar a alimentar el cerebro diario con `factory brain learn` y lanzar un objetivo real con `knowledge.queries`.
