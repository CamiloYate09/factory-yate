# Tasks

> **Fase 1: harness del repo.** Grupos 1–3.
>
> **Fase 2: motor `factory`.** Grupos 4–8. Desde el grupo 4, cada grupo corresponde a una feature de `feature_list.json`: se marca con `factory features start <id>` al empezar y se cierra con `factory features verify <id>`, que pasa a `passing` con evidencia (dogfooding).

## 1. Base del proyecto Python (fase 1)

- [x] 1.1 Crear `.gitignore` con `.venv/`, `.factory/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/` e `.idea/`. Verificar con `git check-ignore .factory/x .venv/x .idea/x`, que debe listar las tres rutas.
- [x] 1.2 Crear `pyproject.toml`:
  - paquete `factory`, layout `src/`, `requires-python >=3.12`;
  - dependencia `pyyaml` y extras `dev` con `pytest` y `ruff`;
  - script `factory = "factory.cli:main"`;
  - configuración de `ruff` y `pytest` que excluya `.factory/`, con `testpaths = ["tests"]`.

  Crear también `src/factory/{__init__,__main__,cli}.py` con `--version` y eliminar el `main.py` de ejemplo de PyCharm. Verificar que `python -m factory --version` y `factory --version` imprimen la versión.
- [x] 1.3 Crear `scripts/check.sh` (`ruff check`, `ruff format --check`, `pytest -q`) para que se detenga en el primer fallo e imprima la comprobación fallida y el comando para reproducirla. Añadir `tests/test_smoke.py`. Verificar que `./scripts/check.sh` termina en 0 y que, con un test que falla a propósito, termina con un código distinto de cero y nombra el test.
- [x] 1.4 Crear `init.sh`:
  - usa `uv` si existe; si no, `python3 -m venv .venv` + `pip install -e '.[dev]'`;
  - ejecuta `scripts/check.sh` y propaga su código de salida.

  Verificar que `rm -rf .venv && ./init.sh` termina en 0 sin pasos manuales.

## 2. Lista de features y verificación del harness (fase 1, `agent-harness` / `harness-scaffolding`)

- [x] 2.1 Implementar la carga y validación de `feature_list.json`:
  - campos obligatorios y estados válidos;
  - `verification` como lista de comandos y `manual_checks` aparte;
  - WIP=1;
  - `passing` exige evidencia.

  Verificar con `pytest tests/test_features.py`, que cubre los escenarios "Feature incompleta en la lista", "Dos features activas" y "Promoción manual sin evidencia".
- [x] 2.2 Implementar `factory features validate|start|verify <id>`:
  - `start` hace cumplir WIP=1;
  - `verify` ejecuta los comandos y, solo si todos pasan, promueve a `passing` registrando comando, código, fecha y commit;
  - si algo falla, informa el comando que falló.

  Verificar con `pytest tests/test_features_cli.py` sobre repos git temporales, que cubre "Verificación exitosa" y "Verificación fallida".
- [x] 2.3 Implementar `factory doctor [--json]`. Las comprobaciones se agrupan por subsistema:
  - instrucciones: 200 líneas o menos y enlaces que existen;
  - estado: lista válida y `progress.md`;
  - verificación: comando definido y ejecutable;
  - alcance: WIP=1;
  - ciclo de vida: handoff y checklist.

  Cada comprobación lleva severidad crítica o recomendada y una acción correctiva. El reporte señala el subsistema más débil con hasta 3 acciones, y el comando termina con un código distinto de cero si falla alguna crítica. Verificar con `pytest tests/test_doctor.py`, que cubre "Harness completo", "Falta la ruta de verificación", "Subsistema más débil", "Consumo desde otro proceso" y "Archivo de entrada excede el límite".

## 3. Artefactos del harness del repo (fase 1, `agent-harness`)

