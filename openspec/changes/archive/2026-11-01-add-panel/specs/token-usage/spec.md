# Spec Delta

## Purpose

Mide en qué se gastan los tokens del proyecto: los loops headless de factory y las sesiones interactivas de Claude Code con sus subagentes. Agrega el consumo por origen, día, modelo, tipo de agente y sesión, sin contar dos veces un mismo mensaje y sin exponer el contenido de las conversaciones.

## ADDED Requirements

### Requirement: Consumo de los loops
El sistema SHALL agregar el consumo de cada evento `agent` de `.factory/runs/*/events.jsonl`: tokens de entrada y de salida, turnos y coste en USD. Lo MUST agrupar por ejecución, rol y modelo, y dar el total. Una línea que no sea JSON válido o un evento sin estos campos MUST ignorarse sin interrumpir la agregación.

#### Scenario: Ejecución con maker y checker
- **WHEN** una ejecución registra un evento `agent` del maker (sonnet, 0,13 USD) y otro del checker (opus, 0,31 USD)
- **THEN** la ejecución suma 0,44 USD y aparece desglosada por rol y por modelo

#### Scenario: Línea corrupta
- **WHEN** `events.jsonl` contiene una línea truncada entre dos eventos válidos
- **THEN** se agregan los dos eventos válidos y la línea truncada se ignora

### Requirement: Transcripciones del proyecto
El sistema SHALL leer las transcripciones de Claude Code del proyecto: las del directorio del repo principal y las de sus worktrees `.claude/worktrees/*` dentro del directorio de proyectos de Claude Code (`$CLAUDE_CONFIG_DIR/projects` o `~/.claude/projects`), incluidos los subagentes. Los worktrees de los loops de factory MUST excluirse, porque su consumo ya cuenta en los loops.

#### Scenario: Sesión en un worktree del equipo
- **WHEN** existe una transcripción de una sesión abierta en `.claude/worktrees/agent-x` del repo
- **THEN** su consumo se suma al del proyecto

#### Scenario: Worktree de un loop
- **WHEN** existe una transcripción de una sesión abierta en `<repo>.factory-worktrees/<run-id>`
- **THEN** no se suma al consumo de las sesiones

### Requirement: Deduplicación por mensaje
El sistema SHALL contar el `usage` de cada mensaje del asistente una sola vez, identificándolo por su id de mensaje (o, si falta, por el id de la petición). Las filas repetidas de un mismo mensaje MUST contarse una vez. Los mensajes sin `usage` o con modelo sintético MUST ignorarse.

#### Scenario: Mensaje repetido por bloques
- **WHEN** una transcripción repite tres veces el mismo id de mensaje con el mismo `usage` de 234 tokens de salida
- **THEN** la salida suma 234 tokens, no 702

### Requirement: Desglose de las sesiones
El consumo de las sesiones SHALL separarse en entrada, escritura de caché, lectura de caché y salida, y agruparse por día, modelo, tipo de agente y sesión. El tipo de agente MUST ser `principal` para la sesión y el tipo declarado del subagente en los demás casos, o `subagente` si no consta. El sistema MUST dar también la proporción de lectura de caché sobre la entrada total.

#### Scenario: Subagente checker
- **WHEN** una sesión lanza un subagente cuyo metadato declara el tipo `checker`
- **THEN** sus tokens aparecen bajo el tipo `checker` y no bajo `principal`

### Requirement: Coste solo donde se registró
El USD SHALL mostrarse solo para el consumo que trae un coste registrado (los loops). El consumo de las sesiones MUST expresarse en tokens, sin precios estimados.

#### Scenario: Sesión interactiva
- **WHEN** solo hay transcripciones de sesiones interactivas
- **THEN** el consumo muestra tokens y ningún importe en USD

### Requirement: Privacidad de las transcripciones
De las transcripciones el sistema SHALL extraer solo modelo, `usage`, marca de tiempo, identificadores de sesión y de agente, y el tipo y la descripción del subagente. El texto de los mensajes, las entradas de herramientas y sus resultados MUST quedar fuera de cualquier salida.

#### Scenario: Mensaje con un secreto
- **WHEN** un mensaje de una transcripción contiene la cadena `SECRETO-123`
- **THEN** la cadena no aparece en ninguna salida de la agregación
