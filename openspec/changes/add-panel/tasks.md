# Tasks

> Del grupo 2 al 4, cada grupo es una feature de `feature_list.json` y se trabaja con WIP=1:
> 1. `factory features start <id>`;
> 2. las tareas del grupo;
> 3. `factory features verify <id>`;
> 4. la siguiente feature.
>
> Los tests usan directorios temporales y fixtures, nunca `~/.claude` ni el `.factory/` real.

## 1. Preparación

- [x] 1.1 Añadir a `feature_list.json` las features `token-usage` (24), `review-hooks` (25) y `observability-panel` (26), en `not_started`, con `evidence: []` y sus comandos `pytest` (`tests/test_panel_tokens.py`; `tests/test_panel_hooks.py tests/test_panel_reviews.py`; `tests/test_panel_tasks.py tests/test_panel_server.py`). Crear el esbozo de `docs/harness/panel.md` y su enlace en `AGENTS.md`. Verificar que `factory features validate` y `./scripts/check.sh` pasan.

## 2. Consumo de tokens (`token-usage`)

- [x] 2.1 Crear `src/factory/panel/` (`PanelError` y la resolución del repo principal por `--git-common-dir`). Implementar en `tokens.py` el consumo de los loops desde `events.jsonl`, agrupado por ejecución, rol y modelo. Verificar con `pytest tests/test_panel_tokens.py`, escenarios "Ejecución con maker y checker" y "Línea corrupta", más un test de resolución desde un worktree.
- [x] 2.2 Implementar el descubrimiento de transcripciones (slug del repo y `--claude-worktrees-*`, `--projects-dir` y `$CLAUDE_CONFIG_DIR`), la deduplicación por id de mensaje, el desglose por día, modelo, tipo de agente (`meta.json`) y sesión, y la proporción de caché. Verificar con `pytest tests/test_panel_tokens.py`, escenarios "Sesión en un worktree del equipo", "Worktree de un loop", "Mensaje repetido por bloques", "Subagente checker", "Sesión interactiva" y "Mensaje con un secreto".
- [x] 2.3 Implementar la caché incremental por archivo: lee solo lo añadido y relee si el archivo encoge. Verificar con `pytest tests/test_panel_tokens.py`: un archivo que crece suma solo las filas nuevas, y uno truncado se relee sin contar de más.
- [x] 2.4 Medir con los datos reales, sin coste de API, el tiempo de una agregación completa y de un refresco incremental, y comprobar a mano que los totales de una transcripción coinciden con un recuento independiente por `message.id`. Registrar las cifras en `docs/harness/panel.md` (sección de tokens) y en `progress.md`.

## 3. Revisiones con hooks (`review-hooks`)

- [ ] 3.1 Implementar `panel/hooks.py` y el subcomando `factory hook`: normalizar `PreToolUse` (`Agent`/`Task`) y `SubagentStop`, resolver el repo principal desde un worktree y añadir la línea con `flock` y un solo `write`, siempre con salida 0 y sin stdout. Verificar con `pytest tests/test_panel_hooks.py`, escenarios "Hook desde un worktree", "Entrada inválida", "Registro no escribible", "Lanzamiento del checker" y "Subagente que no revisa", más un test de 8 procesos concurrentes sin líneas mezcladas y otro que comprueba que el `prompt` no se registra.
- [x] 3.2 Implementar la lectura de la última respuesta del subagente (`agent_transcript_path` o la ruta derivada), la extracción del veredicto y las severidades y la detección de revisores (`checker` o `tipo: revisor` en `.claude/agents/`). Verificar con `pytest tests/test_panel_hooks.py`, escenarios "Checker con un hallazgo medio" y "Respuesta sin veredicto", más un formato de jugador (`## Jugador: qa (#2)`) y un extracto recortado a 4.000 caracteres.
- [x] 3.3 Implementar `panel/reviews.py`: unir inicio y fin (por `tool_use_id` o por el último inicio abierto de la misma sesión y tipo), las revisiones `en_curso` y las de los loops desde `state.json`, ordenadas y limitadas. Verificar con `pytest tests/test_panel_reviews.py`, escenarios "Revisión en curso" y "Revisión de un loop", más un fin sin inicio.
- [x] 3.4 Crear `.claude/hooks/panel-hook.sh` y registrar el hook en `.claude/settings.json` (`PreToolUse` con matcher `Agent|Task` y `SubagentStop`, `timeout: 10`), cargando antes la skill `update-config`. Verificar con `pytest tests/test_panel_hooks.py`:
  - escenario "Worktree sin entorno virtual": el script termina en 0 sin `factory` y con un `factory` falso del repo principal le pasa stdin;
  - `settings.json` es JSON válido y apunta al script.

  Documentar los hooks en `docs/harness/panel.md`.
