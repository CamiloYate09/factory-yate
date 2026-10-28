# maker-checker-loop Specification

## Purpose

Garantiza la separación entre generador y evaluador dentro de los loops. Un agente maker implementa, un agente checker independiente y de solo lectura juzga, y solo el orquestador decide aprobar, revertir o seguir. Cada ejecución queda aislada en su propio worktree.

## Requirements

### Requirement: Roles maker y checker independientes
Cada ronda SHALL invocar al maker y al checker como sesiones distintas. Cada rol MUST tener su propio prompt, herramientas permitidas y modelo, configurables por separado, para que puedan usar modelos diferentes. El checker MUST NOT recibir la transcripción ni el razonamiento del maker: solo los criterios, el diff acumulado de la ejecución respecto a su commit base y los resultados de la verificación determinista.

#### Scenario: Entrada del checker
- **WHEN** el maker termina una ronda
- **THEN** el checker se invoca en una sesión nueva con los criterios de aceptación, el diff acumulado desde el commit base de la ejecución y los resultados de verificación, sin la conversación del maker

#### Scenario: Ronda final pequeña tras rondas previas
- **WHEN** la ronda que completaría la ejecución solo corrige una línea, pero una ronda anterior debilitó un test
- **THEN** el checker juzga el diff acumulado, que incluye el test debilitado, y puede rechazar la ronda por ello

#### Scenario: Modelos distintos por rol
- **WHEN** la configuración asigna modelos distintos al maker y al checker
- **THEN** cada invocación usa el modelo de su rol y el modelo usado queda registrado en los eventos de la ronda

### Requirement: Checker de solo lectura
El checker SHALL ejecutarse solo con herramientas de lectura; la verificación determinista la ejecuta el orquestador. Si el árbol de trabajo cambia durante la invocación del checker, el orquestador MUST descartar su veredicto, revertir esos cambios y registrar la ronda como fallida.

#### Scenario: El checker intenta modificar archivos
- **WHEN** el árbol de trabajo difiere antes y después de la invocación del checker
- **THEN** el veredicto se descarta, los cambios se revierten y la ronda se registra como fallida por violación de rol

### Requirement: Veredicto estructurado con evidencia
El checker SHALL devolver un veredicto estructurado y validado contra un esquema. Contiene un resultado (`pass`, `fail` o `pass_with_minor`) y una lista de hallazgos. Cada hallazgo tiene severidad (`critical`, `medium`, `minor`), ubicación, descripción, evidencia y sugerencia. Un veredicto que no cumpla el esquema MUST tratarse como `fail`.

#### Scenario: Veredicto malformado
- **WHEN** la salida del checker no cumple el esquema del veredicto
- **THEN** la ronda se registra como fallida con el motivo "veredicto inválido" y nunca se interpreta como aprobada

#### Scenario: Hallazgo sin evidencia
- **WHEN** el checker reporta un hallazgo sin ubicación o sin evidencia
- **THEN** el veredicto se considera inválido y la ronda se registra como fallida

### Requirement: Aprobación decidida por el orquestador
Una ronda SHALL considerarse aprobada solo si se cumplen las dos condiciones:
- todos los criterios de la verificación determinista pasan;
- el checker devuelve `pass`, o `pass_with_minor` sin hallazgos `critical` ni `medium`.

El maker MUST NOT poder declarar la aprobación ni cambiar el estado de una feature.

#### Scenario: Tests pasan pero el checker rechaza
- **WHEN** todos los comandos de aceptación pasan y el checker devuelve `fail` con un hallazgo `critical`
- **THEN** la ronda no se aprueba y el hallazgo se entrega al maker en la siguiente ronda

#### Scenario: Checker aprueba pero un test falla
- **WHEN** el checker devuelve `pass` y un comando de aceptación falla
- **THEN** la ronda no se aprueba

### Requirement: Retroalimentación entre rondas
El orquestador SHALL entregar al maker de la ronda siguiente los criterios fallidos y los hallazgos del checker, con ubicación y evidencia, en forma de correcciones accionables.