- [x] 3.1 Escribir `AGENTS.md` como router de 200 líneas o menos. Debe incluir:
  - resumen del proyecto;
  - arranque con `./init.sh` y verificación con `./scripts/check.sh`;
  - restricciones duras: no editar estados de features a mano, no debilitar ni borrar tests, no hacer push ni merge desde agentes;
  - definición de terminado, rutina de inicio y de cierre de sesión;
  - enlaces a `docs/harness/`.

  Verificar que las comprobaciones de instrucciones de `factory doctor` pasan.
- [x] 3.2 Escribir `CLAUDE.md` con `@AGENTS.md` más las notas propias de Claude Code: cuándo usar el subagente `checker` y cómo cerrar sesión. Verificar que una sesión nueva de `claude` responde correctamente "¿cuál es el comando de verificación?" sin leer otros archivos.
- [x] 3.3 Escribir `docs/harness/verificacion.md`, `features.md`, `sesiones.md` y `roles.md`, de 50 a 150 líneas cada uno, adaptados del curso con atribución MIT. Verificar que `factory doctor` confirma que todos los enlaces de `AGENTS.md` resuelven.
- [x] 3.4 Crear `progress.md` (estado verificado actual y registro por sesión), `session-handoff.md` y `docs/harness/clean-state-checklist.md`. Verificar que las comprobaciones de ciclo de vida de `factory doctor` pasan.
- [x] 3.5 Crear `.claude/agents/checker.md`:
  - herramientas Read, Grep y Glob;
  - prompt adversarial con checklist (corrección, calidad, tests significativos o debilitados, impacto);
  - formato de veredicto con ubicación, evidencia y severidad.

  Verificar invocándolo sobre un diff de prueba: debe devolver un veredicto con evidencia y `git status` no debe cambiar. Registrar la evidencia en `progress.md`.
- [x] 3.6 Poblar `feature_list.json` con las features de la fase 2: una por cada grupo del 4 al 8, cada una con sus comandos de verificación (`pytest tests/<archivo>`). Verificar que `factory features validate` pasa.
- [x] 3.7 Añadir `factory doctor` a `scripts/check.sh`, ahora que existen todos los artefactos. Verificar que `./scripts/check.sh` termina en 0, que poner a mano una feature en `passing` sin evidencia lo hace fallar identificando la feature, y que vuelve a verde al revertirlo.
- [x] 3.8 Escribir `README.md`: qué es factory-yate, las fases, el inicio rápido y la atribución al curso walkinglabs/learn-harness-engineering (MIT). Verificar que los comandos del inicio rápido se ejecutan tal como están escritos.
- [x] 3.9 **Con aprobación explícita del usuario**, hacer el commit inicial en `main` con todo el harness. Es un prerrequisito para los worktrees de la fase 2. Verificar que `git log --oneline` muestra el commit y `git status` está limpio.
- [x] 3.10 Hacer la prueba de arranque en frío:
  - clonar el repo en un directorio temporal y ejecutar `./init.sh`, que debe terminar en 0;
  - una sesión nueva debe responder solo con artefactos del repo qué es el proyecto, cómo arrancar, cómo verificar, cuál es la siguiente feature y qué riesgos hay.

  Registrar la evidencia en `progress.md`.

## 4. Configuración, goal.md y adaptador de agentes (fase 2, `goal-loop` / `maker-checker-loop`)

- [x] 4.1 Implementar la carga de `factory.toml`: verificación, roles (modelo, herramientas permitidas y denegadas, `permission_mode`, prompt), límites por defecto de D3 y umbrales de alertas. Crear el `factory.toml` del repo. Verificar con `pytest tests/test_config.py`, incluido el rechazo de `bypassPermissions` como modo.
- [x] 4.2 Implementar el parser y validador de `goal.md`:
  - frontmatter YAML y cuerpo;
  - al menos un criterio con `run`;
  - `mode: finite|monitor`;
  - globs de alcance, con `feature_list.json` siempre en `deny`;
  - límites por defecto.

  Crear `goals/_template.md`, adaptado del curso. Verificar con `pytest tests/test_goal.py`, que cubre "Objetivo válido", "Criterios no verificables" y "goal.md sin límites".
