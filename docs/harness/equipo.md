# El equipo ideal

Un solo revisor generalista no cubre con la misma profundidad la seguridad, los tests, la complejidad, la documentación, el encaje con la petición y la revisión de ramas. El **equipo ideal** reparte ese trabajo como un equipo de fútbol:

- un **técnico** (`tecnico`), el orquestador maestro, que lee el contexto y decide a quién convoca: a todos o solo a algunos;
- hasta **11 jugadores** especialistas, cada uno un subagente de Claude Code en `.claude/agents/<name>.md` con un puesto, un tipo y unas reglas de convocatoria;
- un **árbitro**, el `checker`, que no forma parte del equipo y sigue siendo obligatorio antes de dar por terminada una feature.

No hay registro central: fichar es añadir un archivo y dar de baja es borrarlo. La plantilla se declara en el frontmatter de cada agente.

## Plantilla

| # | Posición | Jugador | Tipo | Modelo | Convocatoria | Qué hace |
|---|---|---|---|---|---|---|
| — | técnico | `tecnico` | tecnico | opus | — | decide la convocatoria y dirige el partido; no edita |
| 1 | portero | `seguridad` | revisor | opus | `**/*.py, **/*.sh, pyproject.toml, factory.toml, prompts/**, .claude/**, src/factory/templates/**, goals/**` | vulnerabilidades del diff, en modo guía |
| 2 | lateral-derecho | `qa` | revisor | sonnet | `src/**, tests/**` | plan de pruebas y auditoría de la cobertura |
| 3 | lateral-izquierdo | `documentador` | constructor | sonnet | `src/factory/cli.py, src/factory/config.py, factory.toml, docs/**, README.md, AGENTS.md, CLAUDE.md` | actualiza la documentación (solo `*.md`) |
| 4 | central-derecho | `revisor-pr` | revisor | opus | `siempre` | revisa una rama o PR completos, propios o ajenos |
| 5 | central-izquierdo | `metricas` | revisor | sonnet | `**/*.py` | lee el informe de `factory complexity` |
| 6 | pivote | `producto` | revisor | opus | `peticion, openspec/changes/**` | preguntas y respuestas, criterios WHEN/THEN y matriz petición→diff |
| 7 | extremo-derecho | *vacante* | — | — | — | — |
| 8 | interior-derecho | *vacante* | — | — | — | — |
| 9 | delantero-centro | `ingeniero-software` | constructor | sonnet | `peticion` | implementa siguiendo AGENTS.md |
| 10 | mediapunta | *vacante* | — | — | — | — |
| 11 | extremo-izquierdo | *vacante* | — | — | — | — |

- **Revisores:** solo lectura (`Read, Grep, Glob`); nunca ejecutan comandos.
- **Constructores:** pueden editar, pero no invocar a otros agentes.
- **Convocatoria sugerida:** un jugador entra si alguno de sus globs coincide con una ruta cambiada, si tiene `peticion` y hay petición, o si tiene `siempre` y hay rutas o petición.

## Formación (4-3-3)

```text
     11 vacante          9 ingeniero-software          7 vacante

               10 vacante                  8 vacante
                            6 producto

   3 documentador   5 metricas      4 revisor-pr     2 qa

                           1 seguridad

   Banquillo: tecnico (técnico)                Árbitro: checker
```

## Vacantes

Los dorsales 7, 8, 10 y 11 están libres y se irán llenando a medida que lleguen nuevas necesidades. Estos perfiles son solo sugerencias:

| # | Posición | Perfil sugerido | Para qué |
|---|---|---|---|
| 7 | extremo-derecho | `rendimiento-costes` | complejidad algorítmica, E/S y coste de tokens en los loops |
| 8 | interior-derecho | `bibliotecario` | cura los cerebros, propone `factory brain learn` y cita el principal |
| 10 | mediapunta | `arquitecto` | coherencia con OpenSpec y con `design.md` |
| 11 | extremo-izquierdo | `experiencia-cli` | ayuda, mensajes de error accionables y ergonomía |

## Cómo fichar

1. **Crea `.claude/agents/<name>.md`** con este frontmatter (D8), un dorsal libre y el cuerpo en español:

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

   - `dorsal`: entero de 1 a 11, sin comillas y único.
   - `tipo`: `revisor` (`tools` ⊆ `Read, Grep, Glob`) o `constructor` (sin `Agent`).
   - `convocatoria`: globs relativos al repo (`**`, `*`, `?`) y los tokens `siempre` y `peticion`, separados por comas.
   - Un revisor responde con el formato común: `## Jugador: <name> (#<dorsal>)`, una línea de veredicto y hallazgos con `archivo:línea` y evidencia (como el `checker`).
2. **Valida la plantilla:** `.venv/bin/factory team validate` debe terminar en 0, y `factory team list` debe mostrar el fichaje en su puesto.
3. **Haz una prueba real barata con haiku** y comprueba que el agente carga y que, si es revisor, `git status --porcelain` no cambia:

   ```bash
   claude -p --agent <name> --model haiku --max-budget-usd 0.05 \
     --permission-mode dontAsk --no-session-persistence --output-format json "<tarea mínima>"
   ```
4. **Añade su test** autocontenido (`tests/test_team_<name>.py`), que lea el frontmatter y compruebe su contrato.
5. **Opcional:** si el fichaje cambia el reglamento, propónlo como cambio OpenSpec (`/opsx:propose`).

## El partido

El reglamento está en `.claude/skills/equipo/SKILL.md`. Resumen:

