# Design

## Context

Estado actual del código (`main` en `7563c8f` más el archivado del cambio anterior). Motivación: ver `proposal.md`.

- **Alcance de cada ronda.** `engine._round` compara los archivos cambiados desde el commit anterior a la ronda con `scope.allow` y `scope.deny` (`goal.out_of_scope`). Si hay violación, revierte con `Worktree.reset_to(pre_commit)` y registra `scope_revert`. `feature_list.json` está siempre en `deny`. No hay noción de "existía en la base": `deny` también impide **crear** archivos.
- **Dónde quedan los resultados.** El estado de cada ejecución está en `.factory/runs/<id>/`: `state.json`, `loop-state.md`, `events.jsonl` y una copia de `goal.md`. Las salidas del maker y del checker solo aparecen dentro de `events.jsonl`. El directorio `rounds/<n>/` que prometía el diseño D5 del cambio archivado **nunca se implementó**.
- **Worktrees.** `gitops.create_worktree(root, worktrees_dir, run_id, base)` siempre parte del commit base. Los worktrees viven fuera del repo (`../<repo>.factory-worktrees/`). Los comandos de verificación y el entorno del maker anteponen `<cwd>/src` a `PYTHONPATH` (`util.command_env`).
- **Roles.** `config.enforce_role_policy` impone denegaciones obligatorias (publicar, editar `feature_list.json`) y limita el checker a Read, Glob y Grep con `permission_mode = "dontAsk"`. Los overrides de `goal.md` pasan por la misma política.
- **Bandeja.** Las entradas tienen `kind` (`run` o `escalation`) y `origin` (`goal` o `tick`). Integrar una rama hoy es un `git merge` manual; en la sesión 003 se hizo así.
- **Otros detalles.**
  - El checker se omite si el presupuesto se agotó tras el maker.
  - Un error del motor dentro de un tick queda registrado como `run` con `run_status=error`.
  - El bloqueo del tick usa `flock`.
- **Referencia analizada.** *Software Factory v2* (GPLv3). Se adoptan sus patrones; no se copia código ni prompts.

## Goals / Non-Goals

**Goals:**
- Que ninguna rama pueda cambiar las reglas con las que se la juzga, ni debilitar tests existentes, sin que la ronda falle de forma determinista.
- Que cada ronda deje archivos legibles por humanos y parseables por scripts.
- Que el trabajo de una ejecución bloqueada se pueda retomar, y que integrar sea un comando verificado.
- Que una petición en lenguaje natural pase por un triaje antes de convertirse en objetivo, sin que lo que proponga un agente se ejecute sin revisión.

**Non-Goals:**
- Merge automático decidido por un agente. `land` solo lo invoca un humano.
- Enrutado por riesgo, revisores adicionales, agente aprobador, dashboard, hook `SubagentStop`, cola con concurrencia y GitHub: ver la sección "Aplazado" de la propuesta.
- Squash o rebase en `land`: solo merge `--no-ff`, para conservar las instantáneas por ronda.

## Decisions

### D1. Rutas protegidas: diff con estados contra la base, después de la instantánea
Tras el commit de instantánea de la ronda, el orquestador obtiene `git diff --name-status -M <base_commit>..HEAD`. Una entrada es violación cuando cumple todo lo siguiente:
- su estado es `M`, `D`, `T`, o `R`/`C`, en cuyo caso se evalúa la ruta **original**;
- esa ruta coincide con el conjunto protegido efectivo;
- no está liberada.

Las altas (`A`) nunca son violación. Si hay violación, se reutiliza el camino de `scope_revert`: `reset_to(pre_commit)`, la decisión `protected_revert`, una firma de estancamiento `protected:<rutas>` y retroalimentación que nombra cada archivo y el tipo de cambio.

- **Conjunto protegido efectivo** = críticos ∪ `[loop] protected_paths` ∪ `scope.protected` del objetivo, menos `scope.allow_modify`, que solo afecta a rutas no críticas.
- **Archivos críticos:**
  - `feature_list.json`, `factory.toml` y `prompts/**`;
  - el script de `harness.verify_command`;
  - el script de cada comando de `acceptance` cuyo primer token sea una ruta relativa existente en la base, por ejemplo `./scripts/check.sh`.
- **Por qué contra la base y no contra la ronda anterior:** también cubre la ejecución hija de un retrabajo (D3), que parte de una punta con rondas previas.
- **Por qué no ejecutar la copia del checkout principal** de los scripts, como hace la referencia: si los scripts críticos no pueden cambiar en la rama, la copia del worktree es idéntica a la de la base. La copia del checkout principal, en cambio, puede desfasarse cuando `main` avanza. En `land` (D4) el merge ya contiene la versión vigente de `main`.
- *Alternativa: ampliar `scope.deny`.* Se descarta porque `deny` impide crear archivos, y queremos permitir tests nuevos.

