@AGENTS.md

## Notas para Claude Code

- **Revisión independiente.** Antes de declarar terminada una feature, invoca el subagente `checker` (definido en `.claude/agents/checker.md`).
  - Pásale solo el diff (`git diff`) y los criterios de la feature, no tu razonamiento.
  - Corrige los hallazgos `critical` y `medium` y vuelve a pedir revisión.
- **El `checker` es de solo lectura.** Si hace falta verificar, ejecuta tú `./scripts/check.sh` y pásale el resultado.
- **Trabajo largo o desatendido.** Usa el motor de loops de `factory` en lugar de encadenar prompts a mano (ver `docs/harness/loops.md`).
- **Cierre de sesión.** Sigue la lista de `AGENTS.md`. No termines con `./scripts/check.sh` en rojo sin documentarlo en `progress.md`.
- **OpenSpec.** Los comandos `/opsx:*` gestionan las specs y los cambios de `openspec/`.
