# Design

## Context

Motivación: ver `proposal.md`.

**Estado actual:**
- `.claude/agents/` solo contiene `checker.md`: revisor de solo lectura (`tools: Read, Grep, Glob`, `model: opus`) con un veredicto en Markdown (`✅ pass / ❌ fail / ⚠️ pass_with_minor`) y hallazgos `[critical|medium|minor]` con Ubicación, Descripción, Evidencia y Sugerencia.
- Los loops headless (`factory goal run`, `factory tick`) no leen `.claude/agents/`. Sus roles salen de `prompts/*.md` y de `[roles.*]` en `factory.toml`. Por eso este cambio no toca el motor.
- `cli.py` registra grupos argparse con `set_defaults(handler=…)`. `doctor.py` agrupa sus comprobaciones en cinco subsistemas fijos. `protection.py` define `STATIC_CRITICAL` y `CRITICAL_SAMPLES`.
- **Base del jugador de seguridad:** `cloudflare/security-audit-skill` @ `c1c8a8c` (MIT). Su `SKILL.md` tiene dos modos:
  - **guía** (por defecto, sin artefactos);
  - **auditoría completa** en 6 fases, que delega en agentes, escribe un directorio de salida y ejecuta validadores de Node.

  Para declarar `confirmed` un hallazgo exige un resultado observado al ejecutar.

**Restricción de Claude Code:** solo un agente con la herramienta `Agent` puede invocar subagentes. La sesión principal la tiene; los revisores de solo lectura, no. Por eso el técnico es quien orquesta y los jugadores nunca se invocan entre sí.

## Goals / Non-Goals

**Goals:**
- Una plantilla extensible: fichar es añadir un archivo; no hay registro central que editar.
- Convocatoria explicable: una sugerencia determinista y verificable que el técnico ajusta con el contexto, justificando cada cambio.
- Separación maker/checker reforzada: quien construye nunca aprueba, y cada revisor recibe solo criterios, diff y verificación.
- Contrato de salida común a todos los revisores, para consolidar un acta única.

**Non-Goals:**
- Ejecutar el equipo dentro de los loops headless (cambio posterior).
- Fichar los puestos vacantes.
- Modo de auditoría completa de seguridad.
- Métricas distintas de la complejidad ciclomática.

## Decisions

### D1. La plantilla vive en el frontmatter de cada agente
Cada miembro del equipo es `.claude/agents/<name>.md` con tres claves planas adicionales. Claude Code ignora las claves que no conoce; la prueba e2e de cada jugador lo confirma con `claude -p --agent <name>`.

- `dorsal`: entero de 1 a 11, único en la plantilla. Fija la posición en un 4-3-3 clásico:

  | Dorsal | Posición |
  |---|---|
  | 1 | portero |
  | 2 | lateral-derecho |
  | 3 | lateral-izquierdo |
  | 4 | central-derecho |
  | 5 | central-izquierdo |
  | 6 | pivote |
  | 7 | extremo-derecho |
  | 8 | interior-derecho |
  | 9 | delantero-centro |
  | 10 | mediapunta |
  | 11 | extremo-izquierdo |

- `tipo`:
  - `revisor`: solo lectura; `tools` ⊆ {`Read`, `Grep`, `Glob`}.
  - `constructor`: puede editar; `tools` no incluye `Agent`.
  - `tecnico`: sin `dorsal`; como mucho uno en la plantilla; `tools` no incluye `Edit`, `Write` ni `NotebookEdit`.
- `convocatoria`: cadena con elementos separados por comas. Cada elemento es un glob de ruta relativa al repo (la misma sintaxis que `scope` de `goal.md`: `**`, `*`, `?`) o uno de los tokens `siempre` o `peticion`. El técnico no la lleva.
- Un archivo sin `dorsal` ni `tipo` no pertenece al equipo y no se valida. Es el caso del `checker`, que actúa como **árbitro**.
- *Alternativa: un `equipo.toml` central.* Se descarta porque cada fichaje tocaría dos archivos y porque las unidades de trabajo en paralelo chocarían en él.

### D2. Plantilla inicial

