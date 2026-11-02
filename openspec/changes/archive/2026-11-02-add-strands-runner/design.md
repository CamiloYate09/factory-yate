# Design

## Context

- **La costura ya existe.** El motor, `tick` e `intake` solo conocen el protocolo `AgentRunner.run(AgentRequest) -> AgentResult` (`src/factory/agents/base.py`). El adaptador concreto se elige en un único punto, `make_runner` (`src/factory/cli.py`), y los tests lo sustituyen por `FakeRunner`.
- **Las reglas de herramientas siguen la sintaxis de Claude Code.** Ejemplos: `Read`, `Bash(git diff:*)`, `Write(feature_list.json)`. `config.py` añade las denegaciones obligatorias por rol (`MANDATORY_DENIED`) y prohíbe `bypassPermissions`.
- **Lo que hace `strands-harness` 0.3.3 (Python) por defecto.** Comprobado inspeccionando el paquete instalado en un venv temporal:
  - `create_harness()` devuelve un `strands.Agent` con persistencia de sesión en `./.agent/sessions`, memoria a largo plazo, skills, el plugin `todos`/`environment` y las herramientas `shell`, `read`, `write`, `edit`, `web_*`, `programmatic_tool_caller` y `subagent`.
  - Las herramientas de archivos exigen rutas absolutas y se ejecutan con el sandbox `NotASandboxLocalEnvironment`, que no confina nada: resuelve contra `os.getcwd()` y accede a todo el host.
  - El `shell` no tiene restricciones.
  - No hay herramientas `glob` ni `grep`.
- **Strands no informa del coste en USD.** El `AgentResult` de Strands expone `metrics.accumulated_usage` (tokens del agente) e `invocation_context.usage` (tokens de toda la petición, incluidas las llamadas auxiliares). `Limits` solo admite `turns`, `output_tokens`, `total_tokens` y `structured_output_attempts`.
- **Entorno.** El `.venv` del proyecto es Python 3.15, compatible con `strands-harness`. Hoy no hay credenciales de Anthropic ni de AWS en el entorno de la sesión.

## Goals / Non-Goals

**Goals:**
- Que `StrandsRunner` cumpla las mismas garantías que `ClaudeCodeRunner` (ver `specs/agent-backends/spec.md`) y que sea intercambiable sin tocar el motor.
- Que todo se pueda probar sin red: el runner recibe una fábrica de agentes inyectable.

**Non-Goals:**
- Usar las herramientas integradas de archivos y shell de `strands-harness`. Se sustituyen por las nuestras (D2).
- Gestionar credenciales: son del proveedor (variables de entorno estándar de Anthropic o AWS).
- El `Swarm` del equipo (fase 2).

## Decisions

### D1. Backend detrás de `AgentRunner`, con `claude-code` por defecto
`AgentConfig` gana `backend: str = "claude-code"` y una subsección `strands` (D4). `make_runner` devuelve `ClaudeCodeRunner` o `StrandsRunner`.
- **Alternativa descartada:** sustituir directamente `ClaudeCodeRunner`. Rompería la evidencia `live` existente, las plantillas de `factory init` y los hooks del panel, que dependen de Claude Code, y obligaría a migrar todo de golpe.

### D2. Herramientas propias confinadas, sin las integradas
Se llama a `create_harness(builtin_tools=[], builtin_plugins=[], session=False, memory=False, skills=False, background_tasks=False, mcp_servers=None, tools=[...])` con herramientas propias (`@strands.tool`): `read`, `glob`, `grep`, `edit`, `write` y `shell`. Todas pasan por una `PathPolicy` (D3), y el shell por un `ShellPolicy` (D5).
- Conservamos de `create_harness` lo que aporta valor: el prompt de sistema afinado, `instructions` (con semántica de añadir, como `--append-system-prompt`), la resolución de `"provider/model"`, `effort` y el caché.
- **Alternativa A, descartada:** un `Sandbox` propio con las herramientas integradas. No aporta `glob` ni `grep` (el checker los necesita), el `shell` integrado sigue sin restricciones y la API de `Sandbox` es más amplia y cambiante que seis funciones nuestras.
- **Alternativa B, descartada:** `strands.Agent` sin el harness. Perderíamos el prompt de sistema y la gestión de contexto sin ganar control, porque las herramientas ya las ponemos nosotros.
- `context_manager=ContextManager(stash=False)`: las estrategias de `"auto"`, sin almacén ni la herramienta `retrieve_context`.
  - `"auto"` añade `retrieve_context`, que busca con una expresión regular del modelo dentro del proceso. Un patrón costoso congelaría el tiempo límite (D3b).
  - Coste aceptado: los resultados de más de unos 1.500 tokens se recortan a una vista previa del principio y del final, con el marcador `[... N chars elided ...]`. Un archivo se puede volver a leer por tramos con `read`; la salida de `shell`, `grep` o `glob` no se recupera, y el agente tiene que acotar el comando. Su efecto en la calidad se medirá en la prueba `live`, aplazada a un seguimiento posterior.
  - La tarea 2.3 comprobó el 2026-11-01, con strands-harness 0.3.3, un modelo falso y `session`, `memory` y `skills` desactivados, que `agent.storage` es `None` y que no se escribe nada ni en el `cwd` ni en `~/.agent`. `tests/test_strands_integration.py` lo mantiene y fija la lista exacta de herramientas.