### D2. Artefactos por ronda generados por el orquestador
Los agentes siguen devolviendo JSON validado (`--json-schema`). Es el **orquestador** quien escribe los archivos de cada ronda a partir de `RoundRecord`, `Verification` y `Verdict`, así que no dependen de que un agente siga un formato de texto.

```
.factory/runs/<id>/rounds/<n>/maker.md    STATUS / MODEL / COST_USD   + resumen, archivos, riesgos
                               checks.md    GATE / COMMIT / SCORE / [REVERTED_TO] + rutas protegidas + criterios con final de salida
                               review.md    VERDICT / MODEL              + hallazgos (o motivo si omitido/inválido)
.factory/runs/<id>/decision.md              RESULT / REASON / BRANCH / BEST_ROUND / [PARENT] / [LANDED]
.factory/runs/<id>/land/checks.md           GATE / COMMIT / MAIN / BRANCH (lo escribe D4)
```

- **Formato.** Las cabeceras son líneas `CLAVE: valor` hasta la primera línea en blanco. Un helper `read_header(path)` las parsea; lo usan los tests y el futuro dashboard. Se escriben con `atomic_write_text`.
- **Fuentes de verdad.** `events.jsonl` sigue siendo el registro completo para máquinas. `state.json` sigue siendo la fuente de verdad del estado.

### D3. Retrabajo: ejecución hija desde la punta del padre
`factory goal rework <run-id> (--answer TEXTO | --answer-file F) [--rounds N] [--budget USD]`:

1. Exige que la ejecución padre esté en un estado final distinto de `completed` y que su rama exista.
2. Crea una ejecución hija con `parent_run_id`. Su `start_commit` es la punta de la rama del padre; su `base_commit` es el **base original** del padre.
3. Crea una rama nueva `factory/<run-id-hijo>` desde `start_commit`. `create_worktree` recibe un `start_point` opcional. La rama del padre no cambia.
4. Usa la copia de `goal.md` guardada en el estado del padre, porque el objetivo puede haber cambiado en `goals/`.
5. Hace la verificación base sobre `start_commit`, que pasa a ser la mejor ronda inicial.
6. Como primera retroalimentación del maker entrega: "Respuesta humana: …", la pregunta del padre si la hubo y las notas de su última ronda.
7. Marca la entrada de la bandeja del padre como revisada, con la nota `retrabajo → <run-id-hijo>`.

Los límites salen del objetivo, salvo que se indiquen `--rounds` o `--budget`. El diff acumulado del checker (`base_commit..HEAD`) incluye así las rondas del padre.

### D4. `factory land`: verificar el merge exacto y avanzar con `--ff-only`
Se implementa en un módulo nuevo `land.py`. Nunca ejecuta comandos de red.

1. **Precondiciones:**
   - el estado es `completed` y `landed_commit` está vacío;
   - existe `refs/heads/<branch>`;
   - en el checkout principal no hay cambios en archivos versionados (`git status --porcelain --untracked-files=no` vacío) y `git symbolic-ref --short HEAD` coincide con `main_branch`. Los archivos sin seguimiento (por ejemplo, un `goal.md` nuevo) no bloquean: si alguno chocara con el merge, `--ff-only` falla y se informa sin cambiar nada.
2. Lee `main_tip = rev-parse main`. Crea un worktree temporal **desacoplado** en `<worktrees_dir>/land-<run-id>` sobre `main_tip`. Ahí ejecuta `git merge --no-ff --no-edit -m "factory: integrar <run-id> (<goal-id>)" <branch>`.
   - Si hay conflicto, lista `git diff --name-only --diff-filter=U`, ejecuta `merge --abort`, elimina el worktree y falla.
3. Ejecuta, sobre el commit de merge `M`, los criterios de la copia de `goal.md` de la ejecución. Además comprueba las rutas protegidas del lado de la rama (`git diff --name-status merge-base(main_tip, branch)..branch`). Escribe `land/checks.md`.
4. Con `--dry-run`, se detiene aquí sin tocar nada más.
5. Comprueba de nuevo que `rev-parse main == main_tip` y que el checkout sigue limpio. Después ejecuta `git merge --ff-only M` en el checkout principal, de modo que `main` apunta **exactamente** al commit verificado.
6. Registra `landed_commit` en el estado de la ejecución, escribe `decision.md`, marca la entrada de la bandeja como revisada con el commit y elimina el worktree temporal. Con `--delete-branch`, borra la rama con `git branch -d`, que solo funciona si ya está integrada.

- **Identidad del commit.** El merge usa la identidad git del usuario. Si no hay ninguna configurada, usa la identidad de reserva de factory y lo avisa.
- *Alternativa: `git merge --no-ff` directamente en el checkout principal y revertir si falla.* Se descarta: tocaría el checkout del humano y verificaría un estado distinto del que queda integrado.

