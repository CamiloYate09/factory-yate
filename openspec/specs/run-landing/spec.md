# run-landing Specification

## Purpose

Permite que un humano integre en la rama principal el resultado de una ejecución terminada con éxito. Antes de avanzar la rama principal, verifica el merge exacto contra su estado actual, sin hacer push. Integrar es siempre una decisión humana explícita.

## Requirements

### Requirement: Integración solo por orden humana
La integración de una ejecución en la rama principal SHALL ocurrir solo mediante el comando `factory land <run-id>`, ejecutado por un humano. `factory goal run` y `factory tick` MUST NOT invocarla nunca.

#### Scenario: Ejecución completada sin integrar
- **WHEN** `factory goal run` o un tick terminan una ejecución con resultado `completed`
- **THEN** la rama principal no cambia hasta que un humano ejecuta `factory land` sobre esa ejecución

### Requirement: Precondiciones de la integración
`factory land` SHALL negarse a integrar y no cambiar nada en estos casos:
- el checkout principal tiene cambios sin commitear;
- el checkout principal no está en la rama principal configurada;
- la ejecución no terminó `completed`;
- la rama de la ejecución no existe;
- la ejecución ya fue integrada.

#### Scenario: Checkout principal con cambios
- **WHEN** se ejecuta `factory land` con archivos modificados sin commitear en el checkout principal
- **THEN** el comando falla sin modificar ninguna rama e indica que hay que limpiar o guardar esos cambios

#### Scenario: Ejecución no completada
- **WHEN** se ejecuta `factory land` sobre una ejecución que terminó `blocked`
- **THEN** el comando falla sin modificar ninguna rama y sugiere `factory goal rework`

### Requirement: Verificación del merge exacto
Antes de integrar, `factory land` SHALL construir el merge de la rama de la ejecución sobre la punta actual de la rama principal, en un worktree temporal fuera del repositorio. Sobre ese resultado MUST ejecutar los criterios de aceptación del objetivo de la ejecución y la comprobación de rutas protegidas, y dejar el informe en `.factory/runs/<run-id>/land/checks.md`.

#### Scenario: La rama principal avanzó y el merge rompe los tests
- **WHEN** la rama principal recibió commits tras la ejecución y el merge resultante hace fallar un criterio de aceptación
- **THEN** la integración se rechaza, la rama principal no cambia y el informe nombra el criterio fallido

#### Scenario: Conflicto de merge
- **WHEN** la rama de la ejecución entra en conflicto con la punta actual de la rama principal
- **THEN** la integración se rechaza, la rama principal no cambia, se listan los archivos en conflicto y se elimina el worktree temporal

### Requirement: Avance al commit verificado
Si la verificación pasa, la rama principal SHALL avanzar exactamente al commit de merge verificado: un merge `--no-ff` con un mensaje que referencia la ejecución. Si la rama principal cambió durante la verificación, la integración MUST rechazarse. El comando MUST NOT hacer push a ningún remoto.

#### Scenario: Integración correcta
- **WHEN** la verificación del merge pasa y la rama principal no cambió durante ella
- **THEN** la rama principal apunta al commit de merge verificado, cuyos padres son la punta anterior de la rama principal y la punta de la rama de la ejecución, y ningún remoto recibe cambios

#### Scenario: La rama principal cambió durante la verificación
- **WHEN** la rama principal recibe un commit mientras `factory land` verifica el merge
- **THEN** la integración se rechaza sin modificar la rama principal y se pide repetir el comando

### Requirement: Cierre tras integrar
Tras una integración correcta, `factory land` SHALL marcar como revisada la entrada de la bandeja de la ejecución, registrar el commit integrado en el estado de la ejecución y eliminar el worktree temporal. La rama de la ejecución MUST conservarse, salvo que el humano pida borrarla con `--delete-branch`.

#### Scenario: Bandeja y estado tras integrar
- **WHEN** termina una integración correcta
- **THEN** la entrada de la bandeja de la ejecución está revisada con el commit integrado, el estado de la ejecución registra ese commit y un segundo `factory land` sobre ella se rechaza por ya integrada

### Requirement: Comprobación sin integrar
`factory land --dry-run` SHALL ejecutar todas las precondiciones y la verificación del merge exacto, sin modificar ninguna rama ni la bandeja.

#### Scenario: Comprobación previa
- **WHEN** se ejecuta `factory land <run-id> --dry-run` y la verificación pasa
- **THEN** el comando informa que la integración es posible, la rama principal no cambia y la entrada de la bandeja sigue pendiente
