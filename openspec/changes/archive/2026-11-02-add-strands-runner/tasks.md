# Tasks

> Del grupo 2 al 4, cada grupo es una feature de `feature_list.json` y se trabaja con WIP=1:
> 1. `factory features start <id>`;
> 2. las tareas del grupo;
> 3. `factory features verify <id>`;
> 4. la siguiente feature.
>
> Los tests unitarios no importan `strands`. Usan una fábrica de agentes falsa y directorios temporales. `tests/test_strands_integration.py` usa el `strands.Agent` real con un modelo falso, sin red, y se omite sin el extra. Solo los tests marcados `live` llaman a un proveedor real.

## 1. Preparación

- [x] 1.1 Añadir a `feature_list.json` las features `agent-backend-config` (27), `strands-tools` (28) y `strands-runner` (29), en `not_started`, con `evidence: []` y sus comandos `pytest` (`tests/test_agent_backend_config.py`; `tests/test_strands_tools.py`; `tests/test_strands_runner.py`). Verificar que `factory features validate` y `./scripts/check.sh` pasan.
- [x] 1.2 Añadir a `pyproject.toml` el extra `strands = ["strands-harness>=0.3.3,<0.4"]`, sin tocar las dependencias base ni la configuración de ruff o pytest. Verificar que `./init.sh` sigue en verde sin el extra y que `.venv/bin/pip install -e '.[strands]'` instala `strands-harness` 0.3.x en el `.venv` (Python 3.15).
- [x] 1.3 Consultar la referencia oficial de precios (skill `claude-api`) para los modelos por defecto de D4 y anotar las cifras, la fecha y la fuente para `pricing.py`. Verificar que cada precio tiene fuente, sin cifras de memoria.

## 2. Selección de backend (`agent-backend-config`)

- [x] 2.1 Ampliar `AgentConfig` con `backend` (`claude-code` por defecto, validado) y con la subsección `[agent.strands]` (`provider`, `models`, `prices`), y crear `agents/pricing.py` con la tabla por defecto de la tarea 1.3. Verificar con `pytest tests/test_agent_backend_config.py`, escenarios "Configuración sin backend" y "Backend desconocido", más la sobrescritura de un precio desde `factory.toml`.
- [x] 2.2 Hacer que `make_runner` elija `ClaudeCodeRunner` o `StrandsRunner` (un esqueleto que devuelve un error si falta el extra). Verificar con `pytest tests/test_agent_backend_config.py` que `goal run`, `tick` e `intake` reciben el runner del backend configurado, y que con `strands` sin el extra el error indica `pip install -e '.[strands]'` (escenario "Strands no instalado").
- [x] 2.3 Comprobar, en un directorio temporal y con un modelo falso de Strands, si `create_harness(context_manager="auto", session=False, memory=False, ...)` escribe algo en disco. Fijar el valor de `context_manager` según el resultado (pregunta abierta del diseño) y registrarlo en `design.md`. Verificar listando el directorio antes y después.
- [x] 2.4 Documentar en `docs/harness/loops.md` la sección "Backends de agentes" (selección, instalación del extra, credenciales del proveedor y vuelta atrás) y comentar la clave en el `factory.toml` del repo y en la plantilla de `factory init`. Verificar que `factory doctor` sigue en verde y que `pytest tests/test_scaffold*.py` pasa con la plantilla actualizada.

## 3. Herramientas confinadas (`strands-tools`)

