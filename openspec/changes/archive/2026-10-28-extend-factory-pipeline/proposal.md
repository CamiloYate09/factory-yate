# Proposal

## Why

Analizamos *Software Factory for Claude Code v2* (zazencodes-season-3), una fábrica que lleva peticiones a código integrado mediante un pipeline fijo. Las etapas deterministas las ejecutan scripts y el juicio lo aportan agentes. Varias de sus ideas cubren huecos concretos de factory-yate:

- **Tests y verificación desprotegidos.** El maker puede modificar o borrar tests existentes, o tocar el propio script de verificación. Hoy solo lo frena el criterio del checker o un `scope.deny` explícito en el objetivo.
- **Rondas sin rastro legible.** El diseño anterior (D5) prometía `rounds/<n>/` y nunca se implementó. Lo que pasa en cada ronda solo queda en `events.jsonl`.
- **Bloqueos que obligan a empezar de cero.** Cuando una ejecución termina `blocked` o `max_rounds`, la respuesta del humano no puede retomar la rama; hay que relanzar desde `main` y se pierde el trabajo.
- **Integración manual sin comprobar `main`.** Integrar una rama es un `git merge` a mano, sin verificar que el resultado siga en verde si `main` avanzó mientras tanto.
- **Peticiones sin filtro.** Todo objetivo lo escribe un humano. No hay una puerta que decida si una petición merece construirse, la recorte si es demasiado grande o pregunte cuando falta información.

Tomamos los patrones, no el código: el proyecto de referencia es GPLv3.

## What Changes

- **Rutas protegidas.** Si una ronda modifica, borra o renombra un archivo existente que coincide con una ruta protegida, falla y se revierte. Crear archivos nuevos sí está permitido; así un maker puede añadir tests, pero no debilitar los que ya existen.
  - Algunos archivos críticos del harness están **siempre** protegidos: `feature_list.json`, `factory.toml`, el script de verificación y `prompts/**`.
  - `factory.toml` y cada `goal.md` pueden añadir rutas, y un objetivo puede liberar rutas concretas que sí debe modificar (nunca las críticas).
- **Artefactos legibles por ronda.** Se escriben en `.factory/runs/<id>/rounds/<n>/`:
  - `maker.md`, `checks.md` (con `COMMIT:` y el resultado de las rutas protegidas), `review.md`;
  - `decision.md` al final de la ejecución.

  Todos empiezan con cabeceras `CLAVE: valor` que se pueden parsear.
- **Retrabajo.** `factory goal rework <run-id> --answer …` continúa una ejecución terminada desde la punta de su rama, con la respuesta humana como retroalimentación inicial. Conserva el commit base original, así el checker y las rutas protegidas siguen viendo todo el trabajo acumulado.
- **Integración asistida.** `factory land <run-id>` es un comando que solo invoca un humano:
  1. comprueba que el checkout principal está limpio y en `main`;
  2. construye el merge exacto de la rama sobre el `main` actual en un worktree temporal;
  3. vuelve a verificar ese resultado;
  4. solo si pasa, avanza `main` a ese commit verificado (merge `--no-ff`);
  5. marca la entrada de la bandeja como revisada.

  Nunca hace push. `goal run` y `tick` nunca lo invocan.
- **Intake de peticiones.** `factory intake "<petición>"`: un agente de solo lectura, sin shell, recibe la petición como dato citado y decide `ACCEPT`, `NEEDS-INFO` o `REJECT`. También puede recortar el alcance y valora el riesgo y las superficies afectadas.
  - Si acepta, genera un **borrador** de `goal.md`.
  - `goal run` y `tick` rechazan los borradores hasta que un humano los promueve con `factory goal promote … --yes`, después de ver los comandos que se ejecutarán.

**Aplazado a cambios futuros (con motivo):**
- **Enrutado por riesgo con revisores adicionales** (seguridad, UI, UX): obliga a modificar el requisito "Aprobación decidida por el orquestador". Se hará en su propio cambio, usando el riesgo que el intake ya registra.
- **Agente aprobador**: en factory-yate aprueba siempre un humano. Un aprobador solo podría recomendar, y eso aporta poco mientras `land` sea manual.
- **Dashboard HTML**: es útil, pero `factory status` y la bandeja cubren lo básico. Conviene hacerlo cuando existan los artefactos por ronda.
- **Hook de autoverificación del maker** (`SubagentStop`): es un empujón para el maker. La puerta determinista ya decide.
- **Cola con concurrencia (`factory run`) e issues/PR de GitHub**: es el nivel 4–5 de la escalera de madurez; el repo no tiene remoto ni `gh`.
- **Coste a partir de transcripciones**: `claude -p` ya devuelve el coste exacto, de forma más fiable.

## Capabilities

### New Capabilities
- `run-landing`: integración de una ejecución terminada en la rama principal. La invoca un humano, con una verificación previa del merge exacto contra el `main` actual y sin push.
- `request-intake`: triaje de peticiones (aceptar, pedir información o rechazar, recortar alcance, riesgo y superficies). Genera borradores de objetivo que no se ejecutan hasta que un humano los promueve.

### Modified Capabilities
- `goal-loop`: se añaden las rutas protegidas (con las críticas del harness siempre protegidas) y el retrabajo desde una ejecución anterior. Solo requisitos `ADDED`; no cambia ningún requisito existente.
- `loop-state`: se añaden los artefactos legibles por ronda y el commit asociado a cada verificación. Solo requisitos `ADDED`.

## Impact

- **Código:**
  - `src/factory/goal.py`: `scope.protected`, `scope.allow_modify` y el estado `draft`.
  - `src/factory/config.py`: `[loop] protected_paths` y `[roles.intake]`.
  - `src/factory/engine.py`: comprobación de rutas protegidas, artefactos por ronda y ejecuciones hijas de un retrabajo.
  - `src/factory/gitops.py`: diff con estados contra la base y merge en worktree temporal.
  - Módulos nuevos `src/factory/land.py` e `src/factory/intake.py`.
  - CLI: `goal rework`, `goal promote`, `land` e `intake`.
- **Estado:** `.factory/runs/<id>/rounds/` y `.factory/requests/<id>/`; borradores en `goals/drafts/`.
- **Documentación:** `docs/harness/loops.md`, `roles.md` y `observabilidad.md`; `README.md`.
- **Dependencias:** ninguna nueva.
- **Coste:** el intake añade una invocación de agente por petición. Lo demás es determinista.
- **Atribución:** patrones inspirados en *Software Factory for Claude Code v2* (ZazenCodes, GPLv3), sin copiar código ni prompts.
