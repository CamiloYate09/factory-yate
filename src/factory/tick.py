"""Loop por tiempo (`factory tick`): vigilancia idempotente con verificación previa sin coste.

Cada tick verifica primero, sin invocar agentes. Solo si algo falla (y las guardas lo permiten)
lanza una ejecución acotada del loop de objetivo. Las guardas son: bloqueo entre ticks, trabajo
pendiente de revisión, presupuesto diario y cortacircuitos tras fallos repetidos.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from factory.agents.base import AgentRunner
from factory.config import Config
from factory.engine import Limits, LoopEngine
from factory.goal import Goal, GoalError
from factory.inbox import Inbox, InboxEntry
from factory.records import truncate
from factory.state import COMPLETED
from factory.util import atomic_write_text, now_iso
from factory.verify import run_criteria

NOOP = "noop"
RUN = "run"
SKIPPED = "skipped"
AWAITING_REVIEW = "awaiting_review"
BUDGET_EXHAUSTED = "budget_exhausted"
CIRCUIT_OPEN = "circuit_open"


@dataclass
class TickRecord:
    goal_id: str
    result: str
    ts: str = ""
    run_id: str | None = None
    run_status: str | None = None
    cost_usd: float = 0.0
    detail: str = ""


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _alive(pid: int) -> bool:
    if pid <= 0:  # os.kill(-1, 0) señalaría a todos los procesos: nunca es un dueño válido
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class TickStore:
    def __init__(self, state_dir: Path):
        self.base = state_dir

    # ---------------------------------------------------------------- registro de ticks
    def log_path(self, goal_id: str) -> Path:
        return self.base / "ticks" / f"{goal_id}.jsonl"

    def append(self, record: TickRecord) -> None:
        path = self.log_path(record.goal_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        record.ts = record.ts or now_iso()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")

    def read(self, goal_id: str) -> list[TickRecord]:
        path = self.log_path(goal_id)
        if not path.exists():
            return []
        return [TickRecord(**json.loads(line)) for line in path.read_text().splitlines() if line]

    def goals(self) -> list[str]:
        directory = self.base / "ticks"
        return sorted(p.stem for p in directory.glob("*.jsonl")) if directory.exists() else []

    # ---------------------------------------------------------------- bloqueo
    def lock_path(self, goal_id: str) -> Path:
        return self.base / "locks" / f"{goal_id}.lock"

    def _guard(self, goal_id: str) -> int:
        """Serializa la comprobación y la toma del bloqueo entre procesos (flock; se libera solo
        si el proceso muere), para que dos ticks nunca decidan a la vez sobre el mismo bloqueo."""
        guard = self.base / "locks" / f"{goal_id}.guard"
        guard.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(guard, os.O_CREAT | os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX)
        return fd

    def _owner(self, path: Path) -> tuple[int, float]:
        """(pid, inicio). Un archivo ilegible o vacío cuenta como recién creado (mtime)."""
        try:
            owner = json.loads(path.read_text())
            return int(owner["pid"]), float(owner["started"])
        except (OSError, ValueError, KeyError, TypeError):
            try:
                return 0, path.stat().st_mtime
            except OSError:
                return 0, 0.0

    def acquire(self, goal_id: str, stale_after_s: float) -> tuple[bool, str]:
        """(adquirido, detalle). Recupera bloqueos de procesos muertos o demasiado antiguos."""
        path = self.lock_path(goal_id)
        fd = self._guard(goal_id)
        try:
            detail = ""
            if path.exists():
                pid, started = self._owner(path)
                age = time.time() - started
                fresh = age <= stale_after_s
                if fresh and (_alive(pid) or pid == 0):
                    return False, f"otro tick en curso (pid {pid or 'desconocido'})"
                path.unlink(missing_ok=True)
                detail = f"bloqueo obsoleto recuperado (pid {pid}, {age / 60:.0f} min)"
            atomic_write_text(path, json.dumps({"pid": os.getpid(), "started": time.time()}))
            return True, detail
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def release(self, goal_id: str) -> None:
        """Libera el bloqueo solo si es de este proceso."""
        path = self.lock_path(goal_id)
        fd = self._guard(goal_id)
        try:
            if path.exists() and self._owner(path)[0] == os.getpid():
                path.unlink(missing_ok=True)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    # ---------------------------------------------------------------- cortacircuitos
    def breaker_path(self, goal_id: str) -> Path:
        return self.base / "breakers" / f"{goal_id}.json"

    def breaker(self, goal_id: str) -> dict:
        path = self.breaker_path(goal_id)
        if not path.exists():
            return {"open": False, "failures": 0}
        return json.loads(path.read_text())

    def save_breaker(self, goal_id: str, data: dict) -> None:
        atomic_write_text(self.breaker_path(goal_id), json.dumps(data, indent=2) + "\n")

    def reset_breaker(self, goal_id: str) -> None:
        self.save_breaker(goal_id, {"open": False, "failures": 0, "reset_at": now_iso()})

    # ---------------------------------------------------------------- gasto diario
    def spend_path(self, day: str | None = None) -> Path:
        return self.base / "spend" / f"{day or _today()}.json"

    def spent_today(self, goal_id: str) -> float:
        path = self.spend_path()
        return float(json.loads(path.read_text()).get(goal_id, 0.0)) if path.exists() else 0.0

    def add_spend(self, goal_id: str, amount: float) -> None:
        path = self.spend_path()
        data = json.loads(path.read_text()) if path.exists() else {}
        data[goal_id] = round(float(data.get(goal_id, 0.0)) + amount, 6)
        atomic_write_text(path, json.dumps(data, indent=2) + "\n")


def tick(
    config: Config,
    goal: Goal,
    make_runner: Callable[[Config], AgentRunner],
    echo: Callable[[str], None] = print,
) -> TickRecord:
    if goal.mode != "monitor":
        raise GoalError(
            f"'{goal.id}' es un objetivo finito: `factory tick` solo acepta mode: monitor. "
            "Para una tarea con línea de meta usa `factory goal run`."
        )
    store = TickStore(config.state_path)
    acquired, lock_detail = store.acquire(goal.id, config.lock_stale_s)
    if not acquired:
        record = TickRecord(goal.id, SKIPPED, detail=lock_detail)
        store.append(record)
        return record
    try:
        record = _tick(config, goal, make_runner, store, echo)
        record.detail = "; ".join(d for d in (lock_detail, record.detail) if d)
        store.append(record)
        return record
    finally:
        store.release(goal.id)


def _tick(
    config: Config,
    goal: Goal,
    make_runner: Callable[[Config], AgentRunner],
    store: TickStore,
    echo: Callable[[str], None],
) -> TickRecord:
    verification = run_criteria(goal.acceptance, config.root, config.loop.verify_timeout_min * 60)
    if verification.passed:
        breaker = store.breaker(goal.id)
        if breaker.get("failures") and not breaker.get("open"):
            store.save_breaker(goal.id, {**breaker, "failures": 0})
        return TickRecord(goal.id, NOOP, detail=f"{verification.total} criterio(s) en verde")
    failing = ", ".join(verification.failed)
    breaker = store.breaker(goal.id)
    if breaker.get("open"):
        return TickRecord(
            goal.id,
            CIRCUIT_OPEN,
            detail=f"falla {failing}; cortacircuitos abierto: solo se verifica "
            f"(factory tick --reset-breaker)",
        )
    inbox = Inbox(config.state_path)
    pending = inbox.pending_for(goal.id, kind="run", origin="tick")
    if pending:
        return TickRecord(
            goal.id,
            AWAITING_REVIEW,
            detail=f"falla {failing}; pendiente de revisión: {pending[0].id}",
        )
    spent = store.spent_today(goal.id)
    remaining = config.tick.daily_budget_usd - spent
    if remaining <= 0:
        return TickRecord(
            goal.id,
            BUDGET_EXHAUSTED,
            detail=f"falla {failing}; presupuesto diario agotado ({spent:.4f} USD)",
        )
    limits = Limits.from_goal(
        goal,
        max_rounds=config.tick.max_rounds,
        budget=min(config.tick.budget_per_tick_usd, remaining, goal.stop.max_budget_usd),
    )
    echo(f"Falla {failing}: se lanza una ejecución acotada ({limits.max_rounds} rondas máx.)")
    engine: LoopEngine | None = None
    try:
        engine = LoopEngine(
            config, goal, make_runner(config), limits=limits, kind="tick", echo=echo
        )
        state = engine.run()
    except Exception as exc:  # el tick se registra siempre, también si el motor falla
        partial = engine.state if engine else None
        cost = partial.total_cost_usd if partial else 0.0
        store.add_spend(goal.id, cost)
        run_id = partial.run_id if partial else None
        _update_breaker(config, goal, store, inbox, "error", run_id or "-")
        return TickRecord(
            goal.id,
            RUN,
            run_id=run_id,
            run_status="error",
            cost_usd=round(cost, 6),
            detail=f"falla {failing}; error del motor: {truncate(str(exc), 300)}",
        )
    store.add_spend(goal.id, state.total_cost_usd)
    _update_breaker(config, goal, store, inbox, state.status, state.run_id)
    return TickRecord(
        goal.id,
        RUN,
        run_id=state.run_id,
        run_status=state.status,
        cost_usd=round(state.total_cost_usd, 6),
        detail=f"falla {failing}; {truncate(state.stop_reason, 200)}",
    )


def _update_breaker(
    config: Config, goal: Goal, store: TickStore, inbox: Inbox, status: str, run_id: str
) -> None:
    breaker = store.breaker(goal.id)
    if status == COMPLETED:
        store.save_breaker(goal.id, {"open": False, "failures": 0})
        return
    failures = int(breaker.get("failures", 0)) + 1
    opened = failures >= config.tick.circuit_after
    store.save_breaker(
        goal.id,
        {"open": opened, "failures": failures, "last_run": run_id}
        | ({"opened_at": now_iso()} if opened else {}),
    )
    if opened:
        inbox.save(
            InboxEntry(
                id=f"escalado-{goal.id}-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}",
                goal_id=goal.id,
                kind="escalation",
                origin="tick",
                result="circuit_open",
                stop_reason=f"{failures} ticks seguidos sin completar (última: {status})",
                body=(
                    f"# Escalado: {goal.id}\n\n"
                    f"El objetivo de vigilancia `{goal.id}` acumuló {failures} ejecuciones "
                    f"seguidas sin completar (última `{run_id}`: {status}).\n\n"
                    "Los ticks siguientes **solo verifican**: no se invocarán agentes hasta que "
                    "un humano revise el problema y ejecute:\n\n"
                    f"```\nfactory tick {goal.path or goal.id} --reset-breaker\n```\n"
                ),
            )
        )


def summarize(store: TickStore) -> list[str]:
    """Líneas para `factory status`: resumen de vigilancia por objetivo."""
    lines = []
    for goal_id in store.goals():
        records = store.read(goal_id)
        if not records:
            continue
        counts: dict[str, int] = {}
        for record in records:
            counts[record.result] = counts.get(record.result, 0) + 1
        last = records[-1]
        breaker = store.breaker(goal_id)
        cost = sum(r.cost_usd for r in records)
        lines.append(
            f"  {goal_id}: {len(records)} tick(s) · último {last.ts} → {last.result} · "
            + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            + f" · coste {cost:.4f} USD"
            + (" · CORTACIRCUITOS ABIERTO" if breaker.get("open") else "")
        )
    return lines