- [x] 3.1 Implementar `PathPolicy` en `agents/strands_tools.py`: raíz de lectura y escritura `cwd`, raíces de solo lectura `add_dirs`, `realpath` contra enlaces simbólicos y `..`, y reglas `Read(...)`, `Edit(...)` y `Write(...)` denegadas relativas a `cwd`. Verificar con `pytest tests/test_strands_tools.py`, escenarios "Escritura fuera del worktree", "Ruta denegada por rol" y "Cerebro de solo lectura", más un enlace simbólico que sale del worktree.
- [x] 3.2 Implementar `ShellPolicy`: prefijos `Bash(<p>:*)` comparados por tokens, denegaciones, rechazo de metacaracteres y saltos de línea, y ejecución con `shell=False` en `cwd` con `command_env` y tiempo límite. Verificar con `pytest tests/test_strands_tools.py`, escenarios "Push del maker" y "Encadenamiento para eludir el prefijo", más un `git status` permitido que se ejecuta en el `cwd` de la invocación.
- [x] 3.3 Implementar las funciones de las herramientas `read`, `glob`, `grep`, `edit` y `write` sobre `PathPolicy`, con salidas acotadas (líneas numeradas y límite de resultados), y la traducción de herramientas de D6 con fallo cerrado. Verificar con `pytest tests/test_strands_tools.py`, escenarios "Herramienta sin traducción" y "Checker de solo lectura" (las herramientas por defecto del checker producen solo `read`, `glob` y `grep`) y un `Bash` permitido sin prefijo que se rechaza.

## 4. Runner de Strands (`strands-runner`)

- [x] 4.1 Implementar `StrandsRunner.run` con una fábrica de agentes inyectable. Por defecto usa `create_harness` con `builtin_tools=[]`, `builtin_plugins=[]`, `session=False`, `memory=False`, `skills=False`, `background_tasks=False`, `instructions=system_prompt`, el modelo resuelto por alias y las herramientas de la tarea 3.3. Rechazar `bypassPermissions`. Verificar con `pytest tests/test_strands_runner.py` que la fábrica recibe esas opciones y que dos invocaciones crean dos agentes distintos (escenario "Dos rondas consecutivas").
- [x] 4.2 Implementar el coste y el presupuesto de D7: uso de `invocation_context.usage` con `metrics.accumulated_usage` como respaldo, precio por modelo, `Limits(total_tokens=…)` desde `max_budget_usd` y fallo previo si el modelo no tiene precio. Verificar con `pytest tests/test_strands_runner.py`, escenario "Modelo sin precio", más el cálculo de coste con caché y la cota de tokens. Verificar también con `pytest tests/test_engine*.py` usando un runner Strands con agente falso, escenario "Presupuesto agotado".
- [x] 4.3 Implementar el tiempo límite con `cancel_signal`, la conversión de excepciones en `AgentResult(ok=False)` y la salida estructurada de D8 (mover `_structured` a un módulo común sin cambiar el comportamiento de `ClaudeCodeRunner`). Verificar con `pytest tests/test_strands_runner.py`, escenarios "Veredicto del checker" y "Excepción del proveedor", más un agente falso que se bloquea, y con `pytest tests/test_claude_code*.py` sin cambios.
- [x] 4.4 Ampliar `factory doctor` con el backend activo y los avisos de Strands (falta la dependencia o algún modelo no tiene precio), sin fallar con `claude-code`. Verificar con `pytest tests/test_doctor*.py`, escenario "Backend Strands sin precio para un rol".

## 5. Integración

- [x] 5.1 Ejecutar `./scripts/check.sh` sin el extra instalado y después con él. Verificar que termina en 0 en ambos casos.
- 5.2 *(sin casilla: fuera del alcance de este cambio por decisión del usuario (2026-11-02): no hay credenciales del proveedor ni coste autorizado; pasa a un seguimiento posterior.)* Era: Con permiso explícito del usuario y credenciales del proveedor: añadir un test `live` (`pytest -m live tests/test_strands_runner.py`) que invoque al checker de Strands sobre un diff mínimo, y ejecutar `factory goal run` con `backend = "strands"` sobre un goal pequeño. Registrar en `progress.md` el coste, los tokens, el veredicto y la comparación con Claude Code.
- [x] 5.3 Revisión independiente con el subagente `checker` sobre el diff completo y los criterios de `specs/agent-backends/spec.md`. Verificar que no quedan hallazgos `critical` ni `medium` abiertos y registrarlo en `progress.md`.

## Workflow follow-up

- Archivar `add-strands-runner` (`/opsx:archive`) cuando las tres features estén en `passing` y la revisión esté limpia. La 5.2 no bloquea el archivado.
- Seguimiento posterior: la prueba `live` (antigua 5.2), con permiso explícito y credenciales del proveedor.
- Proponer la fase 2 (`add-strands-swarm`): el partido del equipo como `strands.multiagent.Swarm`.
