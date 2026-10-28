---
id: dogfood-cli-help
objective: Un test verifica que `factory --help` lista todos los subcomandos del CLI
mode: finite
acceptance:
  - name: test-help
    run: python -m pytest -q tests/test_cli_help.py
  - name: lint
    run: python -m ruff check src tests
  - name: formato
    run: python -m ruff format --check src tests
scope:
  allow: ["tests/test_cli_help.py"]
stop:
  max_rounds: 2
  max_budget_usd: 1.0
  no_progress_rounds: 2
  consecutive_passes: 1
  round_timeout_min: 10
---

## Contexto

`src/factory/cli.py` define los subcomandos `init`, `features`, `goal`, `inbox`, `tick`, `schedule`, `status` y `doctor` con argparse. Hoy ningún test garantiza que aparezcan en la ayuda.

## Cómo trabajar

1. Crea **solo** `tests/test_cli_help.py`. No toques ningún otro archivo.
2. El test ejecuta `factory.cli.main(["--help"])`, captura la salida con `capsys` (argparse sale con `SystemExit` 0) y comprueba que aparece cada uno de los 8 subcomandos.
3. Sigue el estilo de los demás tests de `tests/`: docstring de módulo en español, nombres en español y sin dependencias nuevas.
4. Ejecuta `python -m pytest -q tests/test_cli_help.py` y `python -m ruff check tests/test_cli_help.py` antes de terminar.
