# Tasks

> Cada grupo del 2 al 6 corresponde a una feature nueva de `feature_list.json`. Al empezar el grupo se marca con `factory features start <id>`, y al terminarlo se cierra con `factory features verify <id>`. El orden sigue la decisión D6 del diseño.

## 1. Preparación

- [x] 1.1 Añadir a `feature_list.json` cinco features, cada una con su comando `python -m pytest -q tests/<archivos>`: `protected-paths`, `round-artifacts`, `run-rework`, `run-landing` y `request-intake`. Verificar que `factory features validate` pasa y que `factory doctor` no tiene fallos.

## 2. Rutas protegidas (`goal-loop`)

- [x] 2.1 Añadir `[loop] protected_paths` en `config.py`, con lista vacía por defecto. Añadir `scope.protected` y `scope.allow_modify` en `goal.py`, con la validación de que no se pueden liberar archivos críticos, y que `describe()` muestre las rutas protegidas efectivas y las liberadas. Verificar con `pytest tests/test_protected_config.py`, escenario "Un objetivo intenta liberar un archivo crítico".
- [x] 2.2 Implementar:
  - `Worktree.name_status(since)` en `gitops.py`, con `git diff --name-status -M`;
  - el cálculo del conjunto protegido efectivo: archivos críticos (`feature_list.json`, `factory.toml`, `prompts/**`, el script de `verify_command` y los scripts relativos de `acceptance`), más los de configuración y los del objetivo, menos los liberados;
  - la detección de violaciones: `M`, `D` o `T`, y `R`/`C` sobre la ruta original, solo para archivos que existían en la base.

  Verificar con pruebas unitarias en `pytest tests/test_protected_paths.py` que cubran modificar, borrar, renombrar y añadir.
- [x] 2.3 Integrar la comprobación en `engine._round` justo después de la instantánea:
  - decisión `protected_revert` con `reset_to(pre_commit)`;
  - firma de estancamiento `protected:<rutas>`;
  - retroalimentación que nombre cada archivo y el tipo de cambio.

  En `--dry-run`, listar la protección efectiva. Verificar con `pytest tests/test_protected_paths.py` usando `FakeRunner`. Escenarios:
  - "El maker modifica un test existente protegido";
  - "El maker añade un test nuevo";
  - "Renombrar un archivo protegido";
  - "El maker edita el script de verificación";
  - "Objetivo que debe actualizar un test existente";
  - "Simulación muestra la protección efectiva".
- [x] 2.4 Activar `protected_paths = ["tests/**"]` en el `factory.toml` de este repo y documentar las rutas protegidas en `docs/harness/loops.md` y `docs/harness/roles.md`. Verificar que `./scripts/check.sh` termina en 0 y cerrar con `factory features verify protected-paths`.

## 3. Artefactos legibles por ronda (`loop-state`)

- [x] 3.1 Crear `src/factory/artifacts.py`:
  - funciones que generan `maker.md`, `checks.md`, `review.md` y `decision.md` con cabeceras `CLAVE: valor`, a partir de `RoundRecord`, `Verification` y `Verdict`;
  - `read_header(path)`.

  Verificar con `pytest tests/test_artifacts.py`: formato de cabeceras, final de salida de los criterios fallidos y el veredicto "omitido" o "inválido".
- [x] 3.2 Hacer que el motor escriba `rounds/<n>/` en todas las rondas, también las revertidas por alcance o rutas protegidas, las de error del agente y las de checker omitido, y `decision.md` al cerrar. En las rondas revertidas por el ratchet, `checks.md` debe incluir `REVERTED_TO`. Verificar con `pytest tests/test_round_artifacts.py`, escenarios "Ronda con un criterio fallido", "Ronda revertida por rutas protegidas", "Decisión final" y "Ronda que empeora".
- [x] 3.3 Documentar los artefactos en `docs/harness/observabilidad.md`, comprobar que un ejemplo generado por los tests coincide con la tabla documentada y cerrar con `factory features verify round-artifacts`.

## 4. Retrabajo (`goal-loop`)

- [x] 4.1 Añadir `parent_run_id` y `start_commit` a `RunState` y `start_point` a `create_worktree`. `LoopEngine` debe aceptar ejecución padre, punto de partida y respuesta humana, y hacer la verificación base sobre `start_commit`. Verificar con `pytest tests/test_rework.py` que una ejecución hija parte de la punta del padre, conserva el `base_commit` original y deja intacta la rama del padre.
- [x] 4.2 Implementar `factory goal rework <run-id> (--answer | --answer-file) [--rounds N] [--budget USD]`:
  - usa la copia de `goal.md` del padre;
  - entrega como primera retroalimentación la respuesta humana, la pregunta del padre y las notas de su última ronda;
  - marca como revisada la entrada de la bandeja del padre, con la referencia a la ejecución hija.

  Verificar con `pytest tests/test_rework.py`. Escenarios:
  - "Retrabajo de una ejecución bloqueada" (el diff acumulado que ve el checker incluye el cambio del padre);
  - "Retrabajo de una ejecución completada";
  - "Retrabajo sin respuesta";
  - "La entrada de la bandeja de la ejecución padre".
- [x] 4.3 Documentar el retrabajo en `docs/harness/loops.md`, con el flujo bloqueo → respuesta → retrabajo, y cerrar con `factory features verify run-rework`.

## 5. Integración asistida (`run-landing`)

