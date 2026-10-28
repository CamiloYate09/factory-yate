# Spec Delta

## ADDED Requirements

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
