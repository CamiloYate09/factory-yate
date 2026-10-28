"""`factory schedule`: imprime cómo programar los ticks (cron, launchd o `/loop`).

Nunca instala ni modifica nada del sistema: la programación es una decisión explícita del humano.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

INTERVAL_RE = re.compile(r"^(\d+)([mhd])$")


class ScheduleError(ValueError):
    pass


@dataclass(frozen=True)
class Interval:
    value: int
    unit: str

    @property
    def seconds(self) -> int:
        return self.value * {"m": 60, "h": 3600, "d": 86400}[self.unit]

    @property
    def text(self) -> str:
        return f"{self.value}{self.unit}"


def parse_interval(text: str) -> Interval:
    match = INTERVAL_RE.match(text.strip())
    if not match:
        raise ScheduleError(f"Intervalo '{text}' inválido: usa Nm, Nh o Nd (p. ej. 30m, 2h, 1d)")
    interval = Interval(int(match.group(1)), match.group(2))
    limits = {"m": 59, "h": 23, "d": 1}
    if not 1 <= interval.value <= limits[interval.unit]:
        raise ScheduleError(f"Intervalo '{text}' fuera de rango para cron: 1-59m, 1-23h o 1d")
    return interval


def cron_expression(interval: Interval) -> str:
    if interval.unit == "m":
        return f"*/{interval.value} * * * *"
    if interval.unit == "h":
        return f"0 */{interval.value} * * *"
    return "0 9 * * *"


def factory_executable() -> str:
    candidate = Path(sys.executable).parent / "factory"
    return str(candidate) if candidate.exists() else "factory"


def render(root: Path, goal_path: Path, goal_id: str, interval: Interval) -> str:
    exe = factory_executable()
    log = root / ".factory" / "ticks" / f"{goal_id}.cron.log"
    command = f'cd "{root}" && "{exe}" tick "{goal_path}" >> "{log}" 2>&1'
    label = f"factory.{root.name}.{goal_id}"
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{escape(label)}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{escape(exe)}</string>
    <string>--root</string><string>{escape(str(root))}</string>
    <string>tick</string><string>{escape(str(goal_path))}</string>
  </array>
  <key>WorkingDirectory</key><string>{escape(str(root))}</string>
  <key>StartInterval</key><integer>{interval.seconds}</integer>
  <key>StandardOutPath</key><string>{escape(str(log))}</string>
  <key>StandardErrorPath</key><string>{escape(str(log))}</string>
</dict>
</plist>"""
    try:
        relative = goal_path.relative_to(root)
    except ValueError:
        relative = goal_path
    return "\n".join(
        [
            f"Programación de `factory tick` para '{goal_id}' cada {interval.text}.",
            "No se ha instalado nada: copia la opción que prefieras.",
            "",
            "## cron (crontab -e)",
            f"{cron_expression(interval)} {command}",
            "",
            f"## launchd (macOS): guarda como ~/Library/LaunchAgents/{label}.plist",
            f"## y cárgalo con: launchctl load ~/Library/LaunchAgents/{label}.plist",
            plist,
            "",
            "## Claude Code (solo mientras la sesión esté abierta)",
            f"/loop {interval.text} Ejecuta `{exe} tick {relative}` y resume el resultado "
            "(noop, run, skipped, awaiting_review, budget_exhausted o circuit_open).",
        ]
    )
