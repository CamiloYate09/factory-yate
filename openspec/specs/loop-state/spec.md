# loop-state Specification

## Purpose

Da a los loops una memoria externa durable y observable: estado por ejecución, registro acumulado de resultados, eventos de cada invocación y una bandeja de revisión humana. Así cada ronda parte de lo ya aprendido, el humano audita sin leer transcripciones y los costes silenciosos quedan a la vista.

## Requirements

### Requirement: Directorio de estado por ejecución
Cada ejecución de loop SHALL tener un identificador único y un directorio de estado propio en la raíz del repositorio principal, fuera de los worktrees y excluido del control de versiones. Ese directorio MUST seguir existiendo después de eliminar el worktree de la ejecución.

#### Scenario: Ejecución terminada
- **WHEN** una ejecución termina y su worktree se elimina
- **THEN** su directorio de estado sigue disponible con el estado, los eventos y una copia del `goal.md` usado

### Requirement: Archivo de estado del loop
El orquestador SHALL mantener por ejecución un archivo `loop-state.md` legible por humanos. Lo MUST actualizar al final de cada ronda y antes de iniciar la siguiente.

Contenido:
- información básica: objetivo, ronda actual y estado;
- por cada ronda: qué hizo el maker, resultado de la verificación, hallazgos, decisión y si requiere intervención humana;
- estadísticas acumuladas y lista de bloqueos;
- resultado final.

#### Scenario: Estado tras una ronda
- **WHEN** termina la ronda 3 de una ejecución
- **THEN** `loop-state.md` contiene las entradas de las rondas 1 a 3 y estadísticas acumuladas que coinciden con ellas

#### Scenario: Interrupción
- **WHEN** la ejecución se interrumpe a mitad de una ronda
- **THEN** `loop-state.md` sigue siendo legible, refleja la última ronda completada y marca el estado como `interrupted`

### Requirement: Resumen acotado para la siguiente ronda
El orquestador SHALL derivar del estado del loop un resumen para la entrada de la siguiente ronda. El resumen tiene un tamaño máximo configurable y prioriza los bloqueos, la mejor ronda y la ronda más reciente. El crecimiento del contexto entre rondas MUST quedar acotado y no ser proporcional al historial completo.

#### Scenario: Ejecución larga
- **WHEN** una ejecución llega a la ronda 15
- **THEN** el resumen entregado al maker no supera el tamaño máximo configurado e incluye la ronda 14 y los bloqueos activos

### Requirement: Registro acumulado de resultados
El sistema SHALL mantener un registro tabular acumulado (`results.tsv`) de solo-añadir, con una fila por ronda de todas las ejecuciones. Cada fila incluye marca de tiempo, identificador de ejecución, ronda, commit, puntuación de verificación, veredicto del checker, decisión (conservar o revertir), coste en USD, duración y descripción breve.

#### Scenario: Auditoría posterior
- **WHEN** se ejecutaron dos loops con tres rondas cada uno
- **THEN** `results.tsv` contiene seis filas nuevas y las filas previas no cambian

### Requirement: Eventos de invocación
El orquestador SHALL registrar en un archivo de eventos (una línea JSON por evento) cada invocación de agente y cada comando de verificación. Para agentes: rol, modelo, inicio, duración, resultado, coste, tokens de entrada y salida, y turnos. Para comandos: comando, código de salida, duración y salida truncada.

#### Scenario: Diagnóstico de una ronda fallida
- **WHEN** un humano investiga por qué falló la ronda 2
- **THEN** el archivo de eventos le muestra qué comandos se ejecutaron, con qué código de salida y qué devolvió el checker, sin leer la transcripción del agente

### Requirement: Bandeja de revisión humana
Al terminar cada ejecución, cualquiera que sea su resultado, el sistema SHALL añadir una entrada pendiente a la bandeja de revisión humana. La entrada incluye resultado, motivo de parada, rama, resumen de archivos cambiados, qué se hizo y por qué, hallazgos sin resolver, preguntas abiertas y coste total. El humano MUST poder listar las entradas pendientes y marcarlas como revisadas.

#### Scenario: Ejecución bloqueada
- **WHEN** una ejecución termina con resultado `blocked`
- **THEN** la bandeja contiene una entrada pendiente con la pregunta que requiere decisión humana y la rama afectada

#### Scenario: Marcar como revisada
- **WHEN** el humano marca una entrada como revisada
- **THEN** deja de aparecer entre las pendientes y conserva la fecha de revisión

### Requirement: Indicadores de costes silenciosos
El comando `factory status` SHALL mostrar las ejecuciones recientes y activas junto con indicadores de los cuatro costes silenciosos:
- deuda de verificación: proporción de criterios verificados por máquina;
- deterioro de la comprensión: archivos y líneas cambiados pendientes de revisión;
- rendición cognitiva: entradas de la bandeja pendientes y su antigüedad;
- explosión de tokens: tendencia de tokens de entrada por ronda.

#### Scenario: Bandeja acumulada
- **WHEN** hay más entradas pendientes en la bandeja que el umbral configurado
- **THEN** `factory status` muestra una advertencia de rendición cognitiva con el número de entradas y la más antigua

#### Scenario: Crecimiento de tokens
- **WHEN** los tokens de entrada por ronda de una ejecución crecen por encima del umbral configurado
- **THEN** `factory status` muestra una advertencia de explosión de tokens para esa ejecución

### Requirement: Artefactos legibles por ronda
Por cada ronda, el orquestador SHALL escribir en `.factory/runs/<run-id>/rounds/<n>/`:
- `maker.md`: estado e informe del maker;
- `checks.md`: resultado de la verificación y de las rutas protegidas;
- `review.md`: veredicto y hallazgos del checker.

Al terminar la ejecución MUST escribir `decision.md`. Cada archivo MUST empezar con líneas `CLAVE: valor` hasta la primera línea en blanco, para que una persona o un script lo lean sin abrir `events.jsonl`.

#### Scenario: Ronda con un criterio fallido
- **WHEN** termina una ronda en la que falla el criterio `tests`
- **THEN** `rounds/<n>/checks.md` empieza con `GATE: FAIL` y `COMMIT: <hash>`, lista el criterio fallido e incluye el final de su salida

#### Scenario: Ronda revertida por rutas protegidas
- **WHEN** una ronda se revierte por modificar una ruta protegida
- **THEN** `rounds/<n>/checks.md` indica `GATE: FAIL` y nombra el archivo protegido y el tipo de cambio (modificado, borrado o renombrado)

#### Scenario: Decisión final
- **WHEN** una ejecución termina por cualquier motivo
- **THEN** `decision.md` empieza con `RESULT: <estado>` y `REASON: <motivo>`, e indica la rama y la mejor ronda

### Requirement: Verificación ligada a un commit
Cada `checks.md` SHALL registrar el hash del commit cuyo árbol se verificó. Si después de verificar la ronda se revierte por el ratchet, `checks.md` MUST indicar también el commit al que volvió la rama.

#### Scenario: Ronda que empeora
- **WHEN** el ratchet revierte la ronda 3 a la mejor ronda registrada
- **THEN** `rounds/3/checks.md` registra el commit verificado de la ronda 3 y el commit de la mejor ronda al que volvió la rama
