# goal-loop Specification

## Purpose

Ejecuta un objetivo finito de forma autónoma a partir de un archivo `goal.md`, que reúne objetivo, criterios verificables por máquina, alcance y condiciones de parada. El loop itera hasta cumplirlo o hasta detenerse por una razón explícita, de modo que el humano pasa de dar cada instrucción a supervisar desde fuera.

## Requirements

### Requirement: Definición del objetivo en goal.md
Un objetivo SHALL definirse en un archivo Markdown con metadatos estructurados y cuerpo en lenguaje natural. Los metadatos MUST incluir: el objetivo en una frase, criterios de aceptación expresados como comandos, alcance (rutas permitidas y prohibidas) y condiciones de parada. Pueden incluir el identificador de una feature de la lista de features.

#### Scenario: Objetivo válido
- **WHEN** se valida un `goal.md` que tiene objetivo, al menos un criterio con comando, alcance y condiciones de parada
- **THEN** la validación es exitosa y muestra el resumen del objetivo y los límites efectivos

#### Scenario: Criterios no verificables
- **WHEN** se valida un `goal.md` cuyos criterios de aceptación no incluyen ningún comando
- **THEN** la validación falla con un mensaje que exige al menos un criterio verificable por máquina, y el loop no se inicia

### Requirement: Valores por defecto acotados
Si `goal.md` omite condiciones de parada, el loop SHALL aplicar límites por defecto finitos: rondas máximas, presupuesto máximo en USD, rondas máximas sin progreso y tiempo máximo por ronda. Los límites efectivos MUST mostrarse antes de iniciar.

#### Scenario: goal.md sin límites
- **WHEN** se ejecuta un objetivo sin condiciones de parada explícitas
- **THEN** el loop usa los límites por defecto, los muestra al inicio y ninguna ejecución puede superarlos

### Requirement: Ejecución iterativa con contexto nuevo por ronda
`factory goal run <goal.md>` SHALL ejecutar rondas sucesivas. Cada ronda MUST invocar al agente en una sesión nueva, sin reanudar la anterior. Su entrada MUST incluir el objetivo, el resumen acotado del estado del loop y la retroalimentación de la ronda previa, no la transcripción completa de rondas anteriores.

#### Scenario: Segunda ronda tras un fallo
- **WHEN** la ronda 1 termina con criterios fallidos
- **THEN** la ronda 2 inicia una sesión nueva que recibe el objetivo, el resumen del estado y los fallos concretos de la ronda 1

### Requirement: Verificación determinista por el orquestador
Al final de cada ronda, el orquestador SHALL ejecutar por sí mismo los comandos de aceptación y registrar cuáles pasan. Lo que el agente afirme sobre su propio trabajo MUST NOT bastar para declarar éxito.

#### Scenario: El agente declara éxito pero un test falla
- **WHEN** el agente informa que terminó y uno de los comandos de aceptación termina con código distinto de cero
- **THEN** la ronda se registra como fallida y el loop continúa o se detiene según las condiciones de parada

### Requirement: Condiciones de parada explícitas
El loop SHALL detenerse en cuanto se cumpla cualquiera de estas condiciones:
- éxito (todos los criterios pasan y el evaluador aprueba en las rondas consecutivas requeridas);
- rondas máximas;
- presupuesto agotado;
- sin progreso (la misma firma de fallo durante K rondas);
- bloqueo que requiere decisión humana;
- interrupción del usuario.

MUST registrar el motivo de la parada.

#### Scenario: Éxito
- **WHEN** todos los criterios de aceptación pasan y el evaluador aprueba en el número requerido de rondas consecutivas
- **THEN** el loop termina con resultado `completed` y código de salida cero

#### Scenario: Sin progreso
- **WHEN** el mismo conjunto de criterios falla con la misma firma de error durante K rondas consecutivas
- **THEN** el loop termina con resultado `stalled`, código de salida distinto de cero y la firma repetida en el estado

#### Scenario: Presupuesto agotado
- **WHEN** el coste acumulado de las invocaciones alcanza el presupuesto máximo
- **THEN** no se inicia ninguna ronda nueva y el loop termina con resultado `budget_exhausted`

#### Scenario: Bloqueo humano
- **WHEN** el agente informa de forma estructurada que necesita una decisión humana
- **THEN** el loop termina con resultado `blocked` y la pregunta queda en la bandeja de revisión humana

### Requirement: Respeto del alcance
El orquestador SHALL comprobar tras cada ronda que los archivos modificados estén dentro de las rutas permitidas y fuera de las prohibidas. Si una ronda toca una ruta prohibida, MUST registrarse como fallida y sus cambios MUST revertirse.

#### Scenario: Modificación de ruta prohibida
- **WHEN** una ronda modifica un archivo que coincide con una ruta prohibida del `goal.md`
- **THEN** los cambios de esa ronda se revierten, la ronda se registra como fallida por violación de alcance y la retroalimentación de la siguiente ronda nombra el archivo

### Requirement: Sin integración automática
El loop SHALL dejar su resultado en una rama propia y MUST NOT hacer merge a la rama principal ni push a ningún remoto. La integración la decide un humano.

#### Scenario: Objetivo completado
- **WHEN** el loop termina con resultado `completed`
- **THEN** los cambios quedan en la rama de la ejecución, la rama principal no cambia y la bandeja de revisión humana indica la rama a revisar

