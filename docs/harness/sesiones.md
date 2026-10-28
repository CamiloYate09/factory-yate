# Sesiones: inicio, cierre y handoff

Trata a cada sesión como un ingeniero con amnesia (L05): lo que no esté en el repo no existe para la siguiente. El coste de reconstruir el contexto es la métrica a minimizar.

## Inicio (clock in)

1. `pwd`: confirma que estás en la raíz del repo.
2. Lee `progress.md`: estado verificado actual, riesgos y mejor próximo paso.
3. `.venv/bin/factory features list`: la feature `in_progress`, o la de mayor prioridad sin terminar.
4. `git log --oneline -5`: qué cambió recientemente.
5. `./init.sh`: entorno y verificación de referencia.
6. Si la referencia ya está rota, **arréglala primero**. No apiles trabajo nuevo sobre un estado roto.

Si existe `session-handoff.md` con contenido reciente, léelo después de `progress.md`.

## Durante la sesión

- Trabaja en una sola feature (WIP=1) y dentro de su alcance.
- Verifica después de cada sub-tarea, no solo al final.
- Si te atascas más de dos intentos con el mismo error, cambia de enfoque o simplifica, y anótalo.
- No refactorices "de paso" antes de que lo funcional esté verificado (L09).
- Antes de declarar terminado, pide revisión independiente (ver [roles.md](roles.md)).

## Cierre (clock out): clean state

El clean state forma parte de la definición de terminado (L12). Usa la [lista de cierre](clean-state-checklist.md). Cubre cinco dimensiones:

| Dimensión | Cómo se comprueba |
|---|---|
| Build / entorno | `./init.sh` funciona desde cero |
| Pruebas | `./scripts/check.sh` termina en 0 |
| Progreso | `progress.md` tiene la entrada de esta sesión |
| Artefactos | `feature_list.json` refleja la realidad; no hay archivos temporales sueltos |
| Inicio | la próxima sesión puede seguir sin reparar nada a mano |

"Limpiar después" equivale a no limpiar nunca. Si no puedes dejar algo en verde, **documenta el fallo como riesgo** en `progress.md` antes de terminar. No declares la sesión terminada.

## Registro de progreso (`progress.md`)

Arriba va el **estado verificado actual**: raíz, rutas de arranque y verificación, feature activa, bloqueos. Debajo, una entrada por sesión:

```markdown
### Sesión NNN — AAAA-MM-DD
- Objetivo:
- Completado:
- Verificación ejecutada: (comandos y resultado)
- Evidencia: (features verificadas, enlaces a salidas)
- Riesgos / pendientes:
- Mejor próximo paso:
```

Escribe hechos verificables, no impresiones. "Tests en verde" sin el comando no es evidencia.

## Handoff compacto (`session-handoff.md`)

Úsalo cuando la sesión fue larga o cuando otra persona o agente va a continuar. Tiene cuatro bloques: *verificado ahora*, *cambiado en esta sesión*, *roto o sin verificar* y *mejor próximo paso*, con los comandos exactos. Se sobrescribe en cada handoff; el historial vive en `progress.md` y en git.

## Prueba de arranque en frío

Una sesión nueva, usando solo el repo, debe poder responder (L03):

1. ¿Qué es este proyecto?
2. ¿Cómo se arranca?
3. ¿Cómo se verifica?
4. ¿Cuál es la siguiente feature?
5. ¿Qué riesgos hay abiertos?

Si alguna respuesta exige leer el historial de chat, falta algo en el repo.

## En los loops

Cada ronda de un loop es una sesión nueva con el mismo contrato. El orquestador le da un resumen acotado del estado del loop, en lugar de la transcripción anterior, y deja constancia en `.factory/runs/<run-id>/loop-state.md`.

---
Adaptado de walkinglabs/learn-harness-engineering (MIT), lecciones 03, 05, 06 y 12.
