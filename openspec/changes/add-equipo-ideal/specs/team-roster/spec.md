# Spec Delta

## Purpose

Define la plantilla del equipo ideal: qué subagentes forman parte del equipo, en qué puesto juegan, qué pueden hacer y cuándo se convocan. La plantilla se declara en el frontmatter de cada agente, se valida de forma determinista y permite sugerir una convocatoria explicable a partir de los cambios y de la petición.

## ADDED Requirements

### Requirement: Miembros del equipo
Un agente de `.claude/agents/*.md` SHALL formar parte del equipo cuando su frontmatter declare `tipo`. Los jugadores MUST declarar además `dorsal` (entero) y `convocatoria` (cadena de elementos separados por comas: globs de rutas relativas al repo o los tokens `siempre` y `peticion`). Un agente sin `tipo` ni `dorsal` MUST quedar fuera del equipo sin generar errores.

#### Scenario: Jugador declarado
- **WHEN** `.claude/agents/qa.md` declara `dorsal: 2`, `tipo: revisor` y `convocatoria: "src/**, tests/**"`
- **THEN** `qa` forma parte de la plantilla

#### Scenario: Agente ajeno al equipo
- **WHEN** `.claude/agents/checker.md` no declara `tipo` ni `dorsal`
- **THEN** no aparece en la plantilla y la validación no informa de ningún error por él

### Requirement: Posición por dorsal
El dorsal SHALL determinar la posición en un 4-3-3: 1 portero, 2 lateral-derecho, 3 lateral-izquierdo, 4 central-derecho, 5 central-izquierdo, 6 pivote, 7 extremo-derecho, 8 interior-derecho, 9 delantero-centro, 10 mediapunta y 11 extremo-izquierdo.

#### Scenario: Posición del dorsal 2
- **WHEN** un jugador declara `dorsal: 2`
- **THEN** su posición es lateral-derecho

### Requirement: Validación de la plantilla
`factory team validate` SHALL comprobar el contrato de cada miembro del equipo y terminar con código 0 si no hay errores o 1 si los hay. Debe escribir una línea por error con el archivo y el motivo. Una plantilla vacía o la ausencia de `.claude/agents/` MUST ser válidas.

#### Scenario: Plantilla válida
- **WHEN** la plantilla tiene un técnico y jugadores con dorsales únicos y herramientas acordes a su tipo
- **THEN** `factory team validate` termina con código 0

#### Scenario: Sin equipo
- **WHEN** `.claude/agents/` no existe o no contiene miembros del equipo
- **THEN** `factory team validate` termina con código 0

### Requirement: Identidad y dorsal válidos
La validación SHALL considerar error:
- un frontmatter ilegible;
- un `name` distinto del nombre del archivo;
- un `tipo` distinto de `revisor`, `constructor` o `tecnico`;
- un jugador sin dorsal, con dorsal fuera de 1–11 o repetido.

#### Scenario: Dorsal repetido
- **WHEN** dos agentes declaran `dorsal: 4`
- **THEN** `factory team validate` termina con código 1 y nombra ambos archivos y el dorsal repetido

#### Scenario: Dorsal fuera de rango
- **WHEN** un jugador declara `dorsal: 12`
- **THEN** la validación falla indicando que el dorsal debe estar entre 1 y 11

### Requirement: Permisos según el tipo
La validación SHALL considerar error:
- un `revisor` con herramientas distintas de `Read`, `Grep` y `Glob`;
- un `constructor` con `Agent`;
- más de un `tecnico`;
- un `tecnico` con `dorsal` o con `Edit`, `Write` o `NotebookEdit`.

#### Scenario: Revisor con permisos de escritura
- **WHEN** un agente con `tipo: revisor` declara `tools: Read, Grep, Glob, Edit`
- **THEN** la validación falla indicando que un revisor es de solo lectura

#### Scenario: Técnico que edita
- **WHEN** el agente con `tipo: tecnico` declara `Write` entre sus herramientas
- **THEN** la validación falla indicando que el técnico no edita archivos

### Requirement: Formación con vacantes
`factory team list` SHALL mostrar la formación por líneas (portero, defensa, medio y ataque), con el dorsal, la posición y el jugador de cada puesto, y "vacante" en los puestos libres. MUST mostrar también el técnico y, si existe, el árbitro (`checker`). Con `--json` emite los mismos datos.

#### Scenario: Plantilla incompleta
- **WHEN** solo están cubiertos los dorsales 1, 2, 3, 4, 5, 6 y 9
- **THEN** `factory team list` muestra esos siete jugadores en su posición y los dorsales 7, 8, 10 y 11 como vacantes

### Requirement: Entradas de la convocatoria
`factory team lineup` SHALL tomar las rutas cambiadas de `--paths` si se indica y, si no, de `git diff --name-only <base>` (por defecto `HEAD`) más los archivos no versionados. Hay petición cuando se pasa `--peticion` o `--peticion-file`.

#### Scenario: Rutas desde git
- **WHEN** se ejecuta `factory team lineup --base main` en una rama que modifica `src/a.py` y añade el archivo no versionado `tests/test_a.py`
- **THEN** la convocatoria se calcula con ambas rutas

### Requirement: Reglas de convocatoria
Un jugador SHALL quedar convocado si algún glob de su convocatoria coincide con alguna ruta, si declara `peticion` y hay petición, o si declara `siempre` y hay rutas o petición. Cada convocado MUST llevar un motivo que cite hasta 3 rutas coincidentes o el token que lo convoca. Con `--json` se emiten convocados y no convocados.

#### Scenario: Cambio solo en documentación
- **WHEN** las rutas cambiadas son solo `docs/harness/roles.md` y no hay petición
- **THEN** quedan convocados los jugadores cuya convocatoria cubre `docs/**` o declara `siempre`, y `qa` y `metricas` no lo están

#### Scenario: Petición de producto sin cambios
- **WHEN** no hay rutas cambiadas y se pasa `--peticion "exportar el informe en CSV"`
- **THEN** quedan convocados los jugadores con `peticion` o `siempre`, con ese token como motivo

### Requirement: Sin partido
Sin rutas cambiadas ni petición, `factory team lineup` SHALL terminar con código 0, informar de que no hay partido y no convocar a nadie.

#### Scenario: Nada que jugar
- **WHEN** no hay rutas cambiadas ni petición
- **THEN** el comando termina con código 0, informa de que no hay partido y no convoca a nadie

### Requirement: Doctor valida la plantilla
`factory doctor` SHALL incluir la comprobación crítica `team-roster` en el subsistema `instrucciones`. La comprobación pasa si la plantilla es válida y, si falla, MUST mostrar el primer error y la acción `factory team validate`.

#### Scenario: Plantilla rota en el doctor
- **WHEN** un revisor declara `Edit` entre sus herramientas
- **THEN** `factory doctor` marca `team-roster` como crítica fallida y termina con código distinto de cero

### Requirement: Nombres de agente únicos
La validación SHALL considerar error que dos archivos de `.claude/agents/`, sean o no del equipo, declaren el mismo `name`. Conserva el nombre el archivo que se llama igual, o el primero; el error MUST nombrar al otro archivo y al que ya usa el nombre. Si existe `checker.md`, MUST declarar `name: checker`. Así ningún agente puede suplantar a un jugador ni al árbitro.

#### Scenario: Un agente suplanta al árbitro
- **WHEN** existe `.claude/agents/checker.md` y otro archivo `.claude/agents/arbitro-falso.md` declara `name: checker`
- **THEN** `factory team validate` termina con código 1 y nombra `arbitro-falso.md` y `checker.md`
