"""`factory brain import` (spec main-brain): copia local, refrescable y atómica de un vault.

Solo se copian notas Markdown y los índices que las describen; nunca PDF, `.obsidian/` ni
`_build/`. El origen se abre en solo lectura y jamás se modifica.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from factory.brain import BrainError
from factory.util import atomic_write_text, now_iso

INDEX_FILES = ("_catalog.jsonl", "_books.json", "llms.txt")
SKIPPED_DIRS = ("_build",)
METADATA_FILE = ".factory-import.json"
MAX_MISSING_SHOWN = 5


@dataclass
class ImportResult:
    source: str
    dest: str
    date: str
    notes: int
    books: int
    tokens: int
    catalog_sha256: str
    gitignore_added: bool = False


def _copy_file(src: Path, dst: Path) -> None:
    """Punto único de copia (los tests lo sustituyen para simular un fallo a mitad)."""
    shutil.copy2(src, dst)


def _wanted(relative: Path) -> bool:
    if any(part.startswith(".") or part in SKIPPED_DIRS for part in relative.parts):
        return False
    return relative.suffix == ".md" or (len(relative.parts) == 1 and relative.name in INDEX_FILES)


def _catalog_entries(catalog: Path) -> list[dict]:
    entries = []
    for number, line in enumerate(catalog.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BrainError(f"_catalog.jsonl línea {number}: JSON inválido ({exc.msg})") from exc
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise BrainError(f"_catalog.jsonl línea {number}: falta `path`")
        entries.append(entry)
    return entries


def _ensure_ignored(repo_root: Path, dest: Path) -> bool:
    """Si el destino está dentro del repo y git no lo ignora, lo añade a .gitignore."""
    try:
        relative = dest.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    if not (repo_root / ".git").exists():
        return False
    probe = subprocess.run(
        ["git", "check-ignore", "-q", f"{relative.as_posix()}/x.md"],
        cwd=repo_root,
        capture_output=True,
    )
    if probe.returncode == 0:
        return False
    gitignore = repo_root / ".gitignore"
    current = gitignore.read_text(encoding="utf-8") if gitignore.exists() else ""
    block = (
        "\n# Cerebro principal: copia local de libros (factory brain import). No se versiona.\n"
        f"/{relative.as_posix()}/\n"
    )
    atomic_write_text(gitignore, current.rstrip("\n") + "\n" + block)
    return True


def import_vault(source: Path, dest: Path, repo_root: Path) -> ImportResult:
    source, dest = source.expanduser().resolve(), dest.expanduser().resolve()
    if not source.is_dir():
        raise BrainError(f"No existe el directorio de origen: {source}")
    if dest == source or source in dest.parents or dest in source.parents:
        raise BrainError("El destino no puede estar dentro del origen ni contenerlo.")
    if not (source / "_catalog.jsonl").is_file():
        raise BrainError(
            f"{source} no es un vault con catálogo: falta _catalog.jsonl. Importa la carpeta "
            "que contiene _catalog.jsonl (por ejemplo, .../book/obsidian-vault)."
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.parent / f".{dest.name}.tmp-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        for path in sorted(source.rglob("*")):
            relative = path.relative_to(source)
            if not path.is_file() or not _wanted(relative):
                continue
            target = tmp / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            _copy_file(path, target)
        catalog = tmp / "_catalog.jsonl"
        entries = _catalog_entries(catalog)
        missing = [e["path"] for e in entries if not (tmp / e["path"]).is_file()]
        if missing:
            shown = ", ".join(missing[:MAX_MISSING_SHOWN])
            more = (
                f" (y {len(missing) - MAX_MISSING_SHOWN} más)"
                if len(missing) > MAX_MISSING_SHOWN
                else ""
            )
            raise BrainError(f"El catálogo referencia notas que no existen: {shown}{more}")
        books_file = tmp / "_books.json"
        if books_file.is_file():
            books = len(json.loads(books_file.read_text(encoding="utf-8")))
        else:
            books = len({e.get("book_id") for e in entries if e.get("book_id")})
        result = ImportResult(
            source=str(source),
            dest=str(dest),
            date=now_iso(),
            notes=len(entries),
            books=books,
            tokens=sum(int(e.get("tokens") or 0) for e in entries),
            catalog_sha256=hashlib.sha256(catalog.read_bytes()).hexdigest(),
        )
        atomic_write_text(tmp / METADATA_FILE, json.dumps(asdict(result), indent=2) + "\n")
        # El destino anterior solo desaparece cuando la copia nueva ya está en su sitio.
        if dest.exists():
            old = dest.parent / f".{dest.name}.old-{int(time.time())}"
            dest.rename(old)
            tmp.rename(dest)
            shutil.rmtree(old, ignore_errors=True)
        else:
            tmp.rename(dest)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    result.gitignore_added = _ensure_ignored(repo_root, dest)
    return result


def read_metadata(dest: Path) -> dict | None:
    path = dest / METADATA_FILE
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def leftovers(dest: Path) -> list[Path]:
    """Restos de importaciones interrumpidas (`.<nombre>.tmp-*` / `.<nombre>.old-*`)."""
    parent = dest.parent
    if not parent.exists():
        return []
    return sorted(
        p
        for p in parent.iterdir()
        if p.name.startswith((f".{dest.name}.tmp-", f".{dest.name}.old-"))
    )