### D5. Intake con máquina de estados y borradores que no se ejecutan
Se implementan dos módulos nuevos, `intake.py` (agente y renderizado) y `requests.py` (estado). Cada petición vive en `.factory/requests/<req-id>/` con `request.md`, `state.json`, `intake.json`, `intake.md` y un historial `intake-<k>.md`.

- **Etapas de la petición.** `received → accepted | needs_info | rejected`, `needs_info → received` (con `--answer`), `accepted → promoted`. Un único escritor, `advance(req, etapa)`, valida contra una tabla `TRANSITIONS` y exige el archivo que justifica cada paso. Es el patrón "único escritor que rechaza movimientos ilegales" de la referencia, reescrito desde cero.
- **Rol `intake`.**
  - Se configura en `[roles.intake]`, con modelo por defecto `opus`: una sola invocación por petición y es la etapa que más criterio exige.
  - `enforce_role_policy` lo trata como al checker: solo lectura, `dontAsk` y las denegaciones obligatorias.
  - Su cwd es la raíz del repo, para que pueda leer `AGENTS.md`, código y specs.
  - El prompt de sistema es `prompts/intake.md`, escrito para este repo.
  - El prompt de usuario indica que lo que sigue es un dato citado y contiene la petición con prefijos `> `.
- **Esquema.** `decision`, `risk`, `surfaces[]`, `rescoped`, `scope`, `left_out[]`, `why`, `question` y un objeto `goal` con `objective`, `acceptance[{name, run}]`, `scope{allow, deny, protected}` y `body`. Se valida localmente igual que el veredicto.
- **Borrador.** Se escribe en `goals/drafts/<id>.md`, con el frontmatter de `goal.md` más `status: draft`, `request: <req-id>`, `risk` y `surfaces`.
  - `goal.py` acepta esas claves.
  - `goal run`, `tick` y también `LoopEngine` (defensa en profundidad) rechazan `status: draft` antes de ejecutar ningún criterio.
- **Promoción.** `factory goal promote <draft> [--yes]` muestra `describe()` del borrador y avisa si el ejecutable de un comando no existe en el `PATH` ni en el repo.
  - Sin `--yes`, no cambia nada.
  - Con `--yes`, escribe `goals/<id>.md` sin `status`, sin sobrescribir uno existente, y mueve la petición a `promoted`.
- **Bandeja.** `NEEDS-INFO` y `REJECT` crean entradas de bandeja con `kind = "request"`.

### D6. Dogfooding y orden
Cada grupo de tareas corresponde a una feature nueva en `feature_list.json`, igual que en el cambio anterior. Orden:
1. Rutas protegidas: es la base de seguridad y la usan D3 y D4.
2. Artefactos por ronda: D4 escribe `land/checks.md` con el mismo renderizador.
3. Retrabajo.
4. Integración.
5. Intake.

## Risks / Trade-offs

- **[Las rutas protegidas bloquean cambios legítimos de tests]** → `scope.allow_modify` por objetivo, visible en la validación y en la simulación. La protección por defecto de `tests/**` se activa en `factory.toml` de este repo, no en el código.
- **[La heurística para detectar el script de un comando falla]** (por ejemplo `bash tools/x.sh`) → se documenta. El objetivo puede añadirlo a `scope.protected`. El script de `verify_command` siempre se cubre.
- **[`land` en un repo con hooks de git]** → los hooks del repo se respetan en el merge del worktree temporal. Si fallan, la integración se rechaza como cualquier otro fallo.
- **[Comandos propuestos por un LLM]** → solo existen en borradores. Para que lleguen a ejecutarse hacen falta la promoción con `--yes` y una revisión humana; se avisa de ejecutables inexistentes.
- **[Inyección en las peticiones]** → la petición siempre va citada, el intake no tiene shell ni escritura, y la salida pasa por un esquema.
- **[Coste del intake]** → una invocación por petición con presupuesto propio (`[roles.intake]` y `--max-budget-usd`), registrada en el `events.jsonl` de la petición.
- **[Licencia]** → solo se adoptan patrones de un proyecto GPLv3. El código y los prompts se escriben desde cero, y la atribución va como inspiración.

## Migration Plan

Es aditivo y no requiere migración:
- las ejecuciones existentes no tienen `rounds/` ni `parent_run_id`, y `status` y `land` las tratan como antes;
- `[loop] protected_paths` es opcional;
- los objetivos sin `status` siguen siendo ejecutables.

Rollback: revertir el código. Los directorios nuevos de `.factory/` y `goals/drafts/` se pueden borrar sin consecuencias.

## Open Questions

- ¿El modelo por defecto del intake debe ser `opus` o el alias más capaz disponible en la cuenta? Es solo configuración.
- ¿Conviene que `land` ofrezca `--squash` en el futuro, para repos que lo exijan? No cambia el diseño actual.
