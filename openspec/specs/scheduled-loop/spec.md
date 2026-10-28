# scheduled-loop Specification

## Purpose

Permite vigilar el repositorio o un flujo de trabajo de forma periódica: tests, lint, dependencias, documentación. Cada ejecución es idempotente y verifica primero, sin coste. Solo cuando la verificación detecta un problema se invoca a un agente, con límites estrictos.

## Requirements

### Requirement: Tick con verificación previa sin coste
`factory tick <goal.md>` SHALL ejecutar primero los comandos de aceptación del objetivo, sin invocar ningún agente. Si todos pasan, MUST registrar el tick como `noop` y terminar con código cero y coste cero.

#### Scenario: Todo en orden
- **WHEN** se ejecuta un tick y todos los comandos de aceptación pasan
- **THEN** no se invoca ningún agente, el tick se registra como `noop` y el comando termina con código cero

#### Scenario: Se detecta un fallo
- **WHEN** se ejecuta un tick y algún comando de aceptación falla
- **THEN** se lanza una ejecución del loop de objetivo con los límites por tick y el tick registra el identificador de esa ejecución

### Requirement: Solo objetivos de vigilancia
`factory tick` SHALL aceptar solo objetivos marcados como de vigilancia en sus metadatos. Un objetivo finito MUST rechazarse con un mensaje que recomiende `factory goal run`.

#### Scenario: Objetivo finito programado
- **WHEN** se ejecuta `factory tick` con un `goal.md` que no está marcado como de vigilancia
- **THEN** el comando termina con código distinto de cero, sin invocar agentes, e indica que se use `factory goal run`

### Requirement: Exclusión mutua entre ticks
Para un mismo objetivo, el sistema SHALL permitir como máximo un tick en curso. Un tick que encuentra otro en curso MUST registrarse como `skipped` y terminar sin efectos. Un bloqueo cuyo proceso ya no existe, o que superó la duración máxima configurada, MUST considerarse obsoleto y recuperarse.

#### Scenario: Tick solapado
- **WHEN** se dispara un tick mientras el anterior del mismo objetivo sigue en ejecución
- **THEN** el nuevo tick se registra como `skipped` y no invoca agentes

#### Scenario: Bloqueo obsoleto
- **WHEN** existe un bloqueo cuyo proceso propietario ya no está en ejecución
- **THEN** el siguiente tick recupera el bloqueo, lo registra y continúa normalmente

### Requirement: No duplicar trabajo pendiente de revisión
Si una ejecución previa lanzada por un tick del mismo objetivo tiene una entrada pendiente en la bandeja de revisión humana, un tick nuevo SHALL NOT lanzar otra ejecución con agente. MUST registrarse como `awaiting_review`.

#### Scenario: Rama sin revisar
- **WHEN** un tick detecta un fallo y existe una entrada pendiente de una ejecución anterior del mismo objetivo
- **THEN** no se lanza una nueva ejecución y el tick se registra como `awaiting_review` con la referencia a la entrada pendiente

### Requirement: Límites por tick y por día
Cada objetivo de vigilancia SHALL tener un presupuesto y unas rondas máximas por tick, más un presupuesto máximo diario acumulado. Si se alcanza el presupuesto diario, los ticks siguientes de ese día MUST limitarse a verificar, sin invocar agentes.

#### Scenario: Presupuesto diario agotado
- **WHEN** el coste acumulado del día para un objetivo alcanza su presupuesto diario y un tick detecta un fallo
- **THEN** no se invoca ningún agente y el tick se registra como `budget_exhausted`

### Requirement: Cortacircuitos y escalado a humano
Si un objetivo acumula K ticks consecutivos cuyas ejecuciones no terminan en `completed`, el sistema SHALL abrir un cortacircuitos: los ticks siguientes MUST solo verificar, sin invocar agentes, hasta que un humano lo restablezca. El sistema MUST añadir una entrada de escalado a la bandeja de revisión.

#### Scenario: Fallos repetidos
- **WHEN** K ticks consecutivos de un objetivo terminan en ejecuciones `stalled`, `blocked` o `agent_error`
- **THEN** se abre el cortacircuitos, se añade una entrada de escalado a la bandeja y el siguiente tick no invoca agentes

#### Scenario: Restablecimiento
- **WHEN** el humano restablece el cortacircuitos del objetivo
- **THEN** el siguiente tick vuelve a poder lanzar ejecuciones con agente

### Requirement: Registro de ticks
Cada tick SHALL quedar registrado con marca de tiempo, objetivo, resultado (`noop`, `run`, `skipped`, `awaiting_review`, `budget_exhausted` o `circuit_open`), identificador de ejecución si lo hubo, y coste.

#### Scenario: Historial de vigilancia
- **WHEN** un objetivo se ejecutó cada 30 minutos durante dos horas
- **THEN** el registro contiene una entrada por tick con su resultado y coste, y `factory status` muestra el resumen

### Requirement: Programación externa explícita
El sistema SHALL generar, a petición, la configuración para programar los ticks con cron, launchd o `/loop` de Claude Code. MUST NOT instalar ni modificar ninguna programación del sistema por su cuenta.

#### Scenario: Obtener configuración de cron
- **WHEN** el usuario pide la configuración de programación de un objetivo con un intervalo de 30 minutos
- **THEN** el sistema imprime la línea de cron, la plantilla de launchd y el comando `/loop` equivalentes, sin modificar el sistema
