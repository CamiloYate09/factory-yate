# Salidas grabadas de `claude -p --output-format json`

- `plain_real.json`: salida real (Claude Code 2.1.308, haiku) de la verificación de la tarea 3.2.
- `verdict_in_result.json`: salida real del checker (tarea 3.5) con `result` sustituido por un veredicto JSON entre fences (respaldo de D2).
- `structured_output.json`: igual, con el veredicto en `structured_output` (forma esperada con `--json-schema`; pendiente de confirmar con la prueba live 9.2).
- `error_budget.json`: `plain_real.json` marcado como error de presupuesto (`is_error`, `subtype`).