#### Scenario: Corrección guiada
- **WHEN** la ronda N falla por un hallazgo `medium` en un archivo concreto
- **THEN** la entrada del maker en la ronda N+1 incluye ese hallazgo con su ubicación, evidencia y sugerencia

### Requirement: Aislamiento por worktree
Cada ejecución SHALL trabajar en un worktree de git y en una rama propios, creados a partir del commit actual de la rama principal. El worktree MUST quedar fuera del árbol de directorios del repositorio principal, y el directorio principal MUST permanecer sin cambios durante toda la ejecución. Al terminar, el worktree se elimina y la rama se conserva para revisión.

#### Scenario: Instrucciones de la rama de la ejecución
- **WHEN** una ronda modificó el archivo de instrucciones en la rama de la ejecución
- **THEN** el maker de la ronda siguiente solo carga la versión de la rama, no la del directorio principal

#### Scenario: Ejecución concurrente con trabajo humano
- **WHEN** un loop está en ejecución mientras el humano edita archivos en el directorio principal
- **THEN** los cambios del loop solo aparecen en su rama y los archivos del humano no se modifican

#### Scenario: Repositorio sin commits
- **WHEN** se intenta iniciar un loop en un repositorio cuya rama principal no tiene commits
- **THEN** el loop no se inicia y el mensaje indica que se necesita un commit inicial

### Requirement: Instantánea por ronda y ratchet
El orquestador SHALL registrar un commit en la rama de la ejecución tras cada ronda del maker. Si la puntuación de verificación de una ronda (criterios que pasan) es menor que la mejor registrada, MUST revertir la rama al commit de la mejor ronda antes de la siguiente.

#### Scenario: Ronda que empeora
- **WHEN** la mejor ronda registrada tenía 4 de 5 criterios aprobados y la ronda actual queda en 2 de 5
- **THEN** la rama vuelve al commit de la mejor ronda, la reversión queda registrada y la siguiente ronda parte de ese estado

#### Scenario: Ronda que mejora o iguala
- **WHEN** la ronda actual iguala o supera la mejor puntuación registrada
- **THEN** su commit se conserva y pasa a ser la nueva referencia

### Requirement: Promoción de feature por el orquestador
Si el objetivo está asociado a una feature y la ejecución termina con resultado `completed`, el orquestador SHALL marcar la feature como `passing` en la rama de la ejecución. MUST usar el mismo mecanismo de promoción con evidencia del harness e incluir el identificador de la ejecución en la evidencia.

#### Scenario: Ejecución completada con feature asociada
- **WHEN** termina con resultado `completed` una ejecución cuyo objetivo referencia una feature
- **THEN** en la rama de la ejecución la feature queda en `passing`, con evidencia de los comandos ejecutados y el identificador de la ejecución

### Requirement: Permisos mínimos y sin omisión de permisos
Las invocaciones de agentes SHALL usar listas explícitas de herramientas permitidas y denegadas por rol. MUST NOT usar ningún modo que omita las comprobaciones de permisos. Las acciones de publicación (push, creación de PR, despliegues) MUST estar denegadas para ambos roles.

#### Scenario: El maker intenta hacer push
- **WHEN** el maker intenta ejecutar un push a un remoto
- **THEN** la acción se deniega y ningún remoto recibe cambios de la ejecución

### Requirement: Fallos de invocación del agente
Cuando una invocación de agente falle (error del CLI, salida ilegible o tiempo agotado), el orquestador SHALL registrarla como ronda con error. Si las invocaciones fallan en rondas consecutivas hasta el umbral configurado, MUST detener el loop con resultado `agent_error`.

#### Scenario: CLI del agente no disponible
- **WHEN** el ejecutable del agente no está instalado o termina con error en las rondas consecutivas configuradas
- **THEN** el loop termina con resultado `agent_error` y el mensaje indica el error y cómo verificar la instalación
