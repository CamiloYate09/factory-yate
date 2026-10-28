# harness-scaffolding Specification

## Purpose

Permite aplicar el harness a cualquier repositorio destino (este u otro, de software o de otro flujo de trabajo) y auditar su estado. Así la fábrica se reutiliza en lugar de copiarse a mano.

## Requirements

### Requirement: Generar el harness en un repositorio destino
El comando `factory init` SHALL crear en el repositorio destino los artefactos mínimos del harness: instrucciones router, lista de features, registro de progreso, plantilla de handoff, comando de arranque, configuración de la fábrica y prompts de roles. Los comandos de verificación MUST salir de lo que detecte en el repositorio o de los que indique el usuario.

#### Scenario: Repositorio sin harness
- **WHEN** se ejecuta `factory init` sobre un repositorio que no tiene ninguno de los artefactos
- **THEN** se crean todos los artefactos mínimos y se lista cada archivo creado junto con los marcadores de posición que el usuario debe completar

#### Scenario: Comandos de verificación indicados por el usuario
- **WHEN** se ejecuta `factory init` indicando explícitamente los comandos de verificación
- **THEN** la configuración generada y las instrucciones usan exactamente esos comandos

### Requirement: No sobrescribir sin confirmación explícita
`factory init` SHALL NOT sobrescribir ni borrar un archivo existente, salvo que el usuario pase una opción explícita de sobrescritura. Sin esa opción, MUST omitir el archivo y reportarlo.

#### Scenario: Archivo de instrucciones existente
- **WHEN** el repositorio destino ya tiene un archivo de instrucciones y no se pasa la opción de sobrescritura
- **THEN** el archivo queda intacto y el resultado lo reporta como omitido

### Requirement: Auditoría del harness
El comando `factory doctor` SHALL evaluar el repositorio destino en los cinco subsistemas del harness (instrucciones, estado, verificación, alcance y ciclo de vida). Debe reportar cada comprobación como crítica o recomendada, con su resultado y una acción correctiva concreta. MUST terminar con código distinto de cero si falla alguna comprobación crítica.

#### Scenario: Harness completo
- **WHEN** se ejecuta `factory doctor` sobre un repositorio que cumple todas las comprobaciones críticas
- **THEN** el comando termina con código cero y muestra el resultado de cada subsistema

#### Scenario: Falta la ruta de verificación
- **WHEN** el repositorio no define un comando de verificación
- **THEN** el comando termina con código distinto de cero, marca la comprobación como crítica fallida y sugiere cómo definir el comando

#### Scenario: Subsistema más débil
- **WHEN** la auditoría termina con fallos en varios subsistemas
- **THEN** el reporte identifica el subsistema con peor resultado como candidato a cuello de botella y propone hasta tres acciones priorizadas

### Requirement: Salida legible por máquina
`factory doctor` SHALL ofrecer una salida estructurada (JSON) con el resultado de cada comprobación, para usarla desde loops o desde CI.

#### Scenario: Consumo desde otro proceso
- **WHEN** se ejecuta `factory doctor` en modo de salida estructurada
- **THEN** la salida es JSON válido con, para cada comprobación, su subsistema, severidad, resultado y acción correctiva