- `callback_handler=None`. Por defecto Strands imprime en stdout el texto que va recibiendo del modelo, lo que ensuciaría la salida de `factory`, que también se lee como JSON.
- El uso viene en `invocation_context.usage` con claves camelCase: `inputTokens`, `outputTokens`, `cacheReadInputTokens`, `cacheWriteInputTokens` y `turns_taken`.

### D3. `PathPolicy`: confinamiento por `realpath`
Las raíces son:
- `cwd`: lectura y escritura;
- `add_dirs`: solo lectura.

Toda ruta (relativa a `cwd` o absoluta) se normaliza con `os.path.realpath` y debe quedar dentro de una raíz. Las reglas `Read(...)`, `Edit(...)` y `Write(...)` denegadas se interpretan como rutas o globs relativos a `cwd`.
- **Alternativa descartada:** `chdir` del proceso. No es seguro con hilos y no confina las rutas absolutas.

### D3b. Patrones del modelo en un proceso hijo
`re` no suelta el GIL mientras busca. Un patrón costoso, como `(a+)+$`, evaluado dentro del proceso congela también el hilo principal, así que no vencen el tiempo límite ni Ctrl-C. Se reprodujo: con `timeout_s=1`, no volvió en 20 s.
- `grep` y `glob` evalúan los patrones del modelo en un proceso hijo (`python -I -S`, sin entorno) con tiempo límite propio de 30 s y la misma señal de cancelación. Si se detiene, el agente recibe un error y sigue.
- `PathPolicy` sigue resolviendo los permisos en el proceso: sus patrones vienen de la configuración, no del modelo.
- **Alternativa descartada:** recortar las líneas antes de buscar. Reduce el caso polinómico, no el exponencial.

### D4. Modelos y precios en `factory.toml`
```toml
[agent.strands]
provider = "anthropic"            # prefijo para los alias
[agent.strands.models]            # alias del rol -> id de Strands
sonnet = "anthropic/claude-sonnet-5-5"
opus = "anthropic/claude-opus-5-5"
haiku = "anthropic/claude-haiku-5-5"
[agent.strands.prices."anthropic/claude-sonnet-5-5"]   # USD por millón de tokens
input = 0.0
output = 0.0
cache_read = 0.0
cache_write = 0.0
```
`pricing.py` lleva una tabla por defecto con fecha y fuente, y `factory.toml` la puede sobrescribir. Los precios por defecto se verifican en la implementación con la referencia oficial, nunca de memoria (tarea 1.3). Un modelo sin precio hace fallar la invocación antes de llamar al modelo, y `doctor` lo avisa.
- **Alternativa descartada:** coste 0. Desactivaría en silencio `max_budget_usd`, el presupuesto diario y los cortacircuitos (`engine.py`, `tick.py`).

**Precios por defecto (tarea 1.3).** Son USD por millón de tokens de la API de Anthropic, según la referencia oficial: skill `claude-api`, tabla en caché del 2026-10-06, fuente <https://platform.claude.com/docs/en/about-claude/pricing>. La escritura en caché es la de TTL de 5 minutos: 1,25 × la entrada, según `prompt-caching.md` de la misma skill.

| Modelo | entrada | salida | lectura de caché | escritura de caché (5 min) |
|---|---|---|---|---|
| `claude-opus-5-5` | 4.00 | 20.00 | 0.20 | 5.00 |
| `claude-sonnet-5-5` | 2.00 | 10.00 | 0.20 | 2.50 |
| `claude-haiku-5-5` | 0.50 | 2.50 | 0.05 | 0.625 |

Haiku 5.5 tiene dos tramos: 0.10/0.50 para prompts de hasta 100K tokens y 0.50/2.50 por encima. Strands da el uso agregado de todos los turnos, no el tamaño de cada petición, así que por defecto se aplica el tramo alto. Es conservador: nunca subestima el presupuesto. Quien quiera el tramo bajo lo sobrescribe en `factory.toml`. Bedrock y Vertex tienen precios propios y no llevan valores por defecto, así que un modelo `bedrock/…` exige declarar su precio.

