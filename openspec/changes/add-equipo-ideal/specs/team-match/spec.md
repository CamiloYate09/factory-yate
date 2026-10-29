# Spec Delta

## Purpose

Define cómo juega el equipo ideal en una sesión interactiva de Claude Code. El técnico decide la convocatoria y dirige el partido; cada jugador cumple un contrato de entrada, salida y permisos; el resultado se consolida en un acta. El árbitro (`checker`) sigue siendo independiente del equipo.

## ADDED Requirements

### Requirement: Técnico y reglamento
El equipo SHALL tener un técnico (`.claude/agents/tecnico.md`) y un reglamento (`.claude/skills/equipo/SKILL.md`), invocable con `/equipo` desde la sesión principal o con `claude --agent tecnico`. El técnico MUST NOT editar archivos: construir corresponde a los constructores.

#### Scenario: Técnico sin escritura
- **WHEN** se inspecciona el frontmatter de `tecnico.md`
- **THEN** declara `tipo: tecnico` y sus herramientas no incluyen `Edit`, `Write` ni `NotebookEdit`

### Requirement: Convocatoria del técnico
El técnico SHALL reunir el contexto (petición, feature activa, cambio OpenSpec y diff) y ejecutar `factory team lineup`. MUST publicar la alineación antes de invocar a ningún jugador, justificando cada alta o baja frente a la sugerencia determinista.

#### Scenario: Convocatoria parcial justificada
- **WHEN** se pide `/equipo` sobre un diff que solo toca `docs/harness/roles.md`
- **THEN** el técnico publica una alineación con `documentador` y `revisor-pr`, explica por qué no convoca a `qa`, `metricas` ni `seguridad` e invoca solo a los convocados

#### Scenario: El técnico amplía la sugerencia
- **WHEN** la sugerencia determinista no incluye a `seguridad` pero la petición menciona autenticación o secretos
- **THEN** el técnico convoca a `seguridad` y deja escrito el motivo en la alineación

### Requirement: Fases del partido
Un partido con petición SHALL seguir este orden:
1. convocatoria;
2. pre-partido: `producto` da las preguntas y los criterios WHEN/THEN, y `qa` el plan de pruebas;
3. construcción: `ingeniero-software`;
4. verificación determinista, que ejecuta el técnico;
5. revisión en paralelo;
6. documentación: `documentador`;
7. acta.

#### Scenario: Pregunta abierta antes de construir
- **WHEN** `producto` devuelve una pregunta sin respuesta propuesta sobre el alcance de la petición
- **THEN** el técnico se la plantea al humano y no invoca a `ingeniero-software` hasta tener respuesta

### Requirement: Verificación determinista del técnico
En la fase de verificación, el técnico SHALL ejecutar `./scripts/check.sh` y, si `metricas` está convocado, `factory complexity --base <ref> --json`. Debe pasar la salida a los revisores. Ningún revisor MUST ejecutar comandos.

#### Scenario: Informe de complejidad para métricas
- **WHEN** `metricas` está convocado
- **THEN** el técnico le pasa la salida de `factory complexity --base <ref> --json` junto con el diff y los criterios

### Requirement: Partido de revisión
Un partido para revisar una rama ya hecha (propia, ajena o `factory/<run-id>` antes de `factory land`) SHALL omitir el pre-partido, la construcción y la documentación, y MUST NOT modificar archivos.

#### Scenario: Revisión de una rama de un loop
- **WHEN** se pide `/equipo` para revisar la rama `factory/<run-id>`
- **THEN** el partido usa el diff de la rama frente a `main`, pasa de la convocatoria a la verificación y la revisión, y `git status --porcelain` no cambia

### Requirement: Entrada y efectos de los revisores
Cada jugador con `tipo: revisor` SHALL recibir solo los criterios, el diff y la salida de la verificación, nunca el razonamiento de un constructor. MUST NOT modificar archivos ni ejecutar comandos: el estado del árbol debe ser el mismo antes y después de invocarlo.

#### Scenario: Revisión sin efectos
- **WHEN** el técnico invoca a `qa` con criterios, diff y verificación
- **THEN** `git status --porcelain` es idéntico antes y después

### Requirement: Formato de salida de los revisores
La salida de un revisor SHALL empezar con `## Jugador: <name> (#<dorsal>)`. Luego debe dar el veredicto (`pass`, `fail` o `pass_with_minor`) y los hallazgos `[critical|medium|minor]`, cada uno con `archivo:línea`, descripción, evidencia y sugerencia. Un hallazgo sin ubicación o sin evidencia MUST NOT contar en el acta.

#### Scenario: Cabecera del jugador
- **WHEN** `qa` responde
- **THEN** la respuesta empieza con `## Jugador: qa (#2)` e incluye un veredicto