- [x] 5.1 Crear `src/factory/land.py` con las precondiciones: checkout principal limpio y en `main_branch`, ejecución `completed`, rama existente y ejecución no integrada aún. Verificar con `pytest tests/test_land.py`, escenarios "Checkout principal con cambios" y "Ejecución no completada" (que sugiere `goal rework`).
- [x] 5.2 Implementar el merge `--no-ff` en un worktree temporal desacoplado sobre la punta de `main`:
  - en caso de conflicto, listar los archivos y hacer `merge --abort`, con limpieza del worktree;
  - verificar los criterios de la copia de `goal.md` y las rutas protegidas del lado de la rama;
  - escribir `land/checks.md` con el renderizador del grupo 3.

  Verificar con `pytest tests/test_land.py`, escenarios "La rama principal avanzó y el merge rompe los tests" y "Conflicto de merge". En ambos, el hash de `main` no debe cambiar.
- [x] 5.3 Implementar el avance de `main`:
  - comprobar de nuevo que la punta de `main` no cambió y hacer `git merge --ff-only <commit verificado>`;
  - registrar `landed_commit`, escribir `decision.md` y marcar la bandeja como revisada;
  - opción `--delete-branch` (con `git branch -d`) y opción `--dry-run`;
  - ningún comando de red.

  Verificar con `pytest tests/test_land.py`. Escenarios:
  - "Integración correcta" (padres del merge y un remoto bare sin cambios);
  - "La rama principal cambió durante la verificación" (simulado entre la verificación y el avance);
  - "Bandeja y estado tras integrar" (un segundo `land` se rechaza);
  - "Comprobación previa".
- [x] 5.4 Exponer `factory land <run-id> [--dry-run] [--delete-branch]` en el CLI y añadir un test de "Ejecución completada sin integrar": `goal run` y `tick` terminan en `completed` y `main` no cambia; además, `engine.py` y `tick.py` no importan `land`. Sustituir en `docs/harness/loops.md` la guía de merge manual por `factory land`, actualizar `README.md` y cerrar con `factory features verify run-landing`.

## 6. Intake de peticiones (`request-intake`)

- [x] 6.1 Crear `src/factory/requests.py`: estado de cada petición en `.factory/requests/<req-id>/` y un único escritor `advance()` con tabla `TRANSITIONS` que rechace movimientos ilegales o sin el archivo que los justifica. Verificar con `pytest tests/test_requests.py` las transiciones legales e ilegales.
- [x] 6.2 Añadir el rol `[roles.intake]` (modelo por defecto `opus`) y extender `enforce_role_policy` para que el intake tenga la misma política de solo lectura que el checker. Añadir `INTAKE_SCHEMA` con validador local y escribir desde cero `prompts/intake.md`, también como plantilla empaquetada. Verificar con `pytest tests/test_intake.py`, escenarios "Configuración que concede Bash al intake" y "Salida inválida del intake".
- [x] 6.3 Implementar `factory intake ("<texto>" | --file F)` y `factory intake --answer <req-id> "<texto>"`:
  - `request.md` citado, con el aviso de que es dato;
  - invocación del agente en la raíz del repo, con presupuesto;
  - `intake.md` con cabeceras e historial `intake-<k>.md`;
  - si acepta, borrador en `goals/drafts/<id>.md` con `status: draft`, `request`, `risk` y `surfaces`;
  - si pide información o rechaza, entrada en la bandeja con `kind = "request"`.

  Verificar con `pytest tests/test_intake.py` usando `FakeRunner`. Escenarios:
  - "Petición con instrucciones inyectadas";
  - "Decisión registrada";
  - "Petición sobredimensionada";
  - "Falta información";
  - "Petición rechazada";
  - "Petición aceptada".
- [x] 6.4 Hacer que `goal.py` acepte las claves `status`, `request`, `risk` y `surfaces`. `factory goal run`, `factory tick` y `LoopEngine` deben rechazar `status: draft` antes de ejecutar ningún criterio. Verificar con `pytest tests/test_drafts.py`, escenario "Ejecutar un borrador": un criterio que crearía un archivo marcador no se ejecuta.
- [x] 6.5 Implementar `factory goal promote <borrador> [--yes]`:
  - muestra el plan y avisa de ejecutables inexistentes;
  - sin `--yes` no cambia nada;
  - con `--yes` escribe `goals/<id>.md` sin `status`, sin sobrescribir un objetivo existente, y mueve la petición a `promoted`.

  Verificar con `pytest tests/test_drafts.py`, escenarios "Promoción sin confirmación" y "Promoción confirmada". Documentar el intake en `docs/harness/loops.md` y `README.md`, y cerrar con `factory features verify request-intake`.

## 7. Integración y validación

- [x] 7.1 Verificar que `./scripts/check.sh` termina en 0, que `factory doctor` no tiene fallos críticos, que `openspec validate extend-factory-pipeline --strict` es válido y que las cinco features nuevas están en `passing` con evidencia.
- [x] 7.2 **Con aprobación del usuario para el gasto** (1 USD o menos): pasar una petición real por `factory intake`, revisar el borrador, promoverlo con `factory goal promote --yes` y validarlo con `factory goal run --dry-run`. Registrar la evidencia y el coste en `progress.md`.

## Workflow follow-up

- Archivar el cambio con `/opsx:archive` cuando se cumplan los requisitos de revisión, y sincronizar las specs `goal-loop`, `loop-state`, `run-landing` y `request-intake`.
- Abrir cambios aparte para lo aplazado: enrutado por riesgo con revisores adicionales, dashboard, hook de autoverificación del maker, y cola con concurrencia o GitHub.
- Mejora detectada en 7.2: dar al intake las rutas protegidas efectivas en su prompt y admitir `scope.allow_modify` en `INTAKE_SCHEMA`, para que sus borradores no choquen con `protected_paths`.
