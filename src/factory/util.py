"""Utilidades compartidas: raíz del repo, escritura atómica, ejecución de comandos y git."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT_MARKERS = ("factory.toml", ".git")


def find_root(start: Path | None = None) -> Path:
    """Sube desde `start` hasta encontrar `factory.toml` o `.git`; si no, devuelve `start`."""
    start = (start or Path.cwd()).resolve()
    for candidate in (start, *start.parents):
        if any((candidate / marker).exists() for marker in ROOT_MARKERS):
            return candidate
    return start


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def today() -> str:
    return datetime.now(UTC).date().isoformat()


def atomic_write_text(path: Path, text: str) -> None:
    """Escribe en un temporal del mismo directorio y lo renombra: nunca deja el archivo a medias."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def command_env(cwd: Path | None = None) -> dict[str, str]:
    """Entorno de comandos: `python` resuelve al intérprete actual (p. ej. el de .venv).

    Si `cwd` tiene layout `src/`, se antepone a PYTHONPATH: así, en un worktree, los tests
    importan el código del worktree y no la instalación editable del repo principal.
    """
    env = dict(os.environ)
    bin_dir = str(Path(sys.executable).parent)
    env["PATH"] = bin_dir + os.pathsep + env.get("PATH", "")
    if cwd is not None and (cwd / "src").is_dir():
        current = env.get("PYTHONPATH")
        env["PYTHONPATH"] = str(cwd / "src") + (os.pathsep + current if current else "")
    return env


@dataclass(frozen=True)
class CommandResult:
    command: str
    exit_code: int
    output: str
    duration_s: float
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


TIMEOUT_EXIT_CODE = 124


def run_shell(command: str, cwd: Path, timeout_s: float | None = None) -> CommandResult:
    """Ejecuta `command` en una shell y captura stdout+stderr combinados."""
    started = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            env=command_env(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.output.decode() if isinstance(exc.output, bytes) else (exc.output or "")
        return CommandResult(
            command, TIMEOUT_EXIT_CODE, output, time.monotonic() - started, timed_out=True
        )
    return CommandResult(command, proc.returncode, proc.stdout, time.monotonic() - started)


def git(cwd: Path, *args: str, check: bool = True, strip: bool = True) -> str:
    """Salida de git; `strip=False` la deja tal cual (las salidas `-z` no se recortan)."""
    proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} falló: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip() if strip else proc.stdout


class GitError(RuntimeError):
    pass


NO_COMMIT = "sin-commit"


def git_head(cwd: Path) -> str:
    """Hash del commit actual, o `sin-commit` si no hay repo o aún no hay commits."""
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=cwd, capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else NO_COMMIT