- [x] 4.3 Definir la interfaz de agente y `FakeRunner`. `FakeRunner` reproduce guiones por ronda: editar archivos, devolver un informe o veredicto, simular coste, error o timeout, e intentar escribir siendo checker. Verificar con `pytest tests/test_fake_runner.py`.
- [x] 4.4 Implementar `ClaudeCodeRunner` según D2:
  - construye argv por rol, sin `bypassPermissions` ni `--dangerously-skip-permissions`;
  - usa `--no-session-persistence` y `--max-budget-usd`;
  - parsea el JSON de resultado (coste, uso, turnos, `is_error`) y la salida estructurada, con el respaldo de leer JSON dentro de `result`;
  - gestiona timeout y CLI ausente con un mensaje accionable.

  Verificar con `pytest tests/test_claude_runner.py` usando salidas grabadas como fixtures.
- [x] 4.5 Escribir `prompts/maker.md` y `prompts/checker.md`, adaptados del curso a Python/pytest/ruff; el checklist del checker incluye la pregunta sobre tests debilitados. Añadir los esquemas del informe del maker y del veredicto del checker, y el validador local del veredicto. Verificar con `pytest tests/test_verdict.py`, que cubre "Veredicto malformado" y "Hallazgo sin evidencia".
- [x] 4.6 Documentar en `docs/harness/loops.md` el formato de `goal.md` y la configuración de roles, y en `docs/harness/roles.md` los permisos por rol. Verificar que los ejemplos documentados validan con el parser de 4.2. Cerrar con `factory features verify <feature del grupo 4>`.

## 5. Estado externo y observabilidad (fase 2, `loop-state`)

- [x] 5.1 Implementar el directorio de ejecución:
  - `run-id` y `.factory/runs/<run-id>/` con copia de `goal.md`;
  - `state.json` con escritura atómica;
  - generación de `loop-state.md` con el formato de la plantilla del curso;
  - estado `interrupted`.

  Verificar con `pytest tests/test_state.py`, que cubre "Ejecución terminada", "Estado tras una ronda" e "Interrupción".
- [x] 5.2 Implementar el resumen acotado para la siguiente ronda: tamaño máximo configurable, con prioridad para bloqueos, mejor ronda y ronda más reciente. Verificar con `pytest tests/test_summary.py`, escenario "Ejecución larga" (15 rondas).
- [x] 5.3 Implementar `results.tsv` (solo-añadir) y `events.jsonl` (eventos de agente y de comando, con la salida truncada). Verificar con `pytest tests/test_records.py`, que cubre "Auditoría posterior" y "Diagnóstico de una ronda fallida".
- [x] 5.4 Implementar la bandeja: `.factory/inbox/<run-id>.md` con estado `pending|reviewed`, más `factory inbox list` y `factory inbox ack <run-id>`. Verificar con `pytest tests/test_inbox.py`, que cubre "Ejecución bloqueada" y "Marcar como revisada".
- [x] 5.5 Implementar `factory status`: ejecuciones recientes y activas, e indicadores de los cuatro costes silenciosos con sus umbrales. Verificar con `pytest tests/test_status.py`, que cubre "Bandeja acumulada" y "Crecimiento de tokens". Documentar los indicadores en `docs/harness/loops.md` y cerrar con `factory features verify <feature del grupo 5>`.

## 6. Motor del loop maker-checker (fase 2, `goal-loop` / `maker-checker-loop`)

- [x] 6.1 Implementar las operaciones de git y worktree:
  - preflight (exige commit en `main`; ejecuta `git worktree prune` y detecta worktrees huérfanos);
  - crear el worktree **fuera del repo**, en `worktrees_dir`, que por defecto es `../<repo>.factory-worktrees/<run-id>`, y la rama `factory/<run-id>`;
  - commit de instantánea, reset a un commit y reversión de ronda;
  - hash del árbol, archivos cambiados y diff acumulado desde el commit base;
  - eliminar el worktree conservando la rama.

  Verificar con `pytest tests/test_worktree.py`, que cubre "Repositorio sin commits", "Ejecución concurrente con trabajo humano" y que la ruta del worktree está fuera del repo principal.
