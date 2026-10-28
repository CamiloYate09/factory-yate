---
id: vigilancia-check
objective: La verificación completa del repositorio (./scripts/check.sh) se mantiene en verde
mode: monitor
acceptance:
  - name: check
    run: ./scripts/check.sh
scope:
  allow: ["src/**", "tests/**", "docs/**"]
  deny: ["scripts/**", "pyproject.toml", "init.sh", "factory.toml", "openspec/**"]
stop:
  max_rounds: 3
  max_budget_usd: 2.0
  no_progress_rounds: 2
  round_timeout_min: 15
---

## Contexto

Este objetivo vigila la ruta única de verificación. Cada tick ejecuta `./scripts/check.sh`. Si está en verde, no hace nada y cuesta 0. Si falla, se lanza un loop acotado para repararlo en una rama `factory/<run-id>` que un humano revisará.

## Cómo trabajar

1. Lee el fallo exacto en la retroalimentación (comprobación y salida).
2. Arregla la **causa** en `src/` o `tests/`, o los enlaces de `docs/`.
3. No cambies las reglas de verificación. No debilites ni borres tests. No toques `feature_list.json`.
4. Si el fallo requiere decidir algo (por ejemplo, un test que contradice una spec), termina con `status: needs_human`.
