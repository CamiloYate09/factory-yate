# Spec Delta

## Purpose

Extiende los archivos críticos del harness para que un loop no pueda reescribir el equipo de sub-agentes ni sus skills, que forman parte de cómo se construye y se juzga el trabajo.

## ADDED Requirements

### Requirement: Definiciones del equipo protegidas
Además de los archivos críticos del harness ya existentes, `.claude/agents/**` y `.claude/skills/**` SHALL estar siempre protegidos. Ni `factory.toml` ni `goal.md` MUST poder liberarlos. Crear archivos nuevos en esas rutas MUST seguir permitido, como en el resto de rutas protegidas.

#### Scenario: El maker edita un agente del equipo
- **WHEN** una ronda modifica `.claude/agents/qa.md`
- **THEN** la ronda se revierte por modificar un archivo crítico del harness

#### Scenario: Un objetivo intenta liberar las skills
- **WHEN** un `goal.md` declara `scope.allow_modify` con `.claude/skills/**`
- **THEN** la validación del objetivo falla indicando que los archivos críticos del harness no se pueden liberar

### Requirement: Liberación de un archivo crítico concreto
La validación de `scope.allow_modify` SHALL rechazar un patrón si casa con alguna ruta de muestra de los críticos estáticos (`feature_list.json`, `factory.toml`, `prompts/**`, `.claude/agents/**` y `.claude/skills/**`), como `.claude/**` o `**/SKILL.md`, o si, leído como ruta y sin el prefijo `./`, cae dentro de uno de ellos, como `prompts/checker.md` o `./.claude/agents/qa.md`.

#### Scenario: Un objetivo intenta liberar un agente concreto del equipo
- **WHEN** un `goal.md` declara `scope.allow_modify` con `.claude/agents/qa.md`
- **THEN** la validación del objetivo falla indicando que los archivos críticos del harness no se pueden liberar

#### Scenario: Ruta con prefijo ./
- **WHEN** un `goal.md` declara `scope.allow_modify` con `./prompts/checker.md`
- **THEN** la validación del objetivo falla igual que sin el prefijo

### Requirement: Un patrón aceptado no libera un crítico
Un patrón de `scope.allow_modify` que la validación acepta SHALL NOT liberar ningún archivo crítico. Es el caso del script del comando de verificación, que solo se marca crítico al ejecutar, o de un comodín como `.claude/*/qa.md` o `**/LICENSE`: el archivo crítico sigue protegido en cada ronda.

#### Scenario: Comodín que solapa en parte con un crítico
- **WHEN** un `goal.md` que la validación acepta declara `scope.allow_modify` con `.claude/*/qa.md` y una ronda modifica `.claude/agents/qa.md`
- **THEN** la ronda se revierte por modificar un archivo crítico del harness

#### Scenario: Liberar el script de verificación
- **WHEN** un `goal.md` cuyo criterio ejecuta `./scripts/check.sh` declara `scope.allow_modify` con `scripts/check.sh`
- **THEN** la validación lo acepta y `scripts/check.sh` sigue protegido como crítico

### Requirement: Configuración de Claude Code protegida
Además de los agentes y las skills, `.claude/commands/**`, `.claude/hooks/**` y `.claude/settings.json` SHALL estar siempre protegidos, porque cambian cómo se comportan las sesiones de Claude Code. Ni `factory.toml` ni `goal.md` MUST poder liberarlos.

#### Scenario: Un objetivo intenta liberar los hooks
- **WHEN** un `goal.md` declara `scope.allow_modify` con `.claude/hooks/**`
- **THEN** la validación del objetivo falla indicando que los archivos críticos del harness no se pueden liberar

### Requirement: Rutas con caracteres no ASCII
El alcance y las rutas protegidas SHALL aplicarse igual a las rutas con caracteres no ASCII (por ejemplo, con tildes): las rutas cambiadas MUST leerse de git sin comillas ni escapes.

#### Scenario: Un crítico con tildes
- **WHEN** una ronda modifica `.claude/agents/métricas.md`, que ya existía en la base
- **THEN** la ronda se revierte por modificar un archivo crítico del harness