- [x] 6.2 Implementar la ejecución de criterios en el worktree con timeout, puntuación y firma de fallo normalizada. Verificar con `pytest tests/test_verify.py`: una firma estable ante números o rutas distintas y una firma diferente ante errores distintos.
- [x] 6.3 Implementar el motor de ronda de D3: maker en sesión nueva, comprobación de alcance, instantánea, verificación, checker con guarda de árbol, decisión, ratchet, persistencia y feedback. Verificar con `pytest tests/test_round_engine.py` usando `FakeRunner`. Escenarios:
  - "Segunda ronda tras un fallo";
  - "El agente declara éxito pero un test falla";
  - "Modificación de ruta prohibida";
  - "El checker intenta modificar archivos";
  - "Entrada del checker" (recibe el diff acumulado);
  - "Ronda final pequeña tras rondas previas";
  - "Modelos distintos por rol";
  - "Tests pasan pero el checker rechaza";
  - "Checker aprueba pero un test falla";
  - "Corrección guiada";
  - "Ronda que empeora";
  - "Ronda que mejora o iguala".
- [x] 6.4 Implementar las condiciones de parada y los códigos de salida de D3: `completed`, `stalled`, `max_rounds`, `budget_exhausted`, `blocked` (pregunta enviada a la bandeja), `agent_error` e `interrupted` (manejador de SIGINT). Verificar con `pytest tests/test_stop_conditions.py`, que cubre "Éxito", "Sin progreso", "Presupuesto agotado", "Bloqueo humano", "CLI del agente no disponible" y "El maker intenta hacer push".
- [x] 6.5 Implementar la promoción de la feature asociada al terminar en `completed`. Usa el mecanismo de 2.2 en la rama de la ejecución, con el `run-id` en la evidencia. Verificar con `pytest tests/test_promotion.py`, escenario "Ejecución completada con feature asociada".
- [x] 6.6 Implementar `factory goal run <goal.md> [--dry-run]`. Muestra los límites efectivos, los roles y los comandos. `--dry-run` no invoca agentes ni crea ramas. Verificar con `pytest tests/test_goal_run.py`:
  - "Simulación";
  - "Objetivo completado", donde el HEAD de `main` no cambia y no hay push.
- [x] 6.7 Completar `docs/harness/loops.md`:
  - uso de `factory goal run` y códigos de salida;
  - cómo revisar una rama y la bandeja;
  - anti-patrones de L13 y los cuatro costes silenciosos;
  - la recomendación de sandbox para ejecuciones desatendidas.

  Verificar que los comandos documentados se ejecutan tal como están escritos en `--dry-run`. Cerrar con `factory features verify <feature del grupo 6>`.

## 7. Loop programado (fase 2, `scheduled-loop`)

- [x] 7.1 Implementar `factory tick <goal.md>`:
  - solo acepta `mode: monitor`;
  - verifica primero, y si todo pasa registra `noop` con coste 0;
  - si algo falla, lanza una ejecución con los límites por tick.

  Verificar con `pytest tests/test_tick.py`, que cubre "Todo en orden", "Se detecta un fallo" y "Objetivo finito programado".
- [x] 7.2 Implementar el bloqueo por objetivo: PID y marca de tiempo, resultado `skipped` y recuperación de bloqueos obsoletos. Verificar con `pytest tests/test_tick_lock.py`, que cubre "Tick solapado" y "Bloqueo obsoleto".
- [x] 7.3 Implementar:
  - la guarda `awaiting_review`;
  - el presupuesto por tick y diario (`.factory/spend/<fecha>.json`);
  - el cortacircuitos, con entrada de escalado en la bandeja y `factory tick --reset-breaker <goal>`.

  Verificar con `pytest tests/test_tick_guards.py`, que cubre "Rama sin revisar", "Presupuesto diario agotado", "Fallos repetidos" y "Restablecimiento".
