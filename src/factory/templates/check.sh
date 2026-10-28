#!/usr/bin/env bash
# Ruta única de verificación (generada por factory). Se detiene en el primer fallo e indica
# cómo reproducirlo. Termina en 0 solo si todas las comprobaciones pasan.
# Adaptado de walkinglabs/learn-harness-engineering (MIT).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

run_step() {
  echo "==> $*"
  if ! bash -c "$*"; then
    echo "" >&2
    echo "FALLO. Reproducir con: $*" >&2
    exit 1
  fi
}

{{CHECK_STEPS}}
echo "==> Verificación completa: OK"
