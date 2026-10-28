# AGENTS.md

{{PROJECT}}: describe aquí el proyecto en una o dos frases. <!-- TODO(factory) -->

El objetivo de una sesión no es producir más código, sino dejar el repositorio en un estado que la siguiente sesión pueda continuar sin adivinar.

## Comandos

- Arranque (entorno + verificación de referencia): `{{START}}`
- Verificación completa: `{{VERIFY}}`. Ejecuta:
{{VERIFY_LIST}}
- Features: `factory features list | start <id> | verify <id>`
- Auditoría del harness: `factory doctor`

## Inicio de sesión

1. `pwd`: confirma que estás en la raíz del repositorio.
2. Lee `progress.md`: estado verificado y siguiente paso.
3. `factory features list`: la feature `in_progress` o la de mayor prioridad sin terminar.
4. `git log --oneline -5`.
5. `{{START}}`. Si la verificación de referencia falla, arréglala antes de empezar trabajo nuevo.

## Restricciones duras

- **WIP=1**: una sola feature en `in_progress`.
- **No edites a mano `status` ni `evidence`** de `feature_list.json`; usa `factory features verify <id>`.
- **No debilites, borres ni omitas tests** para que algo pase.
- **No hagas push, merge ni PRs** desde un agente. No cambies las reglas de verificación sin una petición explícita.
- **Respeta el alcance** de la feature activa.

## Definición de terminado

Una feature está terminada solo si:

- el comportamiento está implementado y probado;
- `{{VERIFY}}` termina en 0;
- `factory features verify <id>` la promovió a `passing` con evidencia;
- `progress.md` registra lo hecho y el siguiente paso.

## Cierre de sesión

Sigue la [lista de clean state](docs/harness/clean-state-checklist.md). Actualiza `progress.md`, y también `session-handoff.md` si la sesión fue larga.

---
Harness generado por factory, adaptado del curso [walkinglabs/learn-harness-engineering](https://github.com/walkinglabs/learn-harness-engineering) (MIT).