- [x] 7.4 Implementar el registro de ticks por objetivo e integrarlo en `factory status`. Verificar con `pytest tests/test_tick_log.py`, escenario "Historial de vigilancia".
- [x] 7.5 Implementar `factory schedule <goal> --every <intervalo>`. Imprime la línea de cron, la plantilla de `launchd` y el comando `/loop` sin modificar el sistema. Verificar con `pytest tests/test_schedule.py`: salida esperada y ninguna invocación de `crontab` ni `launchctl`.
- [x] 7.6 Crear el objetivo de vigilancia de ejemplo `goals/vigilancia-check.md`, que ejecuta `./scripts/check.sh`, y documentar los ticks en `docs/harness/loops.md`. Verificar que `factory tick goals/vigilancia-check.md` con el repo en verde registra `noop` y coste 0. Cerrar con `factory features verify <feature del grupo 7>`.

## 8. Scaffolding para otros repositorios (fase 2, `harness-scaffolding`)

- [x] 8.1 Empaquetar las plantillas del harness como datos del paquete en `src/factory/templates/`: instrucciones, lista de features, progreso, handoff, `init.sh`, `factory.toml`, prompts y plantilla de goal, con cabecera de atribución. Verificar con `pytest tests/test_templates.py` que se cargan desde el paquete instalado.
- [x] 8.2 Implementar `factory init --target <ruta> [--commands ...] [--force]`:
  - detecta los comandos de verificación (`pyproject` → pytest/ruff, `package.json` → `npm test`, `Makefile` → `make check`);
  - lista lo creado y los marcadores pendientes;
  - sin `--force`, omite los archivos existentes.

  Verificar con `pytest tests/test_init.py`, que cubre "Repositorio sin harness", "Comandos de verificación indicados por el usuario" y "Archivo de instrucciones existente".
- [x] 8.3 Añadir un test de integración: `factory init` sobre un repo temporal seguido de `factory doctor`, que debe pasar todas las comprobaciones críticas. Documentar `factory init` y `factory doctor` en `README.md`. Verificar con `pytest tests/test_scaffold_integration.py`. Cerrar con `factory features verify <feature del grupo 8>`.

## 9. Integración y validación end-to-end

- [x] 9.1 Validación completa. Verificar que `./scripts/check.sh` termina en 0, que `factory doctor` sobre este repo pasa todas las comprobaciones críticas, que `openspec validate add-harness-loop-engine --strict` es válido y que todas las features de la fase 2 están en `passing` con evidencia.
- [ ] 9.2 **Con aprobación del usuario para el gasto** (0,50 USD o menos): ejecutar la prueba `live` opt-in (`pytest -m live`). Corre un objetivo trivial contra `claude -p` en un repo temporal y resuelve dos preguntas:
  - en qué campo devuelve el CLI la salida de `--json-schema` (pregunta abierta del diseño);
  - si el resultado JSON expone las herramientas denegadas, para registrarlas en `events.jsonl` cuando sea posible;

  además, comprueba en el worktree hermano el escenario "Instrucciones de la rama de la ejecución". Verificar que la prueba pasa y registrar la evidencia en `progress.md`.
- [x] 9.3 **Con aprobación del usuario para el gasto** (2 USD o menos): hacer dogfooding con un `factory goal run` real sobre un objetivo pequeño de este repo. Revisar la entrada de la bandeja y la rama resultante, y escribir la retrospectiva del proyecto 07 en `progress.md`: intervenciones, problemas que el checker detectó o pasó por alto, coste y límites del loop. Verificar que `main` no cambió sin decisión humana.

## Workflow follow-up

- Revisar y, si procede, integrar a mano las ramas `factory/<run-id>` generadas durante el dogfooding.
- Archivar el change con `/opsx:archive` cuando se cumplan los requisitos de revisión, y verificar que las specs quedan en `openspec/specs/`.