#### Scenario: Hallazgo sin evidencia
- **WHEN** un revisor devuelve un hallazgo sin `archivo:línea` o sin evidencia
- **THEN** el técnico no lo cuenta en el acta y pide al revisor que lo concrete

### Requirement: Jugadores revisores iniciales
La plantilla inicial SHALL incluir estos revisores:
- `seguridad` (#1): vulnerabilidades del diff;
- `qa` (#2): plan de pruebas y auditoría de la cobertura, incluidos los tests debilitados, borrados u omitidos;
- `revisor-pr` (#4): una rama o PR completos, propios o ajenos;
- `metricas` (#5): el informe de complejidad;
- `producto` (#6): preguntas y respuestas, criterios y matriz petición→diff.

#### Scenario: Plantilla inicial completa
- **WHEN** se ejecuta `factory team list` tras integrar el cambio
- **THEN** aparecen el técnico, los siete jugadores en sus dorsales y los dorsales 7, 8, 10 y 11 como vacantes

### Requirement: Gravedad en métricas
`metricas` SHALL clasificar como `minor` una función que empeora y queda en el rango C o por debajo. Como `medium`, una función nueva o empeorada que queda en el rango D o superior. Una función sin cambios MUST NOT generar hallazgos.

#### Scenario: Función empeorada hasta D
- **WHEN** el informe muestra una función que pasa de 18 a 23
- **THEN** `metricas` informa de un hallazgo `medium` sobre esa función

### Requirement: Jugadores constructores iniciales
La plantilla inicial SHALL incluir dos constructores:
- `ingeniero-software` (#9): implementa siguiendo AGENTS.md, sin editar `status` ni `evidence`, sin debilitar tests y dentro del alcance;
- `documentador` (#3): actualiza solo documentación (`*.md`).

Los dorsales 7, 8, 10 y 11 MUST quedar vacantes, con perfiles sugeridos en `docs/harness/equipo.md`.

#### Scenario: El documentador no toca código
- **WHEN** el `documentador` recibe un diff que cambia un subcomando del CLI
- **THEN** actualiza la documentación afectada y no modifica ningún archivo fuera de `*.md`

### Requirement: Seguridad en modo guía
El jugador `seguridad` SHALL usar la skill `security-audit`, copiada literal del upstream con su licencia y el commit de origen. MUST aplicar siempre su modo guía sobre el diff recibido, sin preguntas, sin ejecutar código y sin red.

#### Scenario: Sin artefactos de auditoría
- **WHEN** se invoca a `seguridad` sobre un diff
- **THEN** no crea directorios de salida ni invoca otros agentes, y responde con el formato de los revisores

### Requirement: Listón de prueba de seguridad
Un hallazgo bloqueante de `seguridad` SHALL estar probado desde el código, con una traza de entrada a sumidero y sin un control visible que lo impida, y MUST marcarse "no ejecutado". La severidad se traduce así: critical y high → `critical`, medium → `medium`, low e informational → `minor`.

#### Scenario: Inyección de comandos probada desde el código
- **WHEN** el diff construye un comando de shell con una cadena del usuario sin escapar y lo ejecuta con `shell=True`
- **THEN** `seguridad` informa de un hallazgo `critical` o `medium` con la traza de entrada a sumidero, marcado "no ejecutado"

### Requirement: Pistas de seguridad sin prueba
Las sospechas de `seguridad` sin traza completa SHALL listarse en una sección `needs_validation`, con el bloqueo y un plan de validación, y MUST NOT contar para el veredicto.

#### Scenario: Sospecha sin traza completa
- **WHEN** `seguridad` sospecha de una ruta pero no encuentra el sumidero en el código disponible
- **THEN** la pista aparece en `needs_validation` y el veredicto no cambia por ella

### Requirement: Acta del partido
El técnico SHALL cerrar cada partido con un acta: una tabla con el veredicto y los hallazgos por gravedad de cada convocado, seguida de los hallazgos `critical` y `medium`. El veredicto global MUST ser `fail` si algún revisor tiene uno de ellos; esos hallazgos vuelven a construcción. Tras 3 vueltas sin converger, el técnico para e informa al humano.

#### Scenario: Acta con un hallazgo medio
- **WHEN** `qa` devuelve `pass` y `metricas` devuelve un hallazgo `medium`
- **THEN** el acta muestra a ambos jugadores, el veredicto global es `fail` y el hallazgo vuelve a `ingeniero-software`

### Requirement: Árbitro independiente
El acta SHALL NOT sustituir al árbitro. Antes de dar por terminada una feature MUST invocarse al `checker`, que no forma parte del equipo.

#### Scenario: Acta en verde antes de terminar la feature
- **WHEN** el acta termina en `pass`
- **THEN** el técnico recuerda que falta la revisión del `checker` antes de `factory features verify`
