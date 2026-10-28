---
# Plantilla de objetivo para `factory goal run` (o `factory tick` si mode: monitor).
# Cuanto más específico y verificable, mejor el loop. Copia este archivo a goals/<id>.md.
id: plantilla
objective: "Describe en una frase qué cuenta como terminado"
mode: finite            # finite: tarea con línea de meta (goal run) · monitor: vigilancia (tick)
# feature: loop-config  # opcional: id de feature_list.json que se promueve al completar

# Criterios verificables por máquina: cada uno es un comando que termina en 0 cuando se cumple.
# El orquestador los ejecuta él mismo; lo que diga el agente no basta.
acceptance:
  - name: tests
    run: python -m pytest -q
  - name: lint
    run: python -m ruff check .

# Alcance: qué puede tocar el maker. feature_list.json siempre queda prohibido.
scope:
  allow: ["src/**", "tests/**"]
  deny: ["pyproject.toml", "scripts/**", "init.sh"]

# Condiciones de parada. Las que omitas toman el valor de factory.toml ([loop]).
stop:
  max_rounds: 5
  max_budget_usd: 2.0
  no_progress_rounds: 3
  consecutive_passes: 1
  round_timeout_min: 15

# Opcional: overrides por rol (model, permission_mode, allowed_tools, denied_tools).
# roles:
#   maker: {model: sonnet}
#   checker: {model: opus}
---

## Contexto

Qué hay que saber del proyecto para esta tarea. Enlaza documentos en lugar de copiarlos.

## Cómo trabajar

1. Lee `AGENTS.md` y los documentos de `docs/harness/` relevantes.
2. Escribe el enfoque antes de tocar código.
3. Verifica después de cada sub-tarea con los comandos de `acceptance`.
4. Si te atascas dos rondas con el mismo error, cambia de enfoque o simplifica.
5. Si necesitas una decisión humana, termina con `status: needs_human` y la pregunta.

## Fuera de alcance

- Lo que no se debe tocar aunque parezca relacionado.

<!-- Adaptado de la plantilla goal.md de walkinglabs/learn-harness-engineering (MIT), lección 13. -->
