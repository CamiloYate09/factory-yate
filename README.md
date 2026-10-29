# factory-yate

Una "fábrica" para que los agentes de codificación (Claude Code) trabajen **de forma fiable** y, después, **de forma autónoma**.

- **Fase 1: harness.** Instrucciones, estado, verificación, alcance y ciclo de vida. Hace fiable cada ejecución individual: el agente sabe cómo arrancar, qué hacer, cómo comprobar que terminó y cómo dejar el repo listo para la siguiente sesión.
- **Fase 2: motor de loops `factory`.** Un CLI Python que orquesta `claude -p` con un rol maker y un rol checker separados. Ofrece:
  - `factory goal run`: ejecuta un objetivo hasta cumplirlo o detenerse por un motivo explícito;
  - `factory tick`: vigilancia periódica que solo gasta tokens si algo falla;
  - `factory init` y `factory doctor`: aplican y auditan el harness en otros repos.

El humano pasa de escribir cada instrucción a definir objetivos y revisar resultados. Los loops nunca integran en `main` ni hacen push.

## Qué necesitas en tu computador

| Herramienta | Versión | Para qué | Comprobar |
|---|---|---|---|
| macOS o Linux | — | `bash`, `flock` y worktrees de git (Windows solo con WSL) | — |
| Python | ≥ 3.12 | el CLI `factory` y sus tests | `python3 --version` |
| git | ≥ 2.30 | ramas y worktrees de cada ejecución | `git --version` |
| Claude Code (`claude`) | ≥ 2.1, con sesión iniciada | **solo** para los loops reales (`goal run`, `tick` con fallo, `intake`); cuestan dinero | `claude --version` |
| OpenSpec (`openspec`) | opcional | planificar cambios con `/opsx:*` | `openspec --version` |
| uv | opcional | si está instalado, `init.sh` lo usa en lugar de `pip` | `uv --version` |

## Paso a paso

Elige el paso según lo que quieras hacer. A y D son la base; el resto se añade cuando lo necesites.

