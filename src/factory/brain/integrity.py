"""Huella de integridad de un cerebro: detecta cualquier cambio durante una ejecución."""

from __future__ import annotations

import hashlib
from pathlib import Path

INDEX_FILES = ("_catalog.jsonl", "_books.json", "llms.txt")


def _tracked(directory: Path, path: Path) -> bool:
    """Notas `.md` e índices; nunca archivos ocultos (`.DS_Store`, `.obsidian/`, registro)."""
    relative = path.relative_to(directory)
    if any(part.startswith(".") for part in relative.parts):
        return False
    return relative.suffix == ".md" or relative.as_posix() in INDEX_FILES


def fingerprint(directory: Path) -> str:
    """sha256 del catálogo más ruta, tamaño y mtime de cada nota e índice. Vacío si no existe."""
    if not directory.is_dir():
        return ""
    digest = hashlib.sha256()
    catalog = directory / "_catalog.jsonl"
    if catalog.is_file():
        digest.update(hashlib.sha256(catalog.read_bytes()).digest())
    for path in sorted(directory.rglob("*")):
        if path.is_file() and _tracked(directory, path):
            stat = path.stat()
            digest.update(
                f"{path.relative_to(directory)}|{stat.st_size}|{stat.st_mtime_ns}\n".encode()
            )
    return digest.hexdigest()