### D5. `ShellPolicy`: prefijos y nada de metacaracteres
Solo se crea la herramienta `shell` si el rol permite al menos un `Bash(<prefijo>:*)` y `Bash` no está denegado entero.
- El comando se tokeniza con `shlex.split`. Se rechaza si contiene `; & | < > ` + "`" + ` $(` o saltos de línea.
- Debe empezar por un prefijo permitido, comparado por tokens, y no coincidir con ninguno denegado.
- Se ejecuta con `subprocess.Popen(argv, shell=False, cwd=request.cwd, start_new_session=True)`, con el entorno de `command_env(cwd)` sin las credenciales del proveedor. Si se activa la señal de cancelación de la invocación (D7) o se agota su tiempo, se mata el grupo de procesos.
- Una regla `Bash(...)` que `shlex` no puede interpretar es intraducible, tanto si está permitida como si está denegada (fallo cerrado).
- `Bash` permitido sin prefijo se considera intraducible (fallo cerrado), porque daría un shell sin restricciones.

### D6. Traducción de herramientas con fallo cerrado
| Claude Code | Strands (propia) |
|---|---|
| `Read` | `read` |
| `Glob` | `glob` |
| `Grep` | `grep` |
| `Edit` / `MultiEdit` | `edit` |
| `Write` | `write` |
| `Bash(<p>:*)` | `shell` con el prefijo `<p>` |

Cualquier otra herramienta permitida (`NotebookEdit`, `WebFetch`, `Task`, `mcp__*`, `Bash` a secas…) produce `AgentResult(ok=False)` sin coste y sin llamar al modelo. Una herramienta denegada sin patrón quita la herramienta. Con patrón, la regla pasa a la `PathPolicy` o a la `ShellPolicy`.

### D7. Presupuesto, tiempo y resultado
- **Presupuesto por llamada.** `max_budget_usd` se convierte en `Limits(total_tokens=⌊presupuesto / precio_máximo × 10⁶⌋)`, donde el precio máximo es el mayor de entrada, salida, lectura de caché y escritura en caché.
  - Es un **límite blando**: Strands lo comprueba antes de cada turno, así que el último turno puede pasarse. Las llamadas auxiliares, como el resumen del gestor de contexto, no tienen límites.
  - El presupuesto de la ejecución se descuenta con el coste calculado y el loop para por presupuesto como con Claude Code. Ese coste es exacto para los turnos terminados y estimado para un turno cortado por tiempo.
- **Tiempo.** La llamada corre en un hilo con `cancel_signal=threading.Event()`. La misma señal llega al shell. Al agotarse `timeout_s`:
  - se activa la señal, que mata el comando en curso;
  - se esperan hasta 5 s y se devuelve `tiempo agotado`, con el mismo mensaje que hoy;
  - el hilo daemon solo puede seguir esperando al modelo, y Strands lo corta en el siguiente fragmento.
- **Coste.** Se calcula con `invocation_context.usage`, que incluye las llamadas auxiliares, o con `metrics.accumulated_usage` si falta. Los tokens de entrada suman los de entrada, la lectura de caché y la escritura en caché, como en `parse_result`. `num_turns` es `metrics.cycle_count`.
- **Interrupción.** Un `KeyboardInterrupt` durante la espera activa la misma señal antes de propagarse: el comando del agente tiene su propia sesión y Ctrl-C no le llega, y el motor restaura el worktree justo después. Límite aceptado: `SIGTERM` y `SIGHUP` matan a `factory` sin pasar por aquí, y el comando o la búsqueda en curso quedan huérfanos hasta que terminen, porque el tiempo límite lo aplica el proceso padre. Una búsqueda con un patrón exponencial podría no terminar en mucho tiempo.
- **Errores y coste parcial.** Cualquier excepción o tiempo agotado se devuelve como `AgentResult(ok=False, error=...)`. Strands inicializa el uso a ceros y registra los tokens de un turno al final del stream, de modo que un turno cortado no consta. Por eso:
  - **Excepción:** cuesta lo registrado en `agent.event_loop_metrics.accumulated_usage`. Con un error de credenciales es 0, y se aplica la regla de fallos consecutivos del loop. Límites aceptados: si un error corta un stream a medias, ese turno no se cuenta; y sin resultado no se cuentan las llamadas auxiliares, como el resumen del gestor de contexto.
  - **Tiempo agotado:** al cancelar, Strands puede devolver un resultado con `stop_reason="cancelled"` en vez de lanzar una excepción, y su uso tampoco incluye el turno cortado. Salvo que el agente terminara con normalidad durante el margen de gracia, cuesta lo registrado más una estimación del turno en curso: el mayor entre `latest_context_size` y el tamaño del prompt (3 caracteres por token), a precio de entrada, más 4.096 tokens de salida, con el presupuesto restante de la llamada como tope. Es una estimación: el proveedor puede cobrar más o menos. Se descartó cargar toda la cota porque, siendo la cota el presupuesto restante del loop, cada tiempo agotado pararía la ejecución como `budget_exhausted` en lugar de seguir la regla de errores consecutivos.
  - Si la fábrica falló antes de crear el agente, no hubo llamadas y el coste es 0.
  - Un resultado correcto sin ningún token (con precio mayor que 0) se trata como error: sin uso no hay coste (D4).

