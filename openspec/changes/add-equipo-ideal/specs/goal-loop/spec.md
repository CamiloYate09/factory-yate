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
