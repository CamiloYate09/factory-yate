"""Punto de entrada del CLI `factory`."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from factory import __version__, doctor, features, scaffold, schedule, status
from factory import tick as ticks
from factory.agents.base import AgentRunner
from factory.agents.claude_code import ClaudeCodeRunner
from factory.config import Config, ConfigError, load_config
from factory.engine import EngineError, Limits, LoopEngine, exit_code
from factory.gitops import PreflightError
from factory.goal import Goal, GoalError, load_goal
from factory.inbox import Inbox, InboxError
from factory.util import find_root

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2


def _tail(text: str, lines: int = 20) -> str:
    return "\n".join(text.rstrip().splitlines()[-lines:])


def cmd_features(args: argparse.Namespace) -> int:
    config = load_config(args.root)
    path = config.path(config.harness.feature_list)
    data = features.load(path)
    if args.features_cmd == "validate":
        issues = features.validate(data)
        for issue in issues:
            print(f"✗ {issue}")
        if issues:
            print(f"{path.name}: {len(issues)} problema(s)")
            return EXIT_FAIL
        print(f"{path.name}: válida ({len(data['features'])} features)")
        return EXIT_OK
    if args.features_cmd == "list":
        for feature in sorted(data["features"], key=lambda f: f.get("priority", 0)):
            print(
                f"{feature.get('priority'):>3}  {feature.get('status'):<12} {feature.get('id')}  "
                f"{feature.get('title')}"
            )
        return EXIT_OK
    if args.features_cmd == "start":
        features.start(data, args.id)
        features.save(path, data)
        print(f"'{args.id}' → in_progress")
        return EXIT_OK
    if args.features_cmd == "verify":
        outcome = features.verify(data, args.id, cwd=config.root, timeout_s=args.timeout)
        for result in outcome.results:
            mark = "✓" if result.ok else "✗"
            print(f"{mark} {result.command} (código {result.exit_code}, {result.duration_s:.1f}s)")
        if not outcome.ok:
            failed = outcome.failed
            print(f"\nFALLO: '{args.id}' no pasa a passing. Comando que falló: {failed.command}")
            print(_tail(failed.output))
            return EXIT_FAIL
        features.save(path, data)
        print(f"'{args.id}' → passing (evidencia registrada)")
        return EXIT_OK
    raise AssertionError(args.features_cmd)


def cmd_doctor(args: argparse.Namespace) -> int:
    report = doctor.audit(load_config(args.root))
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(doctor.render(report))
    return EXIT_OK if report.ok else EXIT_FAIL


def _goal_path(args: argparse.Namespace) -> Path:
    path = Path(args.goal)
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


def make_runner(config: Config) -> AgentRunner:
    """Agente real; los tests lo sustituyen por un FakeRunner."""
    return ClaudeCodeRunner(config.agent.command)


def describe_plan(config: Config, goal: Goal, limits: Limits) -> str:
    lines = [goal.describe(), "Roles:"]
    for name in ("maker", "checker"):
        role = goal.role(name, config.roles[name])
        lines.append(
            f"  - {name}: modelo={role.model} permisos={role.permission_mode} prompt={role.prompt}"
        )
        allowed = list(role.allowed_tools)
        if name == "maker":
            allowed += [f"Bash({c.run})" for c in goal.acceptance]
        lines.append(f"      permitido: {', '.join(allowed) or '-'}")
        lines.append(f"      denegado: {', '.join(role.denied_tools) or '-'}")
    lines += [
        f"Rondas máximas: {limits.max_rounds} · presupuesto: {limits.max_budget_usd:.2f} USD",
        f"Worktrees: {config.worktrees_path}/<run-id> (rama factory/<run-id>)",
        f"Estado: {config.state_path}/runs/<run-id>/",
    ]
    return "\n".join(lines)


def cmd_goal(args: argparse.Namespace) -> int:
    config = load_config(args.root)
    goal = load_goal(_goal_path(args), config.loop)
    if args.goal_cmd == "validate":
        print(goal.describe())
        print("\nObjetivo válido.")
        return EXIT_OK
    if goal.mode != "finite":
        raise GoalError(f"'{goal.id}' es de vigilancia (mode: monitor): usa `factory tick`.")
    limits = Limits.from_goal(goal)
    print(describe_plan(config, goal, limits))
    if args.dry_run:
        print("\nSimulación: no se invoca ningún agente, no se crea ninguna rama; coste 0 USD.")
        return EXIT_OK
    engine = LoopEngine(config, goal, make_runner(config), limits=limits)
    state = engine.run()
    print(f"Revisión: factory inbox list · rama {state.branch} · {state.summary}")
    return exit_code(state)


def cmd_inbox(args: argparse.Namespace) -> int:
    inbox = Inbox(load_config(args.root).state_path)
    if args.inbox_cmd == "ack":
        entry = inbox.ack(args.id)
        print(f"'{entry.id}' marcada como revisada ({entry.reviewed_at})")
        return EXIT_OK
    entries = inbox.entries(None if args.all else "pending")
    if not entries:
        print("La bandeja está vacía." if args.all else "No hay entradas pendientes.")
        return EXIT_OK
    for e in entries:
        print(
            f"{e.status:<9} {e.created}  {e.id}  [{e.kind}] {e.result or '-'}  "
            f"rama={e.branch or '-'}  coste={e.cost_usd:.4f} USD"
        )
        if e.question:
            print(f"          pregunta: {e.question}")
    return EXIT_OK


def cmd_status(args: argparse.Namespace) -> int:
    config = load_config(args.root)
    report = status.collect(config)
    tick_lines = ticks.summarize(ticks.TickStore(config.state_path))
    if tick_lines:
        report.extra = ["\nVigilancia (ticks):", *tick_lines]
    print(status.render(report))
    return EXIT_OK


TICK_FAILURE_RESULTS = (ticks.AWAITING_REVIEW, ticks.BUDGET_EXHAUSTED, ticks.CIRCUIT_OPEN)


def cmd_tick(args: argparse.Namespace) -> int:
    config = load_config(args.root)
    goal = load_goal(_goal_path(args), config.loop)
    store = ticks.TickStore(config.state_path)
    if args.reset_breaker:
        store.reset_breaker(goal.id)
        print(f"Cortacircuitos de '{goal.id}' restablecido.")
        return EXIT_OK
    record = ticks.tick(config, goal, make_runner)
    run = f" · ejecución {record.run_id} ({record.run_status})" if record.run_id else ""
    print(f"tick '{goal.id}': {record.result}{run} · coste {record.cost_usd:.4f} USD")
    if record.detail:
        print(f"  {record.detail}")
    if record.result == ticks.RUN:
        return 0 if record.run_status == "completed" else EXIT_FAIL
    return EXIT_FAIL if record.result in TICK_FAILURE_RESULTS else EXIT_OK


def cmd_schedule(args: argparse.Namespace) -> int:
    config = load_config(args.root)
    goal_path = _goal_path(args)
    goal = load_goal(goal_path, config.loop)
    if goal.mode != "monitor":
        raise GoalError(f"'{goal.id}' no es de vigilancia (mode: monitor); no se programa.")
    interval = schedule.parse_interval(args.every)
    print(schedule.render(config.root, goal_path, goal.id, interval))
    return EXIT_OK


def cmd_init(args: argparse.Namespace) -> int:
    target = (args.target or Path.cwd()).resolve()
    commands = [c.strip() for c in args.commands.split(",") if c.strip()] if args.commands else None
    try:
        result = scaffold.init_harness(
            target, commands=commands, force=args.force, entry_file=args.agent_file
        )
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    print(result.render())
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="factory",
        description="Harness y motor de loops para agentes de codificación.",
    )
    parser.add_argument("--version", action="version", version=f"factory {__version__}")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="raíz del repositorio (por defecto: se busca factory.toml o .git hacia arriba)",
    )
    sub = parser.add_subparsers(dest="command")

    init = sub.add_parser("init", help="genera el harness mínimo en un repositorio destino")
    init.add_argument("--target", type=Path, default=None, help="repositorio destino (cwd)")
    init.add_argument(
        "--commands", default=None, help="comandos de verificación separados por comas"
    )
    init.add_argument("--force", action="store_true", help="sobrescribe archivos existentes")
    init.add_argument("--agent-file", default="AGENTS.md", help="archivo de instrucciones")
    init.set_defaults(handler=cmd_init)

    feats = sub.add_parser("features", help="lista de features: validar, activar y verificar")
    feats_sub = feats.add_subparsers(dest="features_cmd", required=True)
    feats_sub.add_parser("validate", help="valida esquema, WIP=1 y evidencia de 'passing'")
    feats_sub.add_parser("list", help="lista las features por prioridad")
    start = feats_sub.add_parser("start", help="marca una feature como activa (WIP=1)")
    start.add_argument("id")
    verify = feats_sub.add_parser(
        "verify", help="ejecuta la verificación y, si pasa, promueve a passing con evidencia"
    )
    verify.add_argument("id")
    verify.add_argument("--timeout", type=float, default=None, help="segundos por comando")
    feats.set_defaults(handler=cmd_features)

    goal = sub.add_parser("goal", help="objetivos (goal.md): validar y ejecutar loops")
    goal_sub = goal.add_subparsers(dest="goal_cmd", required=True)
    validate = goal_sub.add_parser("validate", help="valida un goal.md y muestra los límites")
    validate.add_argument("goal", help="ruta al goal.md")
    run = goal_sub.add_parser(
        "run", help="ejecuta el loop maker-checker hasta cumplir el objetivo o una parada"
    )
    run.add_argument("goal", help="ruta al goal.md")
    run.add_argument(
        "--dry-run", action="store_true", help="muestra el plan sin invocar agentes ni crear ramas"
    )
    goal.set_defaults(handler=cmd_goal)

    inbox = sub.add_parser("inbox", help="bandeja de revisión humana")
    inbox_sub = inbox.add_subparsers(dest="inbox_cmd", required=True)
    inbox_list = inbox_sub.add_parser("list", help="entradas pendientes (o todas con --all)")
    inbox_list.add_argument("--all", action="store_true")
    ack = inbox_sub.add_parser("ack", help="marca una entrada como revisada")
    ack.add_argument("id")
    inbox.set_defaults(handler=cmd_inbox)

    tick = sub.add_parser(
        "tick", help="vigilancia: verifica y, solo si falla, lanza un loop acotado"
    )
    tick.add_argument("goal", help="goal.md con mode: monitor")
    tick.add_argument(
        "--reset-breaker", action="store_true", help="restablece el cortacircuitos del objetivo"
    )
    tick.set_defaults(handler=cmd_tick)

    sched = sub.add_parser("schedule", help="imprime cómo programar los ticks (no instala nada)")
    sched.add_argument("goal", help="goal.md con mode: monitor")
    sched.add_argument("--every", required=True, help="intervalo: Nm, Nh o 1d (p. ej. 30m)")
    sched.set_defaults(handler=cmd_schedule)

    stat = sub.add_parser("status", help="ejecuciones e indicadores de costes silenciosos")
    stat.set_defaults(handler=cmd_status)

    doc = sub.add_parser("doctor", help="audita el harness en sus cinco subsistemas")
    doc.add_argument("--json", action="store_true", help="salida estructurada (JSON)")
    doc.set_defaults(handler=cmd_doctor)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return EXIT_OK
    args.root = (args.root or find_root()).resolve()
    try:
        return args.handler(args)
    except (
        features.FeatureError,
        ConfigError,
        GoalError,
        InboxError,
        PreflightError,
        EngineError,
        schedule.ScheduleError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