### D8. Salida estructurada por texto y validación existente
El esquema JSON va en el prompt con la instrucción de responder solo con un objeto. Se extrae con `_structured` (se mueve a un módulo común) y se valida con `schemas.py`, como hoy.
- **Alternativa descartada:** `structured_output_model`. Exige generar modelos pydantic dinámicos a partir del esquema, lo que añade otra fuente de verdad. Queda para el futuro si la extracción por texto falla en la práctica.

### D9. Import perezoso y extra opcional
`strands`/`strands_harness` solo se importan dentro de `StrandsRunner.run` (o de la fábrica por defecto). `pyproject.toml` añade `[project.optional-dependencies] strands = ["strands-harness[anthropic]>=0.3.3,<0.4"]` (el extra `anthropic` trae el SDK del proveedor por defecto). `init.sh`, `check.sh`, la configuración de ruff y la de pytest no cambian. Los tests unitarios no importan Strands.

### Fase 2 (orientativa, fuera de este cambio)
El partido del equipo como `strands.multiagent.Swarm`: un nodo por jugador de `.claude/agents/` (su frontmatter da el nombre, la descripción, las herramientas y el modelo), con el técnico como `entry_point`. Reutilizaría D2–D7 para cada nodo. El motor maker→checker sigue siendo determinista en Python y no pasa a usar handoffs.

## Risks / Trade-offs

- **[Riesgo] Las herramientas propias son más pobres que las de Claude Code**, lo que puede dar peor calidad del maker. → Mitigación: el backend es opcional, y la comparación se hace con un goal real en la tarea 6.2 antes de recomendarlo.
- **[Riesgo] La API de `strands-harness` 0.x cambia.** → Mitigación: versión acotada `<0.4` y un único módulo de adaptación. `tests/test_strands_integration.py` (el `Agent` real con un modelo falso) detecta las roturas; la prueba `live` queda para un seguimiento posterior.
- **[Riesgo] La cota de tokens por presupuesto es blanda** (D7): una llamada puede pasarse en su último turno. → Mitigación: el coste real se contabiliza, y el presupuesto de la ejecución y el diario paran el loop.
- **[Riesgo] Los comandos permitidos salen del confinamiento con sus argumentos** (`git diff --output=…`, `python -m pytest` ejecuta código del repo). Es paridad con Claude Code, y `PathPolicy` solo confina las herramientas de archivos. → Mitigación: prefijos estrechos, sin credenciales en el entorno del shell y documentado en `loops.md`.
- **[Riesgo] Sistemas de archivos que no distinguen mayúsculas** (APFS, NTFS). → Las denegaciones (reglas, cerebros y `.git`) se comparan sin distinguir mayúsculas. Denegar de más es el lado seguro.
- **[Riesgo] La lista negra de metacaracteres del shell** puede bloquear comandos legítimos (por ejemplo, `pytest -k "a or b"` va entre comillas y `shlex` lo acepta, pero `>` no). → Mitigación: preferir rechazar a permitir. Se documenta.
- **[Trade-off] El hook de revisiones del panel no ve las invocaciones de Strands** porque no son sesiones de Claude Code. → Los eventos y los tokens siguen en `events.jsonl` y `results.tsv`, que el panel ya lee.

## Migration Plan

1. Mergear con `backend = "claude-code"` por defecto: no cambia nada.
2. Para probarlo: `pip install -e '.[strands]'`, credenciales del proveedor y `backend = "strands"` en `factory.toml`. Después, `factory goal run --dry-run` y un goal pequeño.
3. Para volver atrás: borrar la línea `backend` o poner `claude-code`.

## Open Questions

- El alias de modelo por defecto para Bedrock (`bedrock/global.anthropic.…`) solo se añade si el usuario elige Bedrock como proveedor.
