# Features

`feature_list.json` es la fuente de verdad sobre **qué** hay que hacer y en qué estado está (L08). No es una nota para humanos: el harness la lee, la valida y la actualiza.

## Formato

```json
{
  "project": "factory-yate",
  "last_updated": "2026-10-27",
  "features": [
    {
      "id": "loop-config",
      "priority": 1,
      "area": "loop",
      "title": "Configuración, goal.md y adaptador de agentes",
      "user_visible_behavior": "`factory goal run --dry-run goals/x.md` valida el objetivo…",
      "status": "not_started",
      "verification": ["python -m pytest -q tests/test_config.py tests/test_goal.py"],
      "manual_checks": [],
      "evidence": [],
      "notes": "OpenSpec add-harness-loop-engine, grupo 4"
    }
  ]
}
```

| Campo | Obligatorio | Significado |
|---|---|---|
| `id` | sí | identificador único y estable |
| `priority` | sí | entero; menor = antes. Mejor si no se repite |
| `title` | sí | nombre corto |
| `user_visible_behavior` | sí | qué observa un usuario cuando funciona |
| `status` | sí | `not_started`, `in_progress`, `blocked` o `passing` |
| `verification` | sí | **comandos** que deben terminar en 0 (al menos uno) |
| `evidence` | sí | lo rellena el harness; no se edita a mano |
| `manual_checks` | no | comprobaciones humanas; no sirven para promover a `passing` |
| `area`, `notes` | no | contexto libre |

Cada feature necesita las tres patas: comportamiento + comando de verificación + estado. Si falta una, está incompleta.

## Máquina de estados

```
not_started ──start──▶ in_progress ──verify OK──▶ passing
     │                     │  ▲
     │                     ▼  │ start
     └────────────────▶ blocked
```

- `factory features start <id>` → `in_progress`. Falla si ya hay otra activa (**WIP=1**).
- `factory features verify <id>` ejecuta `verification`:
  - si todo pasa, la feature queda en `passing` con la evidencia registrada;
  - si algo falla, el estado no cambia y el comando informa qué falló.
- `blocked` se pone editando el JSON y documentando el bloqueo en `notes` y en `progress.md`. Es la única transición manual permitida.

## Lo que el harness rechaza

`factory features validate` y `factory doctor`, que forma parte de `./scripts/check.sh`, fallan si:

- falta un campo obligatorio o tiene un tipo incorrecto;
- un `status` no es válido;
- `verification` está vacío o contiene entradas vacías;
- hay dos o más features en `in_progress`;
- una feature está en `passing` sin evidencia exitosa de **cada** comando de verificación, lo que delata una promoción manual;
- hay ids duplicados.

## Granularidad

Una feature debe poder completarse en una sesión (L08). Si no cabe, divídela. Si es demasiado pequeña para tener un comando propio, agrúpala con otra.

En este repo, cada feature de la fase 2 corresponde a un grupo de tareas del cambio OpenSpec `add-harness-loop-engine`. El campo `notes` indica a qué grupo.

## Comandos

```bash
.venv/bin/factory features list            # por prioridad, con estado
.venv/bin/factory features validate        # esquema + WIP + evidencia
.venv/bin/factory features start <id>      # activar (WIP=1)
.venv/bin/factory features verify <id>     # verificar y promover con evidencia
```

Los comandos de `verification` se ejecutan en la raíz del repo con el `python` del entorno actual primero en el `PATH`. Por eso `python -m pytest …` usa el de `.venv`.

## En los loops

Si un `goal.md` declara `feature: <id>` y la ejecución termina en `completed`, el orquestador promueve esa feature **en la rama de la ejecución**, por el mismo mecanismo y con el `run_id` en la evidencia. El maker nunca puede editar `feature_list.json`: siempre está en `scope.deny`.

---
Adaptado de walkinglabs/learn-harness-engineering (MIT), lecciones 07 y 08.
