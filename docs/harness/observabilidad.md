# Observabilidad de los loops

Cuanto más rápido corre un loop, más necesitas ver qué pasa dentro (L11). Con estos archivos, un humano audita una ejecución sin leer transcripciones.

## Estado externo

Cada ejecución deja su memoria en `.factory/` del repo principal. Está fuera de los worktrees e ignorada por git, así que sobrevive cuando se borra el worktree:

| Archivo | Contenido |
|---|---|
| `.factory/runs/<run-id>/loop-state.md` | estado legible: rondas, verificación, hallazgos, decisión, estadísticas, resultado final |
| `.factory/runs/<run-id>/state.json` | lo mismo, legible por máquina (fuente de verdad, escritura atómica) |
| `.factory/runs/<run-id>/events.jsonl` | una línea por invocación de agente (rol, modelo, coste, tokens, denegaciones) o comando (código, salida truncada) |
| `.factory/runs/<run-id>/goal.md` | copia del objetivo usado |
| `.factory/results.tsv` | una fila por ronda de todas las ejecuciones (solo-añadir) |
| `.factory/inbox/<run-id>.md` | entrada de la bandeja de revisión humana |

Cada ronda recibe un **resumen acotado** (`summary_max_chars`), no la transcripción anterior. El resumen prioriza los bloqueos, la mejor ronda y la más reciente.

### Bandeja y `factory status`

```bash
.venv/bin/factory inbox list           # pendientes (--all para todas)
.venv/bin/factory inbox ack <run-id>   # marcar como revisada tras revisar la rama
.venv/bin/factory status               # ejecuciones e indicadores
```

`factory status` muestra los **cuatro costes silenciosos** (L13), que crecen cuanto más tiempo corren los loops:

| Indicador | Qué mide | Aviso (`[alerts]`) |
|---|---|---|
| Deuda de verificación | % de criterios verificados por máquina frente a comprobaciones solo humanas | si hay comprobaciones solo humanas |
| Deterioro de la comprensión | líneas y archivos de ramas pendientes de revisión | `pending_lines_max` (500) |
| Rendición cognitiva | entradas pendientes y la más antigua | `inbox_pending_max` (3) |
| Explosión de tokens | tokens de entrada del maker, primera vs. última ronda | `token_growth_ratio` (×2) |

Si aparece un aviso, **revisa antes de lanzar más loops**. La generación es casi gratis; el juicio humano es el recurso escaso.

---
Adaptado de walkinglabs/learn-harness-engineering (MIT), lecciones 11 y 13.
