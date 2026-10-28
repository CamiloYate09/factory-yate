#!/usr/bin/env bash
# Ruta única de verificación del repositorio.
# Termina en 0 solo si todas las comprobaciones pasan; se detiene en el primer fallo
# e indica qué comprobación falló y cómo reproducirla.
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ -x .venv/bin/python ]; then
  PY=.venv/bin/python
else
  PY="${PYTHON:-python3}"
fi

run_step() {
  local name="$1"
  shift
  echo "==> [$name] $*"
  if ! "$@"; then
    echo "" >&2
    echo "FALLO en la comprobación '$name'." >&2
    echo "Reproducir con: $*" >&2
    exit 1
  fi
}

run_step lint "$PY" -m ruff check .
run_step formato "$PY" -m ruff format --check .
run_step tests "$PY" -m pytest -q
run_step harness "$PY" -m factory doctor

echo "==> Verificación completa: OK"
