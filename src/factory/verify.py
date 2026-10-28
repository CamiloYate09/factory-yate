"""Verificación determinista de los criterios de un objetivo, ejecutada por el orquestador."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from factory.goal import Criterion
from factory.records import truncate
from factory.util import CommandResult, run_shell

SIGNATURE_LINES = 15
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
NORMALIZERS = (
    # Rutas temporales y de usuario cambian entre ejecuciones.
    (re.compile(r"(/private)?/(tmp|var/folders)/[^\s:'\"]*"), "<TMP>"),
    (re.compile(r"/(Users|home)/[^\s:'\"]*"), "<PATH>"),
    # Hashes, direcciones de memoria y números (líneas, tiempos, contadores).
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<ADDR>"),
    (re.compile(r"\b[0-9a-f]{7,40}\b"), "<HASH>"),
    (re.compile(r"\d+(\.\d+)?"), "N"),
    (re.compile(r"[ \t]+"), " "),
)


def normalize(output: str) -> str:
    text = ANSI_RE.sub("", output)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    tail = "\n".join(lines[-SIGNATURE_LINES:])
    for pattern, replacement in NORMALIZERS:
        tail = pattern.sub(replacement, tail)
    return tail


@dataclass
class Verification:
    results: dict[str, CommandResult] = field(default_factory=dict)

    @property
    def criteria(self) -> dict[str, bool]:
        return {name: result.ok for name, result in self.results.items()}

    @property
    def score(self) -> int:
        return sum(self.criteria.values())

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> bool:
        return self.total > 0 and self.score == self.total

    @property
    def failed(self) -> list[str]:
        return [name for name, ok in self.criteria.items() if not ok]

    @property
    def signature(self) -> str:
        """Firma estable del fallo: mismos criterios y mismo error normalizado → misma firma."""
        if self.passed:
            return ""
        parts = [f"{name}\n{normalize(self.results[name].output)}" for name in sorted(self.failed)]
        return hashlib.sha1("\n--\n".join(parts).encode()).hexdigest()[:12]

    def report(self, output_chars: int = 1500) -> str:
        lines = []
        for name, result in self.results.items():
            mark = "✅" if result.ok else "❌"
            suffix = " (tiempo agotado)" if result.timed_out else ""
            lines.append(f"- {mark} {name}: `{result.command}` → código {result.exit_code}{suffix}")
            if not result.ok:
                lines.append("  ```\n" + truncate(result.output.strip(), output_chars) + "\n  ```")
        return "\n".join(lines)


def run_criteria(
    criteria: list[Criterion],
    cwd: Path,
    timeout_s: float | None,
    on_result: Callable[[str, CommandResult], None] | None = None,
) -> Verification:
    verification = Verification()
    for criterion in criteria:
        result = run_shell(criterion.run, cwd=cwd, timeout_s=timeout_s)
        verification.results[criterion.name] = result
        if on_result:
            on_result(criterion.name, result)
    return verification