| Fase | Quién | Qué |
|---|---|---|
| 1. Convocatoria | técnico | reúne el contexto, ejecuta `factory team lineup`, ajusta justificando cada alta o baja y **publica la alineación antes de invocar a nadie** |
| 2. Pre-partido | `producto`, `qa` | preguntas, criterios WHEN/THEN y plan de pruebas; las preguntas abiertas van al humano **antes de construir** |
| 3. Construcción | `ingeniero-software` | implementa con los criterios, el plan y las respuestas |
| 4. Verificación | técnico | `./scripts/check.sh` y, si juega `metricas`, `factory complexity --base <ref> --json` |
| 5. Revisión | revisores convocados | en paralelo; cada uno recibe solo criterios, diff y verificación |
| 6. Documentación | `documentador` | actualiza los `*.md` afectados |
| 7. Acta | técnico | tabla por jugador y veredicto global; `fail` vuelve a construcción, **máximo 3 vueltas** |
| 8. Árbitro | sesión principal | invocar al `checker` antes de `factory features verify` |

- **Sin petición** (un diff ya hecho en el árbol) se saltan el pre-partido y la construcción.
- **Hallazgos sin `archivo:línea` o sin evidencia** no cuentan: el técnico pide que se concreten.
- **Un veredicto ambiguo** (sin exactamente una línea de veredicto, o con dos contradictorias) cuenta como `fail` hasta que el jugador lo aclare.
- **Revisores sin efectos:** el técnico compara `git status --porcelain` antes y después de cada tanda. Si cambia, descarta esos veredictos.

### Partido de revisión

Para una rama ya hecha: propia, ajena o una `factory/<run-id>` antes de `factory land`.

- Se juegan la convocatoria, la verificación, la revisión y el acta, **sin modificar ningún archivo**.
- El diff usa tres puntos, contra la merge-base: `git diff main...<rama>` y `git log main..<rama>`.
- Cada revisor recibe la lista de archivos cambiados (`git diff --name-only main...<rama>`) y lee cada archivo completo, no solo los hunks.
- La verificación se ejecuta sobre el código de la rama: en el checkout si es esa rama o, si no, en un worktree temporal fuera del repo.
- En una rama de un loop, los criterios salen de su `goal.md`. Los revisores reciben solo `goal.md`, `rounds/<n>/checks.md` y `land/checks.md`; nunca `decision.md`, `loop-state.md`, `rounds/<n>/maker.md` ni `rounds/<n>/review.md`.

## Árbitro frente a equipo

| | Equipo | Árbitro |
|---|---|---|
| Quién | `tecnico` y los convocados | `checker` (`.claude/agents/checker.md`) |
| Pregunta | ¿qué riesgos tiene este cambio, especialidad por especialidad? | ¿está terminada esta feature? |
| Cuándo | cuando pides `/equipo` | siempre, antes de `factory features verify` |
| Salida | acta del partido | veredicto con hallazgos |

El acta, aunque termine en `pass`, **no sustituye** al árbitro. Ver [Roles](roles.md).

## Comandos

| Comando | Qué hace |
|---|---|
| `/equipo <petición, rama o descripción>` | la sesión principal hace de técnico y juega el partido |
| `claude --agent tecnico "<…>"` | arranca Claude Code con el técnico como agente principal |
| `factory team list [--json]` | formación por líneas, vacantes, técnico y árbitro |
| `factory team validate [--json]` | comprueba el frontmatter de la plantilla (también lo hace `factory doctor`) |
| `factory team lineup [--base REF] [--paths P…] [--peticion TEXTO \| --peticion-file F] [--json]` | convocatoria sugerida, con el motivo de cada jugador |
| `factory complexity [RUTAS…] [--base REF] [--max N] [--json]` | complejidad ciclomática por función (rangos A–F) y delta frente a `REF` |

No lances al técnico como subagente (`subagent_type: tecnico`). Un subagente no puede invocar a otros, así que el técnico solo dirige desde la sesión principal o como agente principal.

## Costes

- Los subcomandos `factory team` y `factory complexity` son deterministas y no cuestan nada.
- Cada convocado es una invocación de subagente, y cada vuelta o petición de concreción, otra más. Por eso existe la convocatoria: el técnico convoca lo mínimo que cubra el riesgo.
- `seguridad`, `revisor-pr`, `producto` y el técnico usan opus; `qa`, `documentador`, `metricas` e `ingeniero-software`, sonnet.
- Las pruebas reales de cada agente usan haiku con `--max-budget-usd 0.05`.

## Protección

Las definiciones del equipo son archivos críticos del harness en los loops (D7):

- `.claude/agents/**` y `.claude/skills/**` están en `STATIC_CRITICAL`. Si el maker de `factory goal run` o `factory tick` modifica, borra o renombra un agente o una skill existentes, el orquestador lo revierte.
- Nadie puede liberarlos: siguen protegidos en cada ronda aunque un objetivo los nombre. Además, `goal validate` rechaza un `scope.allow_modify` que los cubra (`.claude/**`) o que apunte dentro de ellos (`.claude/agents/qa.md`); un comodín que solo los solapa en parte (`**/LICENSE`) no se detecta al validar.
- Crear archivos nuevos en esas rutas sigue permitido, como en el resto de rutas protegidas. Ver [Loops](loops.md#rutas-protegidas).

---
Diseño y requisitos en `openspec/changes/add-equipo-ideal/` (D1–D9). `seguridad` se basa en cloudflare/security-audit-skill (MIT). Las reglas del veredicto ambiguo y del rango con tres puntos se inspiran en gentleman-guardian-angel (Gentleman-Programming, MIT).
