"""Estado de implementación: features, cambios OpenSpec activos, ejecuciones y bandeja."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from factory.inbox import Inbox
from factory.state import RUNNING, RunState

GROUP_HEADING = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$")
TASK_LINE = re.compile(r"^\s*-\s+\[([^\]]*)\]\s*(.*)$")
TASK_ID = re.compile(r"^(\d+(?:\.\d+)*)\s+(.*)$")
BACKTICKS = re.compile(r"`([^`]+)`")
FEATURES_FILE = "feature_list.json"
CHANGES_DIR = Path("openspec") / "changes"


def alive(pid: Any) -> bool:
    """Mismo criterio que el bloqueo del tick: `pid > 0` y `os.kill(pid, 0)` no falla."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def parse_tasks(text: str) -> list[dict[str, Any]]:
    """Grupos `## N. Título` con sus casillas; solo `x` (con o sin espacios) cuenta como hecha."""
    groups: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in text.splitlines():
        heading = GROUP_HEADING.match(line)
        if heading:
            current = {
                "number": int(heading.group(1)),
                "title": heading.group(2),
                "ids": BACKTICKS.findall(heading.group(2)),
                "tasks": [],
            }
            groups.append(current)
            continue
        if line.startswith("## "):  # sección sin número (p. ej. "Workflow follow-up")
            current = None
            continue
        task = TASK_LINE.match(line)
        if task and current is not None and not line.startswith((" ", "\t")):
            body = task.group(2)
            numbered = TASK_ID.match(body)
            current["tasks"].append(
                {
                    "id": numbered.group(1) if numbered else "",
                    "text": numbered.group(2) if numbered else body,
                    "done": task.group(1).strip().lower() == "x",
                }
            )
    for group in groups:
        group["done"] = sum(t["done"] for t in group["tasks"])
        group["total"] = len(group["tasks"])
    return groups


def _features(root: Path, warnings: list[str]) -> list[dict[str, Any]]:
    path = root / FEATURES_FILE
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = data["features"]
        if not isinstance(raw, list):
            raise TypeError("`features` no es una lista")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        warnings.append(f"{FEATURES_FILE}: no se pudo leer ({exc})")
        return []
    features = []
    for item in raw:
        if not isinstance(item, dict) or not isinstance(item.get("id"), str):
            continue
        evidence = [e for e in item.get("evidence") or [] if isinstance(e, dict)]
        last: dict[str, dict[str, Any]] = {}
        for entry in evidence:  # la última evidencia de cada comando
            last[str(entry.get("command", ""))] = entry
        features.append(
            {
                "id": item["id"],
                "priority": item.get("priority"),
                "area": item.get("area", ""),
                "title": item.get("title", ""),
                "status": item.get("status", ""),
                "user_visible_behavior": item.get("user_visible_behavior", ""),
                "verification": item.get("verification") or [],
                "manual_checks": item.get("manual_checks") or [],
                "notes": item.get("notes", ""),
                "evidence": list(last.values()),
                "groups": [],
                "runs": [],
            }
        )
    features.sort(key=lambda f: f["priority"] if isinstance(f["priority"], int) else 1 << 30)
    return features


def _changes(root: Path, warnings: list[str]) -> list[dict[str, Any]]:
    base = root / CHANGES_DIR
    if not base.is_dir():
        return []
    changes = []
    for directory in sorted(p for p in base.iterdir() if p.is_dir() and p.name != "archive"):
        tasks_md = directory / "tasks.md"
        groups: list[dict[str, Any]] = []
        if tasks_md.exists():
            try:
                groups = parse_tasks(tasks_md.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError) as exc:
                warnings.append(f"{tasks_md.relative_to(root)}: no se pudo leer ({exc})")
        changes.append(
            {
                "name": directory.name,
                "groups": groups,
                "done": sum(g["done"] for g in groups),
                "total": sum(g["total"] for g in groups),
            }
        )
    return changes


def _runs(runs: list[RunState]) -> list[dict[str, Any]]:
    rows = []
    for run in sorted(runs, key=lambda r: r.started, reverse=True):
        last = run.rounds[-1] if run.rounds else None
        verdict = next((r.checker_verdict for r in reversed(run.rounds) if r.checker_verdict), "")
        rows.append(
            {
                "run_id": run.run_id,
                "goal_id": run.goal_id,
                "feature": run.feature,
                "kind": run.kind,
                "status": run.status,
                "alive": run.status == RUNNING and alive(run.pid),
                "started": run.started,
                "finished": run.finished,
                "round": last.number if last else 0,
                "score": last.score if last else 0,
                "criteria_total": run.criteria_total,
                "verdict": verdict,
                "cost_usd": round(run.total_cost_usd, 4),
                "stop_reason": run.stop_reason,
                "branch": run.branch,
            }
        )
    return rows


def _inbox(state_dir: Path, warnings: list[str]) -> dict[str, Any]:
    try:
        pending = Inbox(state_dir).pending()
    except Exception as exc:  # una entrada mal formada no debe tumbar el panel
        warnings.append(f"bandeja: no se pudo leer ({exc})")
        return {"pending": 0, "ids": []}
    return {"pending": len(pending), "ids": [e.id for e in pending]}


def collect(
    root: Path, state_dir: Path, runs: list[RunState], warnings: list[str]
) -> dict[str, Any]:
    """Sección `tasks` de la instantánea."""
    features = _features(root, warnings)
    changes = _changes(root, warnings)
    by_id = {f["id"]: f for f in features}
    for change in changes:
        for group in change["groups"]:
            linked = next((i for i in group["ids"] if i in by_id), None)
            group["feature"] = linked
            if linked:
                by_id[linked]["groups"].append(
                    {"change": change["name"], **{k: v for k, v in group.items() if k != "ids"}}
                )
            del group["ids"]
    run_rows = _runs(runs)
    for row in run_rows:
        if row["feature"] in by_id:
            by_id[row["feature"]]["runs"].append(row["run_id"])
    counts: dict[str, int] = {}
    for feature in features:
        counts[feature["status"]] = counts.get(feature["status"], 0) + 1
    return {
        "features": features,
        "status_counts": counts,
        "in_progress": [f["id"] for f in features if f["status"] == "in_progress"],
        "changes": changes,
        "runs": run_rows,
        "inbox": _inbox(state_dir, warnings),
    }
