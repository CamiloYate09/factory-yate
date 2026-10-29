# Spec Delta

## Purpose

Hace visibles en tiempo real las revisiones de diffs y ramas que hacen el árbitro (`checker`) y los jugadores revisores. Los hooks de Claude Code registran cuándo empieza y acaba cada revisión y con qué veredicto, y el feed resultante se une con las revisiones del checker de los loops.

## ADDED Requirements

### Requirement: Registro de eventos del hook
`factory hook` SHALL leer de stdin el JSON de un hook de Claude Code y añadir una línea JSON a `.factory/hooks/events.jsonl` del repositorio principal, aunque la sesión esté en un worktree. Cada línea MUST incluir la marca de tiempo, el evento, la sesión y los identificadores de herramienta y de agente disponibles, y escribirse con una sola operación de añadido.

#### Scenario: Hook desde un worktree
- **WHEN** el hook se ejecuta con el directorio de trabajo en un worktree del repo
- **THEN** la línea se añade al `.factory/hooks/events.jsonl` del repo principal

### Requirement: El hook nunca bloquea
`factory hook` SHALL terminar siempre con código 0 y sin escribir en stdout, aunque reciba una entrada vacía, JSON inválido o un evento desconocido, o no pueda escribir el registro. Los errores MUST ir a stderr.

#### Scenario: Entrada inválida
- **WHEN** el hook recibe `no es json` por stdin
- **THEN** termina con código 0, stdout queda vacío y no se añade ninguna línea

#### Scenario: Registro no escribible
- **WHEN** `.factory/hooks/` no se puede crear
- **THEN** el hook termina con código 0 e informa del problema en stderr

### Requirement: Inicio de una revisión
Cuando el hook recibe el lanzamiento de un subagente (`PreToolUse` de la herramienta `Agent` o `Task`), SHALL registrar el tipo de subagente, su descripción y el id de la herramienta. El evento MUST marcarse como revisión si el tipo es `checker` o un agente de `.claude/agents/` con `tipo: revisor`. El prompt del subagente no se registra.

#### Scenario: Lanzamiento del checker
- **WHEN** la sesión lanza `Agent` con `subagent_type: checker` y la descripción "Revisar panel"
- **THEN** se registra un inicio de revisión del `checker` con esa descripción

#### Scenario: Subagente que no revisa
- **WHEN** la sesión lanza `Agent` con `subagent_type: Explore`
- **THEN** se registra un lanzamiento que no cuenta como revisión

### Requirement: Fin de una revisión
Cuando el hook recibe el fin de un subagente (`SubagentStop`), SHALL leer la última respuesta del subagente desde su transcripción y registrar el veredicto (`pass`, `pass_with_minor` o `fail`), el recuento de hallazgos por severidad y un extracto de como mucho 4.000 caracteres. Si no hay veredicto reconocible, MUST registrarlo como `sin_veredicto`.

#### Scenario: Checker con un hallazgo medio
- **WHEN** termina un `checker` cuya última respuesta contiene "## Veredicto ❌ fail" y un hallazgo `[medium]`
- **THEN** se registra el fin de la revisión con veredicto `fail` y un hallazgo `medium`

#### Scenario: Respuesta sin veredicto
- **WHEN** termina un revisor cuya última respuesta no contiene ningún veredicto
- **THEN** se registra el fin con veredicto `sin_veredicto`

### Requirement: Feed de revisiones
El sistema SHALL construir un feed de revisiones ordenado de la más reciente a la más antigua. MUST unir el inicio y el fin de cada revisión de subagente en una sola entrada (en curso o terminada, con su duración) e incluir los veredictos del checker de cada ronda de los loops de factory.

#### Scenario: Revisión en curso
- **WHEN** hay un inicio de revisión sin su fin
- **THEN** el feed muestra esa revisión como `en_curso` con el tiempo transcurrido

#### Scenario: Revisión de un loop
- **WHEN** la ronda 2 de una ejecución tiene `checker_verdict: pass_with_minor`
- **THEN** el feed incluye esa revisión con origen `loop`, la ejecución y la ronda

### Requirement: Hooks del proyecto
El repositorio SHALL declarar en `.claude/settings.json` el hook del panel para `PreToolUse` (matcher `Agent|Task`) y `SubagentStop`. El comando MUST localizar el `factory` del repo principal también desde un worktree y terminar en 0 si no lo encuentra.

#### Scenario: Worktree sin entorno virtual
- **WHEN** una sesión en `.claude/worktrees/agent-x` lanza un subagente y el worktree no tiene `.venv`
- **THEN** el hook usa el `factory` del repo principal y, si tampoco existe, termina en 0 sin registrar nada
