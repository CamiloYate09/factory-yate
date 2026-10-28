# Vigilancia con `factory tick`

Para objetivos con `mode: monitor`, como `goals/vigilancia-check.md`, que vigila `./scripts/check.sh`:

```bash
.venv/bin/factory tick goals/vigilancia-check.md                    # un tick
.venv/bin/factory schedule goals/vigilancia-check.md --every 30m    # imprime cron / launchd / /loop
.venv/bin/factory tick goals/vigilancia-check.md --reset-breaker    # tras revisar un escalado
```

Cada tick **verifica primero, sin agentes y con coste 0**. Si todo pasa, registra `noop`. Si algo falla, aplica estas guardas en orden:

| Resultado | Cuándo | ¿Invoca agentes? |
|---|---|---|
| `noop` | los criterios pasan | no (0 USD) |
| `skipped` | otro tick del mismo objetivo sigue en curso (bloqueo con PID; se recupera si el proceso murió o es demasiado antiguo) | no |
| `circuit_open` | `circuit_after` ticks seguidos sin `completed`. Se crea una entrada de **escalado** en la bandeja | no, hasta `--reset-breaker` |
| `awaiting_review` | ya hay una ejecución de un tick anterior pendiente en la bandeja | no |
| `budget_exhausted` | se alcanzó `daily_budget_usd` del día | no |
| `run` | falla y las guardas lo permiten: loop acotado (`[tick] max_rounds`, `budget_per_tick_usd`) | sí |

`factory tick` sale con 0 en `noop`, `skipped` y `run` completado, y con 1 si el problema sigue sin resolverse. Así cron puede avisar.

**Ojo:** el tick verifica el **árbol de trabajo** del repo principal, pero la ejecución parte del **último commit de `main`**. Si el fallo lo causan cambios sin commitear, la ejecución puede no reproducirlo y terminar en `completed` sin cambios. Vigila sobre un árbol limpio.

`factory schedule` **no instala nada**: imprime la línea de cron, la plantilla de launchd y el comando `/loop`. El `/loop` solo vive mientras la sesión de Claude Code está abierta. El historial queda en `.factory/ticks/<id>.jsonl` y se resume en `factory status`.

---
Adaptado de walkinglabs/learn-harness-engineering (MIT), lección 13 y proyecto 07.
