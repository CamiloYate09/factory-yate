#!/usr/bin/env bash
# Ruta estándar de arranque (generada por factory): prepara el entorno y ejecuta la verificación
# de referencia. Termina con código distinto de cero si la verificación falla.
# Adaptado de walkinglabs/learn-harness-engineering (MIT).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "==> Preparando el entorno"
{{INSTALL}}

echo "==> Verificación de referencia"
exec ./scripts/check.sh