### Requirement: Modo de simulación
`factory goal run` SHALL ofrecer un modo de simulación que valide el objetivo, muestre los límites efectivos, los roles y los comandos de verificación, y termine sin invocar a ningún agente ni modificar archivos.

#### Scenario: Simulación
- **WHEN** se ejecuta el objetivo en modo de simulación
- **THEN** se muestra el plan de ejecución, no se invoca ningún agente, no se crea ninguna rama y el coste es cero

### Requirement: Rutas protegidas
Tras cada ronda, el orquestador SHALL comparar la rama de la ejecución con su commit base. Si un archivo que ya existía en la base y coincide con una ruta protegida aparece modificado, borrado o renombrado, la ronda MUST registrarse como fallida y sus cambios MUST revertirse. Crear archivos nuevos en rutas protegidas MUST estar permitido.

#### Scenario: El maker modifica un test existente protegido
- **WHEN** las rutas protegidas incluyen `tests/**` y una ronda cambia una aserción de un test existente
- **THEN** la ronda se revierte, se registra como fallida por ruta protegida y la retroalimentación de la siguiente ronda nombra el archivo

#### Scenario: El maker añade un test nuevo
- **WHEN** las rutas protegidas incluyen `tests/**` y una ronda solo crea `tests/test_nuevo.py`
- **THEN** la ronda no falla por rutas protegidas y el archivo nuevo se conserva

#### Scenario: Renombrar un archivo protegido
- **WHEN** una ronda renombra un archivo existente que coincide con una ruta protegida
- **THEN** el cambio cuenta como borrado del archivo original y la ronda se revierte

### Requirement: Archivos críticos del harness siempre protegidos
Algunos archivos SHALL estar siempre protegidos, cualquiera que sea la configuración: `feature_list.json`, `factory.toml`, el script del comando de verificación y `prompts/**`. Ni `factory.toml` ni `goal.md` MUST poder liberarlos. Así una rama nunca puede cambiar las reglas con las que se la juzga.

#### Scenario: El maker edita el script de verificación
- **WHEN** una ronda modifica `scripts/check.sh` y ningún objetivo lo protege explícitamente
- **THEN** la ronda se revierte por modificar un archivo crítico del harness

#### Scenario: Un objetivo intenta liberar un archivo crítico
- **WHEN** un `goal.md` declara `scope.allow_modify` con `factory.toml`
- **THEN** la validación del objetivo falla indicando que los archivos críticos del harness no se pueden liberar

### Requirement: Rutas protegidas configurables y liberación explícita
Las rutas protegidas SHALL componerse de tres fuentes: las críticas del harness, `[loop] protected_paths` de `factory.toml` y `scope.protected` del `goal.md`. Un objetivo MAY liberar rutas no críticas que deba modificar mediante `scope.allow_modify`. La validación y la simulación MUST mostrar las rutas protegidas y las liberadas.

#### Scenario: Objetivo que debe actualizar un test existente
- **WHEN** `factory.toml` protege `tests/**` y el objetivo declara `scope.allow_modify` con `tests/test_calc.py`
- **THEN** modificar `tests/test_calc.py` no hace fallar la ronda, y modificar cualquier otro test existente sí

#### Scenario: Simulación muestra la protección efectiva
- **WHEN** se ejecuta `factory goal run --dry-run` sobre un objetivo con rutas protegidas y liberadas
- **THEN** el plan lista las rutas protegidas efectivas y las liberadas por el objetivo

### Requirement: Retrabajo desde una ejecución anterior
`factory goal rework <run-id>` SHALL continuar una ejecución terminada sin éxito (`blocked`, `max_rounds`, `stalled`, `budget_exhausted`, `agent_error` o `interrupted`) con una respuesta humana obligatoria.

La nueva ejecución:
- MUST partir de la punta de la rama anterior en una rama nueva;
- MUST conservar el commit base original;
- MUST registrar la ejecución padre;
- MUST entregar la respuesta humana como retroalimentación inicial del maker.

La rama anterior MUST quedar intacta.

#### Scenario: Retrabajo de una ejecución bloqueada
- **WHEN** una ejecución terminó `blocked` y el humano ejecuta `factory goal rework <run-id> --answer "usa el archivo nuevo"`
- **THEN** se crea una ejecución hija desde la punta de la rama padre, con el commit base original; el primer prompt del maker incluye la respuesta, y el diff acumulado que ve el checker incluye el trabajo de la ejecución padre

#### Scenario: Retrabajo de una ejecución completada
- **WHEN** se pide retrabajo de una ejecución que terminó `completed`
- **THEN** el comando falla sin crear ninguna ejecución y sugiere `factory land`

#### Scenario: Retrabajo sin respuesta
- **WHEN** se ejecuta `factory goal rework <run-id>` sin `--answer` ni `--answer-file`
- **THEN** el comando falla sin crear ninguna ejecución e indica que la respuesta humana es obligatoria

#### Scenario: La entrada de la bandeja de la ejecución padre
- **WHEN** se crea una ejecución hija por retrabajo
- **THEN** la entrada de la bandeja de la ejecución padre queda marcada como revisada, con la referencia a la ejecución hija
