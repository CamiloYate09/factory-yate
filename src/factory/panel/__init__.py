"""Panel de observabilidad: tokens, revisiones y estado de implementación (solo lectura)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from factory.util import find_root


class PanelError(RuntimeError):
    """Error de dominio del panel (argumentos o rutas inválidos)."""


def main_root(start: Path | None = None) -> Path:
    """Raíz del repo principal, también desde un worktree (directorio común de git)."""
    root = find_root(start)
    proc = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    common = Path(proc.stdout.strip()) if proc.returncode == 0 and proc.stdout.strip() else None
    if common is not None and common.name == ".git":
        return common.parent.resolve()
    return root


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Objetos JSON de un archivo de una línea por evento; ignora las líneas inválidas."""
    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError:
        return
    with handle:
        for line in handle:
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                yield data


def is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def number(value: Any) -> int | float:
    """El valor si es un número (no booleano); 0 en otro caso."""
    return value if is_number(value) else 0


def day_of(timestamp: Any) -> str:
    """Día `AAAA-MM-DD` de una marca ISO 8601, o cadena vacía si no lo parece."""
    if isinstance(timestamp, str) and len(timestamp) >= 10 and timestamp[4] == "-":
        return timestamp[:10]
    return ""
