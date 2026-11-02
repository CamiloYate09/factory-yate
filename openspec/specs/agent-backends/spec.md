# agent-backends Specification

## Purpose
Permite elegir con qué backend se ejecutan los agentes de los loops (el CLI de Claude Code o la librería Python Strands) y fija las garantías que cualquier backend debe cumplir: sesión nueva, permisos con fallo cerrado, confinamiento de rutas, coste contabilizado y salida estructurada.

## Requirements

### Requirement: Selección del backend de agentes
`factory.toml` SHALL aceptar `[agent] backend` con los valores `claude-code` o `strands`. Si se omite, el backend MUST ser `claude-code`. Cualquier otro valor MUST rechazarse al cargar la configuración con un mensaje que liste los valores válidos. Todas las invocaciones de agentes de `goal run`, `goal rework`, `tick` e `intake` MUST usar el backend configurado.

#### Scenario: Configuración sin backend
- **WHEN** `factory.toml` no declara `[agent] backend`
- **THEN** los agentes se ejecutan con Claude Code, igual que antes del cambio

#### Scenario: Backend desconocido
- **WHEN** `factory.toml` declara `backend = "otro"`
- **THEN** cualquier comando que cargue la configuración termina con código distinto de cero y el mensaje nombra `claude-code` y `strands`

### Requirement: Dependencia opcional del backend Strands
El backend `strands` SHALL depender de un extra opcional del paquete. El arranque y la verificación estándar MUST funcionar sin ese extra. Si se elige `strands` sin el extra instalado, la invocación MUST fallar como error de agente, con un mensaje que indique cómo instalarlo.

#### Scenario: Strands no instalado
- **WHEN** `backend = "strands"` y la librería no está instalada
- **THEN** la invocación devuelve un error de agente que indica el comando de instalación del extra, y el loop aplica su regla de fallos de invocación

### Requirement: Sesión nueva y sin estado compartido
Cada invocación de un agente con el backend `strands` SHALL crear un agente nuevo, sin reanudar conversaciones anteriores. MUST NOT persistir sesiones ni memoria a largo plazo, cargar skills, delegar en subagentes ni dejar tareas en segundo plano.

#### Scenario: Dos rondas consecutivas
- **WHEN** el maker se invoca en la ronda 1 y de nuevo en la ronda 2
- **THEN** la segunda invocación no recibe la conversación ni la memoria de la primera, y no aparece ningún directorio de sesión o memoria del backend en el worktree ni en el repo

### Requirement: Traducción de herramientas con fallo cerrado
Las herramientas permitidas y denegadas de cada rol SHALL traducirse a un conjunto fijo de herramientas del backend. Si una herramienta permitida no tiene traducción, la invocación MUST fallar antes de llamar al modelo y nombrar la herramienta. Una herramienta denegada MUST NOT estar disponible aunque también figure entre las permitidas.

#### Scenario: Herramienta sin traducción
- **WHEN** un rol permite `NotebookEdit` y el backend es `strands`
- **THEN** la invocación falla sin coste, el error nombra `NotebookEdit` y no se llama al modelo

#### Scenario: Checker de solo lectura
- **WHEN** se invoca al checker con sus herramientas por defecto
- **THEN** solo dispone de herramientas de lectura y búsqueda, y no tiene herramientas de escritura, edición ni shell

### Requirement: Shell restringido a los prefijos permitidos
Con el backend `strands`, el shell SHALL ejecutar solo comandos cuyo inicio coincida con un prefijo `Bash(<prefijo>:*)` permitido al rol y con ninguno denegado. Un comando con operadores de encadenamiento, redirección o sustitución MUST rechazarse. Los comandos MUST ejecutarse en el directorio de trabajo de la invocación.

#### Scenario: Push del maker
- **WHEN** el maker intenta ejecutar `git push origin main`
- **THEN** el comando se rechaza sin ejecutarse y el agente recibe un error de herramienta

#### Scenario: Encadenamiento para eludir el prefijo
- **WHEN** el maker intenta ejecutar `git status; rm -rf src`
- **THEN** el comando se rechaza sin ejecutar ninguna de sus partes

### Requirement: Confinamiento de rutas
Con el backend `strands`, las herramientas de archivos SHALL actuar solo dentro del directorio de trabajo de la invocación. Los directorios adicionales de lectura MUST ser de solo lectura. Las rutas fuera de esos directorios, incluidas las que salen por enlaces simbólicos o `..`, y las rutas denegadas por rol MUST rechazarse.

#### Scenario: Escritura fuera del worktree
- **WHEN** el maker intenta escribir en un archivo del repositorio principal fuera de su worktree
- **THEN** la escritura se rechaza y el archivo no cambia

#### Scenario: Ruta denegada por rol
- **WHEN** el maker intenta editar `feature_list.json` en su worktree
- **THEN** la edición se rechaza y el archivo no cambia

#### Scenario: Cerebro de solo lectura
- **WHEN** el agente intenta escribir en un directorio de cerebro recibido como lectura adicional
- **THEN** la escritura se rechaza y la lectura del mismo directorio sí funciona

### Requirement: Coste contabilizado
Cada invocación con el backend `strands` SHALL devolver un coste en USD calculado a partir de los tokens consumidos y de la tabla de precios configurada para el modelo. Si el modelo no tiene precio, la invocación MUST fallar antes de llamar al modelo. El presupuesto por ejecución, el presupuesto diario y los cortacircuitos MUST seguir funcionando con este coste.

#### Scenario: Modelo sin precio
- **WHEN** un rol usa un modelo que no figura en la tabla de precios
- **THEN** la invocación falla sin llamar al modelo y el mensaje indica cómo añadir su precio

#### Scenario: Presupuesto agotado
- **WHEN** el coste acumulado de las invocaciones de Strands alcanza el presupuesto de la ejecución
- **THEN** el loop se detiene por presupuesto, igual que con Claude Code

### Requirement: Resultado equivalente entre backends
El backend `strands` SHALL devolver el mismo resultado que Claude Code: éxito o error, texto, salida estructurada, coste, tokens de entrada y salida, turnos, duración y modelo. La salida estructurada MUST validarse con los mismos esquemas. Un tiempo agotado o una excepción del backend MUST devolverse como error de agente, no propagarse.

#### Scenario: Veredicto del checker
- **WHEN** el checker de Strands responde con un JSON de veredicto válido
- **THEN** el orquestador lo valida y lo registra igual que un veredicto de Claude Code, con su coste y sus tokens en los eventos

#### Scenario: Excepción del proveedor
- **WHEN** el proveedor del modelo devuelve un error de credenciales
- **THEN** la invocación devuelve un error de agente con el mensaje del proveedor, y el loop aplica su regla de fallos consecutivos

### Requirement: Diagnóstico del backend
`factory doctor` SHALL informar del backend activo. Con `strands`, MUST avisar si falta la dependencia o si algún modelo de los roles no tiene precio. Esos avisos MUST NOT hacer fallar el doctor cuando el backend activo es `claude-code`.

#### Scenario: Backend Strands sin precio para un rol
- **WHEN** `backend = "strands"` y el modelo del checker no tiene precio
- **THEN** `factory doctor` lo señala nombrando el rol y el modelo