| # | Posición | `name` | `tipo` | `model` | `convocatoria` |
|---|---|---|---|---|---|
| — | técnico | `tecnico` | tecnico | opus | — |
| 1 | portero | `seguridad` | revisor | opus | `**/*.py, **/*.sh, pyproject.toml, factory.toml, prompts/**, .claude/**, src/factory/templates/**, goals/**` |
| 2 | lateral-derecho | `qa` | revisor | sonnet | `src/**, tests/**` |
| 3 | lateral-izquierdo | `documentador` | constructor | sonnet | `src/factory/cli.py, src/factory/config.py, factory.toml, docs/**, README.md, AGENTS.md, CLAUDE.md` |
| 4 | central-derecho | `revisor-pr` | revisor | opus | `siempre` |
| 5 | central-izquierdo | `metricas` | revisor | sonnet | `**/*.py` |
| 6 | pivote | `producto` | revisor | opus | `peticion, openspec/changes/**` |
| 9 | delantero-centro | `ingeniero-software` | constructor | sonnet | `peticion` |

**Vacantes:** 7, 8, 10 y 11. Perfiles sugeridos, que solo se documentan:
- 10 `arquitecto`: coherencia con OpenSpec y con `design.md`.
- 8 `bibliotecario`: cura los cerebros, propone `factory brain learn` y cita el principal.
- 7 `rendimiento-costes`: complejidad algorítmica, E/S y coste de tokens en los loops.
- 11 `experiencia-cli`: ayuda, mensajes de error accionables y ergonomía.

### D3. Formato común de los revisores
La salida es la del `checker`, precedida de la cabecera `## Jugador: <name> (#<dorsal>)`:

```
## Jugador: qa (#2)

## Veredicto
✅ pass / ❌ fail / ⚠️ pass_with_minor

## Hallazgos

### 1. [critical|medium|minor] Título
- Ubicación: archivo:línea
- Descripción: …
- Evidencia: …
- Sugerencia: …
```

- **Entrada:** criterios, diff y salida de la verificación. Nunca el razonamiento de un constructor.
- **Hallazgos:** un hallazgo sin ubicación o sin evidencia no vale. Cada jugador puede añadir secciones propias después de "Hallazgos" (por ejemplo `## needs_validation` en seguridad o `## Matriz de trazabilidad` en producto).
- **Veredicto:** `fail` si hay algún `critical` o `medium`; `pass_with_minor` si solo hay `minor`; `pass` si no hay hallazgos.

### D4. El partido
El reglamento vive en `.claude/skills/equipo/SKILL.md`. Se usa con `/equipo <petición | rama | descripción>` desde la sesión principal, o con `claude --agent tecnico`, cuyo cuerpo remite a esa skill.

1. **Convocatoria.** El técnico reúne el contexto (petición, feature activa, cambio OpenSpec, `git diff`) y ejecuta `factory team lineup`. Puede ajustar la sugerencia, pero justifica cada alta o baja. Publica la alineación antes de seguir.
2. **Pre-partido** (si hay petición). `producto` devuelve preguntas, respuestas propuestas y criterios WHEN/THEN; `qa` devuelve el plan de pruebas. Las preguntas abiertas van al humano antes de construir.
3. **Construcción.** `ingeniero-software` implementa. Es el único que toca código y tests.
4. **Verificación determinista.** La ejecuta el técnico, nunca un revisor: `./scripts/check.sh` y, si `metricas` está convocado, `factory complexity --base <ref> --json`.
5. **Revisión.** Los revisores convocados actúan en paralelo, cada uno con criterios, diff y verificación.
6. **Documentación.** `documentador` actualiza la documentación afectada (solo `*.md`).
7. **Acta.** Tabla por jugador con veredicto y hallazgos. El veredicto global es `fail` si algún revisor tiene un `critical` o un `medium`. Los hallazgos `critical` y `medium` vuelven al paso 3. Tras 3 vueltas sin converger se para y se informa al humano.
8. **Árbitro.** Antes de dar por terminada una feature sigue siendo obligatorio el `checker` (CLAUDE.md), que no forma parte del equipo.

Para revisar una rama ya hecha (propia, de otra persona o una `factory/<run-id>` antes de `factory land`) se omiten los pasos 2, 3 y 6.