| Quiero… | Paso | ¿Cuesta dinero? |
|---|---|---|
| tener factory-yate funcionando en este equipo | [A](#a-poner-en-marcha-factory-yate-en-un-equipo-nuevo) | no |
| usar `factory` desde cualquier carpeta | [B](#b-instalar-factory-para-usarlo-desde-otros-proyectos) | no |
| llevar el harness a otro proyecto | [C](#c-aplicar-el-harness-a-otro-proyecto) | no |
| trabajar una tarea en una sesión, con o sin Claude Code | [D](#d-trabajar-una-feature-en-una-sesión) | solo si usas Claude Code |
| delegar una tarea completa a un loop | [E](#e-escribir-un-buen-objetivo-goalmd) → [F](#f-ejecutar-un-objetivo-con-un-loop) → [G](#g-revisar-el-resultado-y-continuar) | sí (`goal run`) |
| describir la tarea en lenguaje natural | [H](#h-de-una-idea-a-un-objetivo-con-triaje-opcional) | sí (`intake`) |
| vigilar que el repo siga en verde | [I](#i-vigilancia-con-factory-tick-opcional) | solo si algo falla |
| consultar los libros y guardar lo aprendido | [J](#j-cerebros-de-conocimiento-opcional) | no |
| planificar un cambio grande con specs | [K](#k-planificar-cambios-grandes-con-openspec-opcional) | solo si usas Claude Code |

> Los ejemplos escriben `factory`. Si no activaste el entorno ni lo instalaste (paso B), usa `.venv/bin/factory`.

### A. Poner en marcha factory-yate en un equipo nuevo

```bash
git clone <url-de-tu-repo> factory-yate     # o copia la carpeta del proyecto
cd factory-yate
./init.sh                                    # crea .venv, instala y verifica (debe terminar en "Verificación completa: OK")
.venv/bin/factory --version                  # factory 0.1.0
.venv/bin/factory doctor                     # 0 críticas fallidas
source .venv/bin/activate                    # opcional: usar `factory` sin escribir .venv/bin/
```

Si vas a usar loops reales, abre `claude` una vez para iniciar sesión y comprueba `claude --version`.

### B. Instalar `factory` para usarlo desde otros proyectos

`factory` vive en el `.venv` de factory-yate. Para usarlo en otros repos sin depender de esa carpeta, instálalo en un entorno propio:

```bash
python3 -m venv ~/.factory-venv
~/.factory-venv/bin/pip install /ruta/a/factory-yate     # instalación normal (no editable)
export PATH="$HOME/.factory-venv/bin:$PATH"              # añádelo a ~/.zshrc o ~/.bashrc
factory --version
```

También puedes llamarlo con la ruta completa: `/ruta/a/factory-yate/.venv/bin/factory`. Para trabajar sobre otro repo sin entrar en él, usa `factory --root /ruta/al/repo <comando>`.

### C. Aplicar el harness a otro proyecto

```bash
cd /ruta/a/otro-proyecto
git init -b main                                  # si aún no es un repo git
factory init --target .                           # detecta Makefile / package.json / pyproject
# o, indicando tú la verificación:
factory init --target . --commands "make lint,make test"
```

Después:

1. Completa los marcadores `TODO(factory)` que lista la salida: la descripción en `AGENTS.md`, la feature de ejemplo en `feature_list.json` y la línea de instalación de `init.sh`.
   - **En proyectos Python** (`pyproject.toml`), `init.sh` ya crea un `.venv` propio (con `uv` si está instalado; si no, con `python3 -m venv`) e instala ahí el proyecto con `pip install -e .`. La verificación corre dentro de ese entorno y nunca toca el Python global.
2. `./init.sh` debe terminar en 0.
3. `factory --root . doctor` no debe mostrar críticas fallidas.
4. `git add -A && git commit -m "Harness de factory"`. Los loops necesitan al menos un commit en `main`.
5. Recomendado: protege tus tests en `factory.toml` con `protected_paths = ["tests/**"]`, para que ningún loop pueda debilitar o borrar los existentes (sí puede añadir nuevos).

`factory init` crea `AGENTS.md`, `CLAUDE.md`, `feature_list.json`, `progress.md`, `session-handoff.md`, `init.sh`, `scripts/check.sh`, `factory.toml`, los prompts de los roles, la plantilla de objetivo y la checklist de clean state.

- **Archivos existentes:** **no sobrescribe** ninguno sin `--force`; los omitidos aparecen en la salida.
- **Verificación:** los comandos detectados, o los de `--commands`, se agrupan en `scripts/check.sh`, la ruta única. Si no se detecta ninguno, la verificación falla a propósito hasta que la definas.
- **`factory doctor`:** evalúa los cinco subsistemas (instrucciones, estado, verificación, alcance y ciclo de vida) y sale con código distinto de cero si falla alguna comprobación crítica.

### D. Trabajar una feature en una sesión

Este es el uso diario del harness, con Claude Code en modo interactivo o a mano. Cada tarea es una **feature** de `feature_list.json`: comportamiento visible + comandos de verificación + estado. Detalle en [docs/harness/features.md](docs/harness/features.md) y [docs/harness/sesiones.md](docs/harness/sesiones.md).

**1. Añadir la feature** (si aún no existe). Edita `feature_list.json` y añade una entrada con `status: "not_started"` y `evidence: []`:

```json
{
  "id": "exportar-csv",
  "priority": 30,
  "title": "Exportar el informe a CSV",
  "user_visible_behavior": "`app export --csv` escribe informe.csv con una fila por registro",
  "status": "not_started",
  "verification": ["python -m pytest -q tests/test_export.py"],
  "evidence": []
}
```

```bash
factory features validate                # esquema, WIP=1 y evidencia
```

**2. Empezar la sesión** (lo mismo que hace un agente al leer `AGENTS.md`):

```bash
pwd                                      # raíz del repo
cat progress.md                          # estado verificado y siguiente paso
factory features list                    # la feature in_progress o la de mayor prioridad
git log --oneline -5
./init.sh                                # si la referencia ya falla, arréglala antes de seguir
factory features start exportar-csv      # la marca in_progress (falla si ya hay otra: WIP=1)
```

Con Claude Code basta con abrir `claude` en la raíz y pedirlo en una frase: *"trabaja en la feature exportar-csv"*. `CLAUDE.md` y `AGENTS.md` le indican estos mismos pasos.

**3. Implementar y verificar a menudo:**

```bash
./scripts/check.sh                       # lint, formato, tests y doctor; debe terminar en 0
```

**4. Pedir revisión independiente.** En Claude Code, pide *"revisa los cambios con el subagente checker"*. El `checker` (`.claude/agents/checker.md`) solo lee: recibe el diff y los criterios de la feature, no el razonamiento de quien implementó. Corrige los hallazgos `critical` y `medium` y vuelve a pedir revisión.

**5. Promover la feature:**

```bash
factory features verify exportar-csv     # ejecuta `verification`; si pasa, queda en passing con evidencia
```

Nunca cambies a mano `status` ni `evidence`: `doctor` y `check.sh` detectan la promoción manual. El único cambio manual permitido es marcarla `blocked` y explicar el motivo en `notes` y en `progress.md`.

**6. Cerrar la sesión** ([lista de clean state](docs/harness/clean-state-checklist.md)):

- `./scripts/check.sh` en verde; si no lo está, documenta el fallo como riesgo en `progress.md`;
- añade a `progress.md` la entrada de la sesión: qué se hizo, qué comandos lo verifican y el mejor próximo paso. Si la sesión fue larga, actualiza también `session-handoff.md`;
- haz el commit tú (`git add … && git commit`). Ningún agente hace push.

### E. Escribir un buen objetivo (`goal.md`)

Un objetivo es una tarea que delegas a un loop. Cuanto más verificable sea, mejor termina el loop. Parte de la plantilla:

```bash
cp goals/_template.md goals/exportar-csv.md
```

Campos del frontmatter:

| Campo | Qué poner | Consejo |
|---|---|---|
| `id` | minúsculas, dígitos y guiones | igual que el nombre del archivo |
| `objective` | una frase: qué cuenta como terminado | si no cabe en una frase, divídelo en varios objetivos |
| `mode` | `finite` (para `goal run`) o `monitor` (para `tick`) | |
| `feature` | id de `feature_list.json` (opcional) | al completar, la feature se promueve a `passing` en la rama |
| `acceptance` | lista de `{name, run}`: comandos que terminan en 0 cuando se cumple | el orquestador los ejecuta él mismo; lo que diga el agente no cuenta |
| `scope.allow` / `scope.deny` | globs de lo que el maker puede y no puede tocar | lo más estrecho posible |
| `scope.protected` / `allow_modify` | archivos existentes intocables / excepciones para este objetivo | |
| `stop` | `max_rounds`, `max_budget_usd`, `no_progress_rounds`, `consecutive_passes`, `round_timeout_min` | empieza con poco presupuesto (1–2 USD) |
| `roles` | modelo y permisos por rol (opcional) | por defecto, maker `sonnet` y checker `opus` |
| `knowledge` | `queries` en inglés para los cerebros (paso J) | opcional |

Debajo del frontmatter escribe **Contexto** (enlaza documentos, no los copies), **Cómo trabajar** y **Fuera de alcance**.

Hay rutas que ningún loop puede tocar, sin importar el objetivo: `feature_list.json`, `factory.toml`, `prompts/**`, el script de verificación, las rutas de `protected_paths` y las carpetas de los cerebros.

```bash
factory goal validate goals/exportar-csv.md       # errores de formato y límites efectivos
```

### F. Ejecutar un objetivo con un loop

```bash
factory goal run goals/exportar-csv.md --dry-run   # plan completo, sin agentes ni coste
factory goal run goals/exportar-csv.md             # ejecución real (cuesta dinero)
factory status                                     # ejecuciones en curso y costes silenciosos
factory inbox list                                 # resultado pendiente de tu revisión
```

Qué pasa en cada ronda:

1. El maker trabaja en un **worktree fuera del repo**, en la rama `factory/<run-id>`.
2. factory deshace lo que se salga del alcance y ejecuta los criterios de `acceptance`.
3. El checker revisa el diff en solo lectura, con otro modelo.
4. El loop para cuando los criterios pasan y el checker aprueba, o por un motivo explícito: rondas, presupuesto, falta de progreso o una pregunta para ti.

Antes de lanzarlo: `main` necesita al menos un commit, y la ejecución parte del **último commit**, no de tus cambios sin commitear. El loop **nunca** integra en `main` ni hace push.

### G. Revisar el resultado y continuar

```bash
factory inbox list                                     # qué terminó y por qué
cat .factory/runs/<run-id>/decision.md                 # RESULT, REASON, BRANCH, BEST_ROUND
cat .factory/runs/<run-id>/rounds/1/checks.md          # verificación de cada ronda (también maker.md y review.md)
git diff main...factory/<run-id>                       # qué cambió
```

Según el resultado (código de salida entre paréntesis):

| Resultado | Qué significa | Qué hacer |
|---|---|---|
| `completed` (0) | criterios en verde y checker conforme | revisar el diff e integrar con `factory land` |
| `blocked` (6) | el maker te hizo una pregunta | contestar con `factory goal rework <run-id> --answer "…"` |
| `max_rounds` (4), `stalled` (3) | se acabaron las rondas / sin progreso | leer `decision.md`; rework con una pista, o reescribir el objetivo |
| `budget_exhausted` (5) | se alcanzó el presupuesto | rework con `--budget`, o acotar el objetivo |
| `agent_error` (7), `interrupted` (130) | falló `claude` o se interrumpió | revisar la sesión de `claude` y repetir con rework |

```bash
factory goal rework <run-id> --answer "tu respuesta"   # continúa desde su rama (también --rounds y --budget)
factory land <run-id> --dry-run                        # solo completed: verifica el merge sobre el main actual
factory land <run-id>                                  # integra en main (merge --no-ff, sin push; marca la bandeja)
factory land <run-id> --delete-branch                  # además borra la rama ya integrada
```

`land` exige que el checkout principal esté en `main` y sin cambios en archivos versionados. Para descartar una ejecución: `git branch -D factory/<run-id>` y `factory inbox ack <run-id>`. Detalle en [docs/harness/revision.md](docs/harness/revision.md).

### H. De una idea a un objetivo, con triaje (opcional)

Si prefieres describir lo que quieres en lenguaje natural en lugar de escribir el `goal.md`:

```bash
factory intake "Añade la función restar con su test"          # ACCEPT → borrador en goals/drafts/
factory intake --answer <request-id> "tu respuesta"           # si contestó NEEDS-INFO
factory goal promote goals/drafts/<id>.md                     # revisa los comandos que se ejecutarían
factory goal promote goals/drafts/<id>.md --yes               # crea goals/<id>.md
factory goal run goals/<id>.md --dry-run                      # y sigue con el paso F
```

El intake usa `claude` (cuesta dinero, 1 USD como máximo por defecto; cámbialo con `--budget`), solo lee el repo y nunca ejecuta comandos. Un borrador no se puede ejecutar hasta que lo promueves.

### I. Vigilancia con `factory tick` (opcional)

Un objetivo con `mode: monitor`, como `goals/vigilancia-check.md`, vigila que unos criterios sigan en verde. Cada tick **verifica primero sin agentes y con coste 0**; solo si algo falla lanza un loop acotado, que deja una rama para revisar (paso G).

```bash
factory tick goals/vigilancia-check.md                    # un tick: noop si todo pasa
factory schedule goals/vigilancia-check.md --every 30m    # imprime cron, launchd y /loop (no instala nada)
factory tick goals/vigilancia-check.md --reset-breaker    # tras revisar un escalado (circuit_open)
```

Copia la opción de `schedule` que prefieras: cron o launchd para que corra solo, o `/loop` mientras tienes Claude Code abierto. Los límites están en `[tick]` de `factory.toml`: rondas, presupuesto por tick y por día, y cuántos fallos seguidos abren el cortacircuitos. Vigila sobre un árbol limpio: el tick verifica tu árbol de trabajo, pero el loop parte del último commit. Detalle en [docs/harness/vigilancia.md](docs/harness/vigilancia.md).

### J. Cerebros de conocimiento (opcional)

Dos bibliotecas en Markdown que los loops consultan en solo lectura. Detalle en [docs/harness/cerebros.md](docs/harness/cerebros.md).

**Qué trae el repo al clonarlo:**
- el **mapa de la biblioteca** (`brain-mapa/`): libros, capítulos, secciones, páginas y keywords, sin texto. `factory brain search` funciona desde el primer momento y devuelve citas.
- el **cerebro diario** (`brain-diario/`): fichas escritas con tus palabras.

> ⚠️ **Los libros no se versionan.** El texto completo (`brain-principal/`) es de terceros: `import` lo añade a `.gitignore` y `factory doctor` falla si algo suyo llega a git, o si el mapa contiene texto. Lleva tu copia del vault a cada equipo tuyo y **impórtala** allí. Solo se copian archivos `.md` y sus índices; los PDF se descartan (`*.pdf` está en `.gitignore`).

```bash
# 1. (Opcional, en tus equipos) Texto completo: copia filtrada de tu vault de libros.
#    Regenera también el mapa; repítelo para refrescarlo.
factory brain import /ruta/redPDF/book/obsidian-vault
factory brain status                                  # principal (si está), mapa y fecha de importación

# 2. Buscar (el principal está en inglés: busca en inglés)
factory brain search "rate limiting"
factory brain search "token bucket" --brain principal --limit 5

# 3. Cerebro diario: lo que aprendes tú (sí se versiona, en brain-diario/)
factory brain learn "En macOS no existe timeout; usar el de la herramienta" --kind gotcha --tags macos
factory brain reindex                                 # si editas una ficha a mano

# 4. Revisar lo que proponen los loops al terminar
factory brain pending                                 # capturas pendientes (también en factory status)
factory brain accept <id>                             # o: factory brain reject <id>

# 5. Commitear SOLO el cerebro diario y el mapa (sin push)
factory brain commit -m "aprendizajes de hoy"
```

Para que un objetivo reciba conocimiento, declara consultas en inglés en su `goal.md` (el intake las propone solo):

```yaml
knowledge:
  queries: ["rate limiting", "api gateway"]
```

El maker recibe las notas más relevantes como texto citado (máximo `[brain] inject_max_tokens`, 3.000 por defecto); el checker no recibe nada. En un equipo sin el texto de los libros, el maker solo recibe las citas del mapa.

### K. Planificar cambios grandes con OpenSpec (opcional)

Para algo que ocupa varias features, primero escribe la spec y después implementa. Dentro de Claude Code:

1. `/opsx:propose <idea>`: crea `openspec/changes/<cambio>/` con la propuesta, las specs delta, el diseño y las tareas.
2. Revisa esos archivos y ajústalos con `/opsx:update` si hace falta.
3. `/opsx:apply <cambio>`: implementa las tareas. En este repo, cada grupo de tareas se registra como una feature y sigue el paso D.
4. `/opsx:archive <cambio>`: con todo en `passing`, pasa las specs delta a `openspec/specs/` y mueve el cambio a `openspec/changes/archive/`.

`openspec validate <cambio> --strict` comprueba el formato en cualquier momento.

## Referencia rápida de comandos

| Comando | Qué hace | Coste |
|---|---|---|
| `factory doctor [--json]` | audita el harness en sus cinco subsistemas | 0 |
| `factory init --target <dir> [--commands …] [--force]` | genera el harness en otro repo | 0 |
| `factory features list \| validate \| start <id> \| verify <id>` | ver, validar, activar y promover features | 0 |
| `factory goal validate <goal.md>` | valida un objetivo y muestra los límites | 0 |
| `factory goal run <goal.md> [--dry-run]` | loop maker/checker hasta cumplir o parar | `claude` |
| `factory goal rework <run-id> --answer …` | continúa una ejecución no completada | `claude` |
| `factory goal promote <borrador> [--yes]` | convierte un borrador del intake en objetivo | 0 |
| `factory intake "<petición>"` | triaje: ACCEPT, NEEDS-INFO o REJECT | `claude` |
| `factory tick <goal.md> [--reset-breaker]` | vigilancia; agentes solo si falla | 0 o `claude` |
| `factory schedule <goal.md> --every 30m` | imprime cómo programar los ticks | 0 |
| `factory status` | ejecuciones, ticks, avisos y costes silenciosos | 0 |
| `factory inbox list [--all] \| ack <run-id>` | bandeja de revisión humana | 0 |
| `factory land <run-id> [--dry-run] [--delete-branch]` | integra en `main` una ejecución completed | 0 |
| `factory brain import \| status \| search \| learn \| reindex \| pending \| accept \| reject \| commit` | cerebros de conocimiento | 0 |

Todos aceptan `--root <repo>` antes del subcomando. Más detalle en [docs/harness/loops.md](docs/harness/loops.md) y [docs/harness/observabilidad.md](docs/harness/observabilidad.md).

## Buenas prácticas

- **Empieza en seco.** Primero `--dry-run` y presupuestos pequeños; súbelos cuando el objetivo funcione.
- **Criterios que se ejecutan.** Si un criterio no es un comando que termina en 0, el loop no puede saber si terminó.
- **Alcance estrecho.** Un `scope.allow` pequeño reduce rondas y coste. Protege los tests existentes con `protected_paths`.
- **Commitea antes de lanzar.** Los loops y `land` parten de `main`, no de tu árbol de trabajo.
- **Revisa antes de integrar.** `land` y `goal promote --yes` son decisiones tuyas; ningún agente las toma.
- **Mira `factory status` a menudo.** Avisa de bandejas acumuladas, crecimiento de tokens y cambios sin commitear en los cerebros.
- **Nunca omitas permisos.** `bypassPermissions` se rechaza al cargar la configuración; no uses `--dangerously-skip-permissions`.

## Problemas frecuentes

| Síntoma | Causa y solución |
|---|---|
| `factory: command not found` | usa `.venv/bin/factory`, `source .venv/bin/activate` o instálalo (paso B) |
| `./init.sh` o `./scripts/check.sh` fallan | lee la primera comprobación en rojo; guía en [docs/harness/verificacion.md](docs/harness/verificacion.md) |
| `features start` falla | ya hay otra feature `in_progress` (WIP=1): termínala o márcala `blocked` |
| `features verify` no promueve | algún comando de `verification` falla; la salida dice cuál |
| `doctor` marca una feature `passing` sin evidencia | alguien editó `status` o `evidence` a mano: deshaz ese cambio (`git diff feature_list.json`) y promuévela con `verify` |
| `goal validate` rechaza el objetivo | el mensaje nombra la clave; compara con `goals/_template.md` |
| el loop termina `completed` sin cambios | los criterios ya pasaban en el último commit de `main`: lo que fallaba estaba sin commitear |
| `land` se niega a integrar | no estás en `main`, hay cambios sin commitear o la ejecución no es `completed`; el mensaje dice cuál |
| `tick` responde `circuit_open` | varios ticks seguidos sin resolverlo: revisa la bandeja y usa `--reset-breaker` |
| `doctor` falla por el mapa de la biblioteca | alguien lo editó a mano: `git restore brain-mapa/` o `factory brain import` |

## Cómo está organizado

| Ruta | Qué es |
|---|---|
| `AGENTS.md` / `CLAUDE.md` | instrucciones de entrada (router corto) para cualquier agente / para Claude Code |
| `docs/harness/` | documentos temáticos: verificación, features, sesiones, roles, loops, revisión, vigilancia, cerebros |
| `feature_list.json` | fuente de verdad del trabajo: comportamiento, comandos de verificación, estado y evidencia |
| `progress.md`, `session-handoff.md` | continuidad entre sesiones |
| `init.sh`, `scripts/check.sh` | rutas estándar de arranque y verificación |
| `factory.toml` | configuración de factory: límites del loop, ticks, roles y cerebros |
| `goals/` | objetivos para los loops (`_template.md`, ejemplos y `drafts/` del intake) |
| `prompts/` | prompts de los roles maker y checker |
| `src/factory/` | paquete y CLI `factory` |
| `.claude/agents/checker.md` | revisor independiente de solo lectura para sesiones interactivas |
| `brain-mapa/`, `brain-diario/` | mapa de la biblioteca (sin texto) y cerebro diario, versionados |
| `brain-principal/` | texto de los libros, solo local (en `.gitignore`) |
| `.factory/` | estado local de ejecuciones, ticks y bandeja (no se versiona) |
| `openspec/` | specs principales en `openspec/specs/` (12 capacidades); los cambios que construyeron todo esto están en `openspec/changes/archive/` |

## Reglas clave

- **WIP=1**: una sola feature activa.
- Una feature solo pasa a `passing` con `factory features verify <id>`, que ejecuta sus comandos y registra la evidencia. Editar el estado a mano rompe `./scripts/check.sh`.
- Quien implementa nunca es quien aprueba: el checker es independiente y de solo lectura.
- Cada sesión termina en *clean state* ([lista](docs/harness/clean-state-checklist.md)).

## Atribución

El diseño y las plantillas se adaptan del curso [Learn Harness Engineering](https://walkinglabs.github.io/learn-harness-engineering/es/) de walkinglabs ([repositorio](https://github.com/walkinglabs/learn-harness-engineering), licencia MIT). Se basan sobre todo en las lecciones 1–13 y el proyecto 07 (loop engineering).