- [x] 3.5 Medir la latencia del hook con un payload real de ejemplo (`time`, 10 repeticiones). Si supera unos 300 ms, hacer que el script llame a `python -m factory.panel.hooks` y volver a medir. Registrar la cifra en `docs/harness/panel.md`.

## 4. Panel (`observability-panel`)

- [ ] 4.1 Implementar `panel/tasks.py`:
  - features con la última evidencia;
  - grupos de `tasks.md` de los cambios activos (sin `archive/`), enlazados por `` `id` ``;
  - ejecuciones con ronda, criterios, veredicto, coste y si siguen vivas;
  - bandeja pendiente.

  Verificar con `pytest tests/test_panel_tasks.py`, escenarios "Grupo enlazado" y "Ejecución huérfana", más un cambio archivado que no aparece.
- [ ] 4.2 Implementar `panel/snapshot.py` y `factory panel --json`, con `warnings` para archivos ilegibles. Verificar con `pytest tests/test_panel_tasks.py`, escenarios "Repo sin ejecuciones" y "Lista de features corrupta".
- [ ] 4.3 Implementar `panel/server.py`: `/`, `/api/snapshot`, cabecera `Host`, 405 y cabeceras de seguridad (D8). Verificar con `pytest tests/test_panel_server.py`, con un servidor real en un puerto libre y escenarios "Página principal", "Host ajeno", "Escritura" e "Instantánea sin efectos".
- [ ] 4.4 Implementar el vigilante y `/api/stream` (SSE, `change` por sección y `: ping`). Verificar con `pytest tests/test_panel_server.py`, escenarios "Revisión que termina" y "Feature promovida", con un tiempo máximo para no colgar la suite.
- [ ] 4.5 Escribir `src/factory/panel/static/index.html` aplicando antes la skill `dataviz`. Debe tener tres pestañas (Tokens, Revisiones y Tareas), detalle por feature, tema claro y oscuro, ancho de móvil, datos insertados solo con `textContent` y un indicador del stream. Verificar con `pytest tests/test_panel_server.py`:
  - escenario "Sin recursos externos";
  - la página no usa `innerHTML`.

  Verificar también con `pip wheel` que la página entra en el wheel.
- [ ] 4.6 Completar `docs/harness/panel.md` (uso, fuentes, privacidad, seguridad, tiempo real y límites) y añadir el panel al README. Verificar que los comandos documentados funcionan tal como están escritos: `factory panel --json | python -m json.tool` y `factory panel --port <libre>` con `curl` a `/api/snapshot`.

## 5. Integración

- [ ] 5.1 Ejecutar `./scripts/check.sh` (código 0) y `openspec validate add-panel --strict` (válido). Ejecutar `factory features verify` de `token-usage`, `review-hooks` y `observability-panel`, una a una (WIP=1), hasta `passing`.
- [ ] 5.2 Captura real sin coste extra: con el hook instalado, la revisión independiente del `checker` de este cambio debe dejar en `.factory/hooks/events.jsonl` un inicio y un fin reales. Compararlos con los fixtures de `tests/test_panel_hooks.py`; si la forma difiere, ajustar los fixtures y el código y repetir 5.1. Registrar los campos observados en `design.md` (Open Questions) y en `progress.md`.
- [ ] 5.3 Prueba de humo con los datos reales: `factory panel --open`. Comprobar que se ven los tokens de las sesiones y los loops, la revisión del paso 5.2 y el avance de `add-panel` y `add-equipo-ideal`, y que una revisión nueva aparece sin recargar. Registrarlo en `progress.md`.

## Workflow follow-up

- Corregir los hallazgos `critical` y `medium` del `checker` y volver a pedir revisión hasta que no quede ninguno abierto.
- Commitear con pathspec explícito y avisar a la sesión de `add-equipo-ideal` antes de integrar. Proponerle que proteja `.claude/settings.json` y `.claude/hooks/**` dentro de su D7.
- Archivar `add-panel` con `/opsx:archive` y sincronizar las specs.