### D5. Seguridad: fork declarado del upstream
- **Copia literal.** `.claude/skills/security-audit/` es una copia literal de `skills/security-audit/` en `c1c8a8c`, con su `LICENSE` y un `UPSTREAM.md` que anota el repositorio, el commit y la fecha. Todas las adaptaciones van en `.claude/agents/seguridad.md`, así que resincronizar es copiar de nuevo.
- **Modo.** Siempre modo guía, sobre el diff recibido. Sin preguntas, sin ejecutar nada y sin red.
- **Listón de prueba (desviación del upstream).** Un hallazgo cuenta si está probado desde el código: traza completa de entrada a sumidero y ningún control visible que lo impida. Se marca "no ejecutado".
- **Severidad.** La escala del upstream se traduce así: critical y high → `critical`, medium → `medium`, low e informational → `minor`.
- **Pistas sin prueba.** Van a la sección `## needs_validation`, con el bloqueo exacto y un plan de validación, y no cuentan para el veredicto.
- **Activación en la sesión principal.** La skill también se puede activar sola desde ahí (su `description` menciona auditorías y pen tests). Se acepta para no editar la copia, y por defecto usa el modo guía.

### D6. `factory complexity`
- **Cálculo.** Complejidad ciclomática por función o método con el módulo `ast`, sin dependencias:
  - Base 1, y +1 por cada `if` y `elif`, `for` y `async for`, `while`, `except`, `case` de un `match`, expresión condicional, cada `for` e `if` de una comprensión, y cada operando adicional de `and` y `or`.
  - Las funciones anidadas y las lambdas asignadas a nombre se miden aparte y no suman a la función que las contiene. El resto de lambdas suman a su función.
  - Los métodos se nombran `Clase.metodo`.
- **Rangos** (como radon): A 1–5, B 6–10, C 11–20, D 21–30, E 31–40, F 41 o más.
- **Interfaz:** `factory complexity [RUTAS…] [--base REF] [--max N] [--json]`.
  - **Rutas.** Por defecto, los `*.py` versionados (`git ls-files`); si no hay git, se recorre el árbol excluyendo los directorios ocultos y `.venv`. Un directorio se expande a sus `*.py`.
  - **`--base REF`.** Solo mide los archivos `*.py` cambiados frente a `REF`, incluidos los no versionados. Cada función muestra su complejidad en `REF` (con `git show REF:ruta`) y el delta. Una función nueva no tiene valor base.
  - **`--max N`.** Termina en 1 si alguna función del alcance supera N. En modo `--base`, el alcance son solo las funciones nuevas o empeoradas.
  - **Salida.** Las funciones aparecen ordenadas por complejidad descendente, con un resumen (número, media y máximo). Un archivo con errores de sintaxis se avisa y se omite.
- **Verificación.** No se añade a `scripts/check.sh`: cambiar la verificación requiere una petición explícita.

### D7. Protección del equipo
- `STATIC_CRITICAL` incluye `.claude/agents/**` y `.claude/skills/**`.
- `CRITICAL_SAMPLES` añade `.claude/agents/x.md` y `.claude/skills/x/SKILL.md`, de modo que un `scope.allow_modify` que los liberase se detecta y se rechaza.
- Crear archivos nuevos en esas rutas sigue permitido, como en el resto de rutas protegidas.
- `releases_critical` rechaza además un patrón que, leído como ruta, cae dentro de un crítico estático (`prompts/checker.md`, `.claude/agents/qa.md`). Antes esos objetivos pasaban la validación y cada ronda que tocaba el archivo se revertía hasta agotar el presupuesto. Es una heurística: rechaza lo que casa con una muestra (`**/SKILL.md`) o lo que, sin `./`, cae dentro de un crítico. Otros comodines (`.claude/*/qa.md`, `**/LICENSE`) y el script de verificación pasan la validación, pero no liberan nada, porque `Protection.is_protected` consulta los críticos antes que las liberaciones.

### D8. Frontmatter de referencia
Todos los agentes del equipo siguen exactamente estos tipos:
- `tools` es una cadena separada por comas, como en `checker.md`;
- `dorsal` es un entero sin comillas;
- `tipo` y `convocatoria` son cadenas;
- el cuerpo va en español.

