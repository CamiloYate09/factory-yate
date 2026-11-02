# Proposal

## Why

Hoy todos los agentes de factory-yate (maker, checker e intake) se ejecutan con un único adaptador: `ClaudeCodeRunner`, que lanza `claude -p` como subproceso. Queremos construir los agentes en Python con **Strands** (`strands-harness`, el equivalente Python de `@strands-agents/harness` 0.3.3, sobre `strands-agents` 1.63). Así tenemos el bucle del modelo, las herramientas y los proveedores (Bedrock, Anthropic, OpenAI…) dentro del propio proceso, y queda abierto el camino a patrones multiagente como `Swarm`.

El motor ya tiene la costura adecuada: el protocolo `AgentRunner.run(AgentRequest) -> AgentResult`. El riesgo de cambiar de backend no está en la interfaz, sino en las garantías que hoy da el CLI de Claude Code y que Strands **no** da por defecto:

- las herramientas de Strands se ejecutan sin preguntar y sobre todo el host;
- Strands persiste sesiones y memoria en `./.agent/`;
- Strands no informa del coste en USD, solo de los tokens.

Si no se cubren, el loop perdería el aislamiento maker/checker, los permisos mínimos y el presupuesto.

## What Changes

**Backend seleccionable (fase 1)**
- Nueva clave `[agent] backend = "claude-code" | "strands"` en `factory.toml`. El valor por defecto sigue siendo `claude-code`, así que el comportamiento actual no cambia y los dos backends conviven.
- Nueva sección `[agent.strands]` con el proveedor y el mapeo de alias de modelo (`sonnet`, `opus`, `haiku`) a identificadores de Strands (`anthropic/…` o `bedrock/…`), además de una tabla de precios por modelo.
- `make_runner` elige el adaptador según `backend`.

**`StrandsRunner` (fase 1)**
- Implementa `AgentRunner` con `strands_harness.create_harness`.
- Aislamiento obligatorio: sin sesión, memoria, skills, `subagent` ni tareas en segundo plano. Cada invocación es un agente nuevo, igual que `--no-session-persistence`.
- Permisos sin omisión:
  - `allowed_tools` y `denied_tools` (sintaxis de Claude Code) se traducen a un conjunto fijo de herramientas;
  - un nombre que no se pueda traducir hace fallar la invocación (fallo cerrado);
  - el shell solo admite los prefijos `Bash(<prefijo>:*)` permitidos;
  - las acciones de publicación siguen denegadas;
  - `bypassPermissions` sigue prohibido.
- Confinamiento de rutas: las herramientas de archivos solo actúan dentro de `request.cwd`, y en solo lectura dentro de `add_dirs`. Las rutas denegadas por rol (por ejemplo, `Write(feature_list.json)`) se rechazan.
- Coste: se calcula a partir de los tokens con la tabla de precios. Si el modelo no tiene precio, la invocación falla con un error explícito, para no desactivar en silencio el presupuesto ni los cortacircuitos.
- Salida estructurada: se reutiliza la extracción y la validación de esquemas actuales (`_structured`, `schemas.py`).
- `strands` se importa de forma perezosa. Queda como extra opcional `factory-yate[strands]`, de modo que `./init.sh` y `./scripts/check.sh` siguen funcionando sin él.
- `factory doctor` informa del backend activo y, con `strands`, de si la dependencia y las credenciales del proveedor están disponibles.

**Fuera de alcance (fase 2, cambio posterior)**
- Partido del equipo ideal como `strands.multiagent.Swarm`, con los jugadores de `.claude/agents/`.
- Retirar `ClaudeCodeRunner` o cambiar el backend por defecto.
- Herramientas web, MCP, `programmatic_tool_caller` e intervenciones `ask` o `smart` de Strands.
- Usar el paquete npm `@strands-agents/harness`: el proyecto es Python y usa `strands-harness`.

## Capabilities

### New Capabilities
- `agent-backends`: selección del backend que ejecuta a los agentes de los loops y las garantías que cualquier backend debe cumplir (sesión nueva, permisos traducidos con fallo cerrado, confinamiento de rutas, coste contabilizado y salida estructurada), con Strands como segundo backend.

### Modified Capabilities
<!-- Ninguna: los requisitos de maker-checker-loop (permisos mínimos, checker de solo lectura,
     fallos de invocación) se mantienen tal cual y el nuevo backend debe cumplirlos. -->

## Impact

- Código:
  - `src/factory/agents/`: nuevos `strands.py` (runner), `strands_tools.py` (herramientas y sandbox confinados) y `pricing.py`;
  - `src/factory/config.py` (`AgentConfig`);
  - `src/factory/cli.py` (`make_runner`);
  - `src/factory/doctor.py`;
  - plantillas de `factory init` (`factory.toml`).
- Dependencias: extra opcional `strands = ["strands-harness>=0.3.3,<0.4"]` en `pyproject.toml`. No cambian las dependencias base ni la configuración de ruff o pytest.
- Tests: unitarios con un agente inyectado y sin red, más un test `live` opcional.
- Documentación: `docs/harness/loops.md` (sección de backends) y `factory.toml` comentado.
- Repo: el `package.json`, el `package-lock.json` y el `node_modules/` sin seguimiento de la raíz no son necesarios para este cambio. Lo que se haga con ellos lo decide el usuario.
