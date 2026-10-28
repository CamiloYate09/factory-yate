# Revisar, retrabajar e integrar

Un loop **nunca** integra en `main` ni hace push. Al terminar deja una rama `factory/<run-id>` y una entrada en la bandeja. Lo que sigue es una decisión humana.

## Revisar el resultado

El loop **nunca** hace merge a `main` ni push. Al terminar elimina el worktree, conserva la rama y deja una entrada en la bandeja:

```bash
.venv/bin/factory inbox list
git log --oneline <base>..factory/<run-id>   # instantáneas por ronda
git diff <base>...factory/<run-id>           # qué cambió en total
cat .factory/runs/<run-id>/loop-state.md     # por qué: rondas, hallazgos, decisiones
.venv/bin/factory inbox ack <run-id>         # marcar como revisada
```

## Integrar: `factory land`

Integrar es una decisión humana, y el comando para hacerlo es `factory land`. `goal run` y `tick` nunca lo invocan.

```bash
.venv/bin/factory land <run-id> --dry-run         # verifica el merge exacto sin cambiar nada
.venv/bin/factory land <run-id>                   # integra en main (merge --no-ff), sin push
.venv/bin/factory land <run-id> --delete-branch   # además borra la rama ya integrada
```

Pasos:

1. **Precondiciones.** La ejecución terminó `completed` y aún no se integró, su rama existe, y el checkout principal está en `main` sin cambios en archivos versionados. Los archivos sin seguimiento no bloquean.
2. **Merge exacto en un worktree temporal** fuera del repo, sobre la punta **actual** de `main`, por si `main` avanzó desde la ejecución. Si hay conflicto, lista los archivos y no cambia nada.
3. **Verificación** de los criterios del objetivo y de las rutas protegidas sobre ese merge. El informe queda en `.factory/runs/<run-id>/land/checks.md`.
4. **Avance de `main`** con `--ff-only` exactamente al commit verificado. Si `main` cambió durante la verificación, se rechaza y hay que repetir.
5. **Cierre.** Registra `landed_commit` y la cabecera `LANDED` en `decision.md`, y marca como revisada la entrada de la bandeja.

Si el objetivo declaraba `feature:`, la promoción a `passing` ya está **en la rama**, con evidencia y `run_id`, y llega a `main` con la integración. Para descartar una ejecución, `git branch -D factory/<run-id>` y `factory inbox ack <run-id>`.

## Retrabajo: responder y continuar

Si una ejecución termina `blocked` (el maker preguntó algo), `max_rounds`, `stalled`, `budget_exhausted`, `agent_error` o `interrupted`, no hace falta empezar desde cero:

```bash
.venv/bin/factory inbox list                                       # lee la pregunta o el motivo
.venv/bin/factory goal rework <run-id> --answer "usa el archivo nuevo"   # o --answer-file respuesta.md
.venv/bin/factory goal rework <run-id> --answer "..." --rounds 3 --budget 1.5
```

El retrabajo crea una **ejecución hija**:

- parte de la punta de la rama del padre, en una rama nueva `factory/<run-id-hijo>`; la rama del padre no cambia;
- conserva el **commit base original**, así el checker ve el diff acumulado de ambas ejecuciones y las rutas protegidas se comprueban contra la base;
- usa la copia de `goal.md` del padre;
- empieza con tu respuesta, la pregunta del padre y las notas de su última ronda;
- marca como revisada la entrada de la bandeja del padre (`resolution: retrabajo → <hijo>`).

Una ejecución `completed` no admite retrabajo: se integra con `factory land`.

---
Adaptado de walkinglabs/learn-harness-engineering (MIT), lección 13. Integración verificada inspirada en *Software Factory v2* (ZazenCodes, GPLv3), sin copiar código.