```yaml
---
name: qa
description: Ingeniero de QA del equipo (#2). Diseña el plan de pruebas a partir de los criterios y audita la cobertura de un diff. Solo lectura.
tools: Read, Grep, Glob
model: sonnet
dorsal: 2
tipo: revisor
convocatoria: "src/**, tests/**"
---
```

El técnico omite `dorsal` y `convocatoria`:

```yaml
---
name: tecnico
description: Técnico (orquestador maestro) del equipo ideal. …
tools: Agent, Read, Grep, Glob, Bash
model: opus
tipo: tecnico
---
```

`factory team validate` acepta exactamente estas formas. Otras formas también se aceptan si son equivalentes: `tools` como lista YAML o `convocatoria` como lista YAML de cadenas.

### D9. `factory team`, doctor y tests
- **Módulo.** `src/factory/team/` define `TeamError`, el parser de la plantilla y la convocatoria. Para los globs se reutiliza `factory.globs.matches`.
- **`factory team list [--json]`.** Muestra la formación por líneas (portero, defensa, medio, ataque), con "vacante" en los puestos libres, el técnico y el árbitro (el `checker`, si existe).
- **`factory team validate [--json]`.** Termina en 0 sin errores y en 1 con errores, uno por línea, con archivo y motivo. Una plantilla vacía es válida.
- **`factory team lineup [--base REF] [--paths P…] [--peticion TEXTO | --peticion-file F] [--json]`.**
  - **Rutas.** Si se pasa `--paths`, se usan tal cual. Si no, se toman `git diff --name-only REF` (por defecto `HEAD`) más los archivos no versionados.
  - **Convocatoria.** Un jugador es convocado si:
    - algún glob coincide con alguna ruta;
    - o tiene `peticion` y hay petición;
    - o tiene `siempre` y hay rutas o petición.
  - **Motivo.** El motivo cita hasta 3 rutas coincidentes o el token. Sin rutas ni petición no hay partido: código 0 y nadie convocado.
- **CLI.** Cada handler captura su propio error de dominio (`TeamError`, `ComplexityError`), lo imprime en stderr y devuelve el código 2. Los imports se hacen dentro del handler.
- **`doctor`.** Nueva comprobación crítica `team-roster` en el subsistema `instrucciones`: la plantilla de `.claude/agents/` es válida. Pasa sin agentes del equipo, como en `make_harness` y tras `factory init`.
- **Tests de los agentes.** Cada agente tiene un test autocontenido que lee su frontmatter con pyyaml y comprueba su contrato D2/D8 y sus secciones obligatorias.

## Risks / Trade-offs

- **[Claude Code empieza a rechazar claves de frontmatter desconocidas]** → La prueba e2e de cada jugador lo detectaría. El plan B es mover las tres claves a un comentario HTML del cuerpo, cambiando solo el parser de `factory team`.
- **[El técnico gasta de más convocando a todos]** → Hay una sugerencia determinista, cada alta se justifica y los jugadores ligeros usan `sonnet`.
- **[Severidad de seguridad sin ejecución]** → Es una desviación declarada (D5). Las pistas sin prueba quedan en `needs_validation` y no bloquean.
- **[Desfase con el upstream de seguridad]** → La copia es literal, con `UPSTREAM.md`. Resincronizar es copiar y comparar.
- **[Solapamiento entre `revisor-pr` y el árbitro]** → Tienen ámbitos distintos: `revisor-pr` revisa ramas completas, propias o ajenas, dentro del equipo; el `checker` decide si una feature está terminada y es independiente del equipo.
- **[La skill de seguridad también se puede activar en la sesión principal]** → Se acepta (D5): su modo por defecto no escribe nada.

## Migration Plan

No hay migración: todo es nuevo salvo D7. D7 añade rutas críticas; los objetivos existentes no tocan `.claude/`, así que no cambia su comportamiento. Rollback: revertir los commits del cambio.

## Open Questions

- ¿Qué fichajes cubren primero las vacantes? Se decidirá con el uso.
- ¿Cómo ejecutará el motor de loops a los jugadores convocados (como checkers adicionales con `--agent`)? Queda para el cambio posterior.
