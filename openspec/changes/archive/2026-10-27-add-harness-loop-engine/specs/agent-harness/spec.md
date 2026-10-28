# Spec Delta

## Purpose

Define el contrato del harness del repositorio: los artefactos y reglas que permiten a un agente de codificación arrancar, mantenerse en alcance, verificar su trabajo y dejar el repositorio listo para la siguiente sesión sin depender del historial de chat.

## ADDED Requirements

### Requirement: Archivo de instrucciones como router
El repositorio SHALL tener un archivo de instrucciones de entrada de 200 líneas o menos. Debe contener un resumen del proyecto, los comandos de arranque y verificación, las restricciones duras, la definición de terminado y enlaces a documentos temáticos. El detalle MUST vivir en esos documentos temáticos, que se cargan bajo demanda, y no en el archivo de entrada.

#### Scenario: Sesión nueva localiza lo esencial
- **WHEN** un agente inicia una sesión nueva y lee solo el archivo de instrucciones de entrada
- **THEN** obtiene el comando de arranque, el comando de verificación, las restricciones duras y la ruta del documento temático de cada área

#### Scenario: Archivo de entrada excede el límite
- **WHEN** el archivo de instrucciones de entrada supera las 200 líneas
- **THEN** la verificación del harness lo reporta como fallo, indicando qué secciones conviene mover a documentos temáticos

### Requirement: Instrucciones compartidas entre agentes
El repositorio SHALL mantener una única fuente canónica de instrucciones para cualquier agente. El archivo específico de Claude Code MUST importar o referenciar esa fuente, no duplicar su contenido.

#### Scenario: Cambio de una regla
- **WHEN** se modifica una restricción dura en la fuente canónica
- **THEN** tanto Claude Code como otros agentes la reciben sin editar un segundo archivo

### Requirement: Ruta estándar de arranque
El repositorio SHALL proveer un único comando de arranque que prepare el entorno reproducible, instale dependencias y ejecute la verificación de referencia. El comando MUST terminar con código distinto de cero si la verificación de referencia falla.

#### Scenario: Arranque en un clon limpio
- **WHEN** se ejecuta el comando de arranque en un clon recién creado con las herramientas base disponibles
- **THEN** el entorno queda listo y la verificación de referencia se ejecuta sin pasos manuales adicionales

#### Scenario: Referencia rota
- **WHEN** la verificación de referencia falla durante el arranque
- **THEN** el comando termina con código distinto de cero e indica qué comprobación falló

### Requirement: Ruta única de verificación
El repositorio SHALL proveer un único comando de verificación completa (lint, formato y tests) que se pueda ejecutar sin interacción. Debe devolver código cero solo si todas las comprobaciones pasan. Los mensajes de fallo MUST indicar qué comprobación falló y cómo reproducirla.

#### Scenario: Todo pasa
- **WHEN** el código cumple lint, formato y tests
- **THEN** el comando de verificación termina con código cero

#### Scenario: Falla una comprobación
- **WHEN** un test falla
- **THEN** el comando termina con código distinto de cero y la salida identifica el test y el comando para reproducirlo

### Requirement: Lista de features como fuente de verdad
El repositorio SHALL mantener una lista de features legible por máquina. Cada feature MUST tener identificador, prioridad, comportamiento visible, comandos de verificación, estado y evidencia. Los estados válidos son `not_started`, `in_progress`, `blocked` y `passing`.

#### Scenario: Feature incompleta en la lista
- **WHEN** una feature no tiene comandos de verificación o tiene un estado fuera de los válidos
- **THEN** la verificación del harness falla e identifica la feature y el campo inválido

### Requirement: Una sola feature activa
El harness SHALL permitir como máximo una feature en estado `in_progress` a la vez (WIP=1).

#### Scenario: Dos features activas
- **WHEN** la lista contiene dos features en `in_progress`
- **THEN** la verificación del harness falla y nombra ambas features

### Requirement: Promoción a passing solo con evidencia
Una feature SHALL pasar a `passing` solo mediante el comando del harness que ejecuta sus comandos de verificación, y solo si todos pasan. El harness MUST registrar la evidencia (comando, resultado, fecha y commit). El harness MUST rechazar una feature en `passing` que no tenga evidencia.

#### Scenario: Verificación exitosa
- **WHEN** se solicita verificar una feature y todos sus comandos terminan con código cero
- **THEN** la feature pasa a `passing` y su evidencia queda registrada con comando, resultado, fecha y commit

#### Scenario: Verificación fallida
- **WHEN** se solicita verificar una feature y alguno de sus comandos falla
- **THEN** la feature no cambia a `passing` y se informa el comando que falló

#### Scenario: Promoción manual sin evidencia
- **WHEN** alguien edita a mano la lista para poner una feature en `passing` sin evidencia
- **THEN** la verificación del harness falla e identifica la feature

### Requirement: Registro de progreso y handoff
El repositorio SHALL mantener un registro de progreso con el estado verificado actual y una entrada por sesión. Cada entrada incluye objetivo, lo completado, la verificación ejecutada, la evidencia, los riesgos y el siguiente paso. Debe existir también una plantilla de handoff compacto para sesiones largas.

#### Scenario: Reanudar en frío
- **WHEN** una sesión nueva lee solo el registro de progreso, la lista de features y los últimos commits
- **THEN** puede determinar la feature de mayor prioridad sin terminar, cómo verificarla y qué riesgos existen, sin consultar el historial de chat

### Requirement: Clean state al cerrar sesión
El harness SHALL definir una lista de cierre de sesión. Al cerrar, el arranque y la verificación funcionan, el progreso y el estado de las features reflejan la realidad, y no quedan pasos a medio hacer sin documentar. Una sesión MUST NOT declararse terminada si alguna dimensión falla.

#### Scenario: Cierre con verificación rota
- **WHEN** una sesión intenta cerrar y el comando de verificación falla
- **THEN** la lista de cierre marca la dimensión como incumplida y el riesgo queda registrado en el progreso antes de terminar

### Requirement: Evaluador independiente en sesiones interactivas
El harness SHALL proveer un rol de revisión independiente, invocable desde una sesión interactiva de Claude Code. Ese rol MUST tener herramientas de solo lectura, recibir solo el diff y los criterios, no el razonamiento del implementador, y emitir un veredicto con evidencia por cada hallazgo.

#### Scenario: Revisión de un cambio
- **WHEN** el implementador solicita revisión de su cambio al rol evaluador
- **THEN** el evaluador devuelve un veredicto (aprobado, rechazado o aceptable con observaciones) con ubicación y evidencia de cada problema, sin modificar archivos
