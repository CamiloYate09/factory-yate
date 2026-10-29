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

También puedes llamarlo con la ruta completa: `/ruta/a/factory-yate/.venv/bin/factory`.

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
   - **Ojo en proyectos Python:** la línea detectada es `python3 -m pip install -e .`, que instala en el Python **global**. Cámbiala por un entorno virtual, por ejemplo `python3 -m venv .venv && .venv/bin/pip install -e .`.
2. `./init.sh` debe terminar en 0.
3. `factory --root . doctor` no debe mostrar críticas fallidas.
4. `git add -A && git commit -m "Harness de factory"`. Los loops necesitan al menos un commit en `main`.
5. Recomendado: protege tus tests en `factory.toml` con `protected_paths = ["tests/**"]`, para que ningún loop pueda debilitar o borrar los existentes (sí puede añadir nuevos).

`factory init` crea `AGENTS.md`, `CLAUDE.md`, `feature_list.json`, `progress.md`, `session-handoff.md`, `init.sh`, `scripts/check.sh`, `factory.toml`, los prompts de los roles, la plantilla de objetivo y la checklist de clean state.

- **Archivos existentes:** **no sobrescribe** ninguno sin `--force`; los omitidos aparecen en la salida.
- **Verificación:** los comandos detectados, o los de `--commands`, se agrupan en `scripts/check.sh`, la ruta única. Si no se detecta ninguno, la verificación falla a propósito hasta que la definas.
- **`factory doctor`:** evalúa los cinco subsistemas (instrucciones, estado, verificación, alcance y ciclo de vida) y sale con código distinto de cero si falla alguna comprobación crítica.

### D. Primer objetivo con un loop

```bash
cp goals/_template.md goals/mi-objetivo.md        # edita objetivo, criterios (comandos), alcance y límites
factory goal validate goals/mi-objetivo.md        # límites efectivos
factory goal run goals/mi-objetivo.md --dry-run   # plan completo, sin agentes ni coste
factory goal run goals/mi-objetivo.md             # ejecución real (cuesta dinero)
factory inbox list                                # resultado pendiente de tu revisión
factory status                                    # ejecuciones y costes silenciosos
```

El resultado queda en una rama `factory/<run-id>`. El loop **nunca** integra en `main` ni hace push.

### E. Revisar el resultado y continuar

```bash
factory inbox list                                     # qué terminó y por qué
cat .factory/runs/<run-id>/decision.md                 # RESULT, REASON, BRANCH, BEST_ROUND
cat .factory/runs/<run-id>/rounds/1/checks.md          # verificación de cada ronda (también maker.md y review.md)
git diff main...factory/<run-id>                       # qué cambió
factory goal rework <run-id> --answer "tu respuesta"   # si quedó bloqueada o sin terminar: continúa desde su rama
factory land <run-id> --dry-run                        # si terminó completed: verifica el merge sobre el main actual
factory land <run-id>                                  # e integra en main (merge --no-ff, sin push; marca la bandeja)
```

Para descartar una ejecución: `git branch -D factory/<run-id>` y `factory inbox ack <run-id>`.

### F. De una idea a un objetivo, con triaje (opcional)

Si prefieres describir lo que quieres en lenguaje natural en lugar de escribir el `goal.md`:

```bash
factory intake "Añade la función restar con su test"          # ACCEPT → borrador en goals/drafts/
factory intake --answer <request-id> "tu respuesta"           # si contestó NEEDS-INFO
factory goal promote goals/drafts/<id>.md                     # revisa los comandos que se ejecutarían
factory goal promote goals/drafts/<id>.md --yes               # crea goals/<id>.md
factory goal run goals/<id>.md --dry-run                      # y sigue con el paso D
```

El intake usa `claude` (cuesta dinero), solo lee el repo y nunca ejecuta comandos. Un borrador no se puede ejecutar hasta que lo promueves.

### G. Cerebros de conocimiento (opcional)

