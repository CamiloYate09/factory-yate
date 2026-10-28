# factory-yate

Una "fábrica" para que los agentes de codificación (Claude Code) trabajen **de forma fiable** y, después, **de forma autónoma**.

- **Fase 1: harness.** Instrucciones, estado, verificación, alcance y ciclo de vida. Hace fiable cada ejecución individual: el agente sabe cómo arrancar, qué hacer, cómo comprobar que terminó y cómo dejar el repo listo para la siguiente sesión.
- **Fase 2: motor de loops `factory`.** Un CLI Python que orquesta `claude -p` con un rol maker y un rol checker separados. Ofrece:
  - `factory goal run`: ejecuta un objetivo hasta cumplirlo o detenerse por un motivo explícito;
  - `factory tick`: vigilancia periódica que solo gasta tokens si algo falla;
  - `factory init` y `factory doctor`: aplican y auditan el harness en otros repos.

El humano pasa de escribir cada instrucción a definir objetivos y revisar resultados. Los loops nunca integran en `main` ni hacen push.

## Inicio rápido

Requiere Python ≥ 3.12 y git.

```bash
./init.sh                          # crea .venv, instala y ejecuta la verificación de referencia
./scripts/check.sh                 # verificación completa: lint, formato, tests y auditoría del harness
.venv/bin/factory doctor           # estado del harness por subsistema
.venv/bin/factory features list    # features por prioridad y estado
```

Los loops reales necesitan además el CLI `claude` (Claude Code ≥ 2.1) en el `PATH` y al menos un commit en `main`.

## Usar factory en otro repositorio

```bash
.venv/bin/factory init --target ../otro-proyecto                      # detecta Makefile / package.json / pyproject
.venv/bin/factory init --target ../otro-proyecto --commands "make lint,make test"
.venv/bin/factory --root ../otro-proyecto doctor                       # auditoría por subsistema (--json para CI)
```

`factory init` crea el harness mínimo: `AGENTS.md`, `CLAUDE.md`, `feature_list.json`, `progress.md`, `session-handoff.md`, `init.sh`, `scripts/check.sh`, `factory.toml`, los prompts de los roles, la plantilla de objetivo y la checklist de clean state.

- **Archivos existentes**: **no sobrescribe** ninguno sin `--force`; los omitidos aparecen en la salida.
- **Marcadores**: los textos `TODO(factory)` que hay que completar se listan al terminar.
- **Verificación**: los comandos detectados, o los que pases con `--commands`, se agrupan en `scripts/check.sh`, la ruta única. Si no se detecta ninguno, la verificación falla a propósito hasta que los definas.

`factory doctor` evalúa los cinco subsistemas (instrucciones, estado, verificación, alcance y ciclo de vida). Marca cada comprobación como crítica o recomendada y le adjunta una acción concreta. Señala el subsistema más débil y sale con un código distinto de cero si falla alguna crítica.

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
| `openspec/` | specs y cambios. El plan de este trabajo está en `openspec/changes/add-harness-loop-engine/` |

## Reglas clave

- **WIP=1**: una sola feature activa.
- Una feature solo pasa a `passing` con `factory features verify <id>`, que ejecuta sus comandos y registra la evidencia. Editar el estado a mano rompe `./scripts/check.sh`.
- Quien implementa nunca es quien aprueba: el checker es independiente y de solo lectura.
- Cada sesión termina en *clean state* ([lista](docs/harness/clean-state-checklist.md)).

## Atribución

El diseño y las plantillas se adaptan del curso [Learn Harness Engineering](https://walkinglabs.github.io/learn-harness-engineering/es/) de walkinglabs ([repositorio](https://github.com/walkinglabs/learn-harness-engineering), licencia MIT). Se basan sobre todo en las lecciones 1–13 y el proyecto 07 (loop engineering).
