# Lista de cierre de sesión (clean state)

Una sesión **no** está terminada si alguna casilla queda sin marcar y sin documentar como riesgo en `progress.md`.

- [ ] **Arranque**: `./init.sh` sigue funcionando desde cero.
- [ ] **Verificación**: `./scripts/check.sh` termina en 0.
- [ ] **Progreso**: `progress.md` tiene la entrada de esta sesión con la verificación ejecutada y el mejor próximo paso.
- [ ] **Features**: `feature_list.json` refleja la realidad. Hay una sola feature en `in_progress` como máximo, nada está en `passing` sin `factory features verify`, y los bloqueos están documentados.
- [ ] **Artefactos**: no quedan archivos temporales, salidas de depuración ni pasos a medio hacer sin documentar.
- [ ] **Revisión**: el subagente `checker` no dejó hallazgos `critical` ni `medium` abiertos en lo que se declara terminado.
- [ ] **Siguiente sesión**: puede continuar sin reparar nada a mano.

Si hay commits, deben tener mensajes descriptivos y el repo debe quedar en un estado seguro para retomar. Los agentes no hacen push.

---
Adaptado de walkinglabs/learn-harness-engineering (MIT), lección 12.