Dos bibliotecas en Markdown que los loops consultan en solo lectura. Detalle en [docs/harness/cerebros.md](docs/harness/cerebros.md).

> ⚠️ **Los libros no se versionan.** El cerebro principal (`brain-principal/`) contiene libros de terceros: `import` lo añade a `.gitignore` y `factory doctor` falla si algo suyo llega a git. En un equipo nuevo hay que **volver a importarlo** desde tu copia local del vault. Solo se copian archivos `.md` y sus índices; los PDF se descartan (`*.pdf` está en `.gitignore`).

```bash
# 1. Cerebro principal: copia filtrada del vault de libros (repite el comando para refrescarlo)
factory brain import /ruta/redPDF/book/obsidian-vault
factory brain status                                  # notas, libros, tokens y fecha de importación

# 2. Buscar (el principal está en inglés: busca en inglés)
factory brain search "rate limiting"
factory brain search "token bucket" --brain principal --limit 5

# 3. Cerebro diario: lo que aprendes tú (sí se versiona, en brain-diario/)
factory brain learn "En macOS no existe timeout; usar el de la herramienta" --kind gotcha --tags macos

# 4. Revisar lo que proponen los loops al terminar
factory brain pending                                 # capturas pendientes (también en factory status)
factory brain accept <id>                             # o: factory brain reject <id>

# 5. Commitear SOLO el cerebro diario (sin push)
factory brain commit -m "aprendizajes de hoy"
```

Para que un objetivo reciba conocimiento, declara consultas en inglés en su `goal.md` (el intake las propone solo):

```yaml
knowledge:
  queries: ["rate limiting", "api gateway"]
```

El maker recibe las notas más relevantes como texto citado (máximo `[brain] inject_max_tokens`, 3.000 por defecto); el checker no recibe nada.

## Loops

Ver [docs/harness/loops.md](docs/harness/loops.md):

- `factory goal run goals/<id>.md` ejecuta un objetivo finito con maker y checker separados, en un worktree fuera del repo. Nunca hace merge ni push.
- `factory tick goals/<id>.md` vigila un objetivo: verifica gratis y solo invoca agentes si algo falla.
- `factory status` y `factory inbox list` sirven para revisar los resultados y los costes silenciosos.

## Cómo está organizado

| Ruta | Qué es |
|---|---|
| `AGENTS.md` / `CLAUDE.md` | instrucciones de entrada (router corto) para cualquier agente / para Claude Code |
| `docs/harness/` | documentos temáticos: verificación, features, sesiones, roles, clean state |
| `feature_list.json` | fuente de verdad del trabajo: comportamiento, comandos de verificación, estado y evidencia |
| `progress.md`, `session-handoff.md` | continuidad entre sesiones |
| `init.sh`, `scripts/check.sh` | rutas estándar de arranque y verificación |
| `src/factory/` | paquete y CLI `factory` |
| `.claude/agents/checker.md` | revisor independiente de solo lectura para sesiones interactivas |
| `openspec/` | specs principales en `openspec/specs/` (8 capacidades); los cambios que construyeron todo esto están en `openspec/changes/archive/` |

## Reglas clave

- **WIP=1**: una sola feature activa.
- Una feature solo pasa a `passing` con `factory features verify <id>`, que ejecuta sus comandos y registra la evidencia. Editar el estado a mano rompe `./scripts/check.sh`.
- Quien implementa nunca es quien aprueba: el checker es independiente y de solo lectura.
- Cada sesión termina en *clean state* ([lista](docs/harness/clean-state-checklist.md)).

## Atribución

El diseño y las plantillas se adaptan del curso [Learn Harness Engineering](https://walkinglabs.github.io/learn-harness-engineering/es/) de walkinglabs ([repositorio](https://github.com/walkinglabs/learn-harness-engineering), licencia MIT). Se basan sobre todo en las lecciones 1–13 y el proyecto 07 (loop engineering).
