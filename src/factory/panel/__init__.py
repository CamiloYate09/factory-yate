"""Panel de observabilidad: tokens, revisiones y estado de implementación (solo lectura)."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from factory.config import ConfigError, load_config
from factory.util import find_root

DESCRIPTION_MAX = 200  # descripción de un subagente que se guarda o se muestra


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


def state_dir(root: Path, warnings: list[str] | None = None) -> Path:
    """Directorio de estado de `root`: `[loop] state_dir` de `factory.toml` o `.factory/`."""
    try:
        return load_config(root).state_path
    except ConfigError as exc:
        if warnings is not None:
            warnings.append(f"factory.toml: {exc}; se usa .factory/")
        return root / ".factory"


def read_meta(transcript: Path) -> dict[str, Any]:
    """`agent-<id>.meta.json` junto a la transcripción de un subagente, o `{}` si no vale."""
    try:
        meta = json.loads(transcript.with_name(transcript.stem + ".meta.json").read_text("utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return meta if isinstance(meta, dict) else {}


def unreadable(path: Path, exc: OSError, warnings: list[str] | None) -> None:
    """Aviso para un archivo que existe pero no se puede leer (uno ausente no avisa)."""
    if warnings is not None and not isinstance(exc, FileNotFoundError):
        warnings.append(f"{path}: no se pudo leer ({exc.strerror or exc})")


def read_jsonl(path: Path, warnings: list[str] | None = None) -> Iterator[dict[str, Any]]:
    """Objetos JSON de un archivo de una línea por evento; ignora las líneas inválidas."""
    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError as exc:
        unreadable(path, exc, warnings)
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
