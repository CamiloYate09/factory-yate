#!/usr/bin/env bash
# Ruta estándar de arranque: prepara el entorno reproducible y ejecuta la verificación de referencia.
# Termina con código distinto de cero si la verificación de referencia falla.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON="${PYTHON:-python3}"

echo "==> Directorio de trabajo: $PWD"

if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
  echo "Se requiere Python >= 3.12 (encontrado: $("$PYTHON" --version 2>&1)). Usa PYTHON=/ruta/a/python3.12 ./init.sh" >&2
  exit 1
fi

if command -v uv >/dev/null 2>&1; then
  echo "==> Sincronizando dependencias con uv"
  [ -d .venv ] || uv venv --python "$PYTHON" .venv
  uv pip install --quiet --python .venv/bin/python -e '.[dev]'
else
  echo "==> Sincronizando dependencias con venv + pip"
  [ -d .venv ] || "$PYTHON" -m venv .venv
  .venv/bin/python -m pip install --quiet --disable-pip-version-check -e '.[dev]'
fi

echo "==> Verificación de referencia"
exec ./scripts/check.sh
