"""Punto de entrada del CLI `factory`."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path

from factory import __version__, doctor, features, scaffold, schedule, status
from factory import intake as intake_mod
from factory import tick as ticks
from factory.agents.base import AgentRunner
from factory.agents.claude_code import ClaudeCodeRunner
from factory.brain import BrainError
from factory.brain import search as brain_search
from factory.brain.captures import CaptureStore
from factory.brain.daily import KINDS, DailyBrain, commit_daily, map_ignored
from factory.brain.importer import import_vault, read_metadata
from factory.brain.libmap import build_map
from factory.config import Config, ConfigError, load_config
from factory.engine import EngineError, Limits, LoopEngine, exit_code
from factory.gitops import PreflightError
from factory.goal import Goal, GoalError, load_goal, parse_goal_text
from factory.inbox import Inbox, InboxError
from factory.land import LandError, land
from factory.requests import RequestError, RequestStore, advance
from factory.state import RunStore
from factory.util import atomic_write_text, command_env, find_root, git

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


def _port(value: str) -> int:
    port = int(value)
    if not 0 <= port <= 65535:
        raise argparse.ArgumentTypeError(f"puerto fuera de rango (0-65535): {port}")
    return port


def cmd_panel(args: argparse.Namespace) -> int:
    from factory.panel import PanelError, main_root, server, snapshot
    from factory.panel.tokens import projects_dir

    root = main_root(args.root)
    projects = projects_dir(args.projects_dir)
    if args.json:
        print(snapshot.to_json(snapshot.build(root, projects)))
        return EXIT_OK
    try:
        return server.serve(root, projects, args.port, args.open)
    except PanelError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE


def cmd_hook(args: argparse.Namespace) -> int:
    from factory.panel import hooks

    return hooks.run()


def cmd_doctor(args: argparse.Namespace) -> int:
    report = doctor.audit(load_config(args.root))
    if args.json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(doctor.render(report))
    return EXIT_OK if report.ok else EXIT_FAIL


def cmd_complexity(args: argparse.Namespace) -> int:
    from factory import complexity

    try:
        informe = complexity.analizar(args.root, args.rutas, base=args.base, umbral=args.max)
    except complexity.ComplexityError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if args.json:
        print(json.dumps(informe.to_dict(), indent=2, ensure_ascii=False))
    else:
        for aviso in informe.avisos:
            print(f"aviso: {aviso}", file=sys.stderr)
        print(complexity.render(informe))
    return EXIT_FAIL if informe.superan else EXIT_OK


def _goal_path(args: argparse.Namespace) -> Path:
    path = Path(args.goal)
    return path if path.is_absolute() else (Path.cwd() / path).resolve()


def make_runner(config: Config) -> AgentRunner:
    """Agente real; los tests lo sustituyen por un FakeRunner."""
    return ClaudeCodeRunner(config.agent.command)


def describe_plan(config: Config, goal: Goal, limits: Limits) -> str:
    prot = goal.protection_for(
        config.root, config.loop.protected_paths, config.effective_verify_command()
    )
    lines = [goal.describe(prot), "Roles:"]
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


REWORKABLE = ("blocked", "max_rounds", "stalled", "budget_exhausted", "agent_error", "interrupted")


def cmd_rework(args: argparse.Namespace, config: Config) -> int:
    answer = args.answer
    if args.answer_file:
        answer = Path(args.answer_file).read_text(encoding="utf-8")
    if not answer or not answer.strip():
        raise GoalError(
            "La respuesta humana es obligatoria para un retrabajo: usa --answer o --answer-file."
        )
    store = RunStore(config.state_path)
    run_dir = store.run_dir(args.run_id)
    if not (run_dir / "state.json").exists():
        raise GoalError(f"No existe la ejecución '{args.run_id}' en {store.runs_dir}")
    parent = store.load(args.run_id)
    if parent.status == "completed":
        raise GoalError(
            f"'{parent.run_id}' terminó completed: no necesita retrabajo. Intégrala con "
            f"`factory land {parent.run_id}`."
        )
    if parent.status not in REWORKABLE:
        raise GoalError(
            f"'{parent.run_id}' está en estado '{parent.status}'; el retrabajo solo aplica a "
            f"{', '.join(REWORKABLE)}."
        )
    if not git(config.root, "branch", "--list", parent.branch):
        raise GoalError(f"La rama {parent.branch} de la ejecución ya no existe.")
    goal_copy = run_dir / "goal.md"
    goal = parse_goal_text(goal_copy.read_text(encoding="utf-8"), config.loop, goal_copy)
    limits = Limits.from_goal(goal, max_rounds=args.rounds, budget=args.budget)
    print(f"Retrabajo de {parent.run_id} ({parent.status}) desde {parent.branch}")
    print(describe_plan(config, goal, limits))
    engine = LoopEngine(
        config, goal, make_runner(config), limits=limits, parent=parent, answer=answer.strip()
    )
    state = engine.run()
    print(f"Revisión: factory inbox list · rama {state.branch} · {state.summary}")
    return exit_code(state)


def _missing_executables(goal: Goal, root: Path) -> list[str]:
    missing = []
    path_env = command_env(root)["PATH"]
    for criterion in goal.acceptance:
        try:
            first = shlex.split(criterion.run)[0]
        except (ValueError, IndexError):
            missing.append(f"{criterion.name}: comando ilegible `{criterion.run}`")
            continue
        found = (root / first).exists() if "/" in first else shutil.which(first, path=path_env)
        if not found:
            missing.append(f"{criterion.name}: no se encuentra `{first}`")
    return missing


def cmd_promote(args: argparse.Namespace, config: Config) -> int:
    path = _goal_path(args)
    goal = load_goal(path, config.loop)
    if not goal.is_draft:
        raise GoalError(
            f"{path} no es un borrador (no tiene status: draft); no hay nada que promover."
        )
    prot = goal.protection_for(
        config.root, config.loop.protected_paths, config.effective_verify_command()
    )
    print(goal.describe(prot))
    for warning in _missing_executables(goal, config.root):
        print(f"AVISO: {warning}")
    target = config.root / "goals" / f"{goal.id}.md"
    if not args.yes:
        print(
            "\nNada cambió. Estos son los comandos que se ejecutarían; si estás de acuerdo, "
            "repite con --yes para promover el borrador."
        )
        return EXIT_OK
    if target.exists():
        raise GoalError(f"Ya existe {target.relative_to(config.root)}: no se sobrescribe.")
    text = path.read_text(encoding="utf-8")
    end = text.index("\n---", 3)
    front = re.sub(r"(?m)^status:\s*draft\s*\n", "", text[:end] + "\n", count=1).rstrip("\n")
    promoted = front + text[end:]
    if parse_goal_text(promoted, config.loop, target).is_draft:
        raise GoalError("No se pudo quitar `status: draft` del borrador.")
    atomic_write_text(target, promoted)
    rel = target.relative_to(config.root)
    if goal.request:
        store = RequestStore(config.state_path)
        try:
            req = store.load(goal.request)
            if req.stage == "accepted":
                req.goal = str(rel)
                advance(store, req, "promoted", f"objetivo {rel}", root=config.root)
        except RequestError as exc:
            print(f"AVISO: no se actualizó la petición {goal.request}: {exc}")
    print(f"\nPromovido: {rel}. Siguiente: factory goal run {rel} --dry-run")
    return EXIT_OK


def cmd_goal(args: argparse.Namespace) -> int:
    config = load_config(args.root)
    if args.goal_cmd == "rework":
        return cmd_rework(args, config)
    if args.goal_cmd == "promote":
        return cmd_promote(args, config)
    goal = load_goal(_goal_path(args), config.loop)
    prot = goal.protection_for(
        config.root, config.loop.protected_paths, config.effective_verify_command()
    )
    if args.goal_cmd == "validate":
        print(goal.describe(prot))
        print("\nObjetivo válido.")
        return EXIT_OK
    goal.require_executable()
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
    report.extra += status.brain_lines(config)
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


def cmd_land(args: argparse.Namespace) -> int:
    config = load_config(args.root)
    try:
        result = land(config, args.run_id, dry_run=args.dry_run, delete_branch=args.delete_branch)
    except LandError as exc:
        print(f"integración rechazada: {exc}", file=sys.stderr)
        return EXIT_FAIL
    print(f"Informe: {result.checks_path}")
    if result.branch_deleted:
        print("Rama de la ejecución borrada.")
    return EXIT_OK


def cmd_intake(args: argparse.Namespace) -> int:
    config = load_config(args.root)
    text = Path(args.file).read_text(encoding="utf-8") if args.file else args.text
    if not text or not text.strip():
        raise GoalError('Falta el texto: `factory intake "<petición>"` o `--file archivo.md`.')
    runner = make_runner(config)
    if args.answer:
        result = intake_mod.answer(config, runner, args.answer, text, budget_usd=args.budget)
    else:
        result = intake_mod.submit(config, runner, text, budget_usd=args.budget)
    if result.decision is None:
        return EXIT_FAIL
    if result.draft:
        rel = result.draft.relative_to(config.root)
        print(f"Revisa el borrador y promuévelo: factory goal promote {rel} --yes")
    return EXIT_OK


def cmd_brain(args: argparse.Namespace) -> int:
    config = load_config(args.root)
    if args.brain_cmd == "import":
        result = import_vault(Path(args.source), config.principal_path, config.root)
        print(
            f"Cerebro principal importado en {result.dest}: {result.notes} notas, "
            f"{result.books} libros, ~{result.tokens:,} tokens (solo .md e índices)."
        )
        if result.gitignore_added:
            print("Añadido a .gitignore: los libros no se versionan.")
        built = build_map(config.principal_path, config.map_path)
        state = f"actualizado ({', '.join(built.changed)})" if built.changed else "sin cambios"
        print(
            f"Mapa de la biblioteca en {built.path}: {built.notes} notas, {built.books} libros, "
            f"sin texto de los libros; {state}."
        )
        if built.dropped:
            print(
                f"AVISO: {built.dropped} nota(s) del catálogo no entran en el mapa porque su "
                "ruta no tiene el formato esperado (`<libro>/…/<nota>.md`)."
            )
        ignored = map_ignored(config)
        if ignored:
            print(
                f"AVISO: `{ignored}/` está en .gitignore, así que el mapa no viajará con el "
                "repo. Quítalo de .gitignore: no contiene texto de los libros."
            )
        elif built.changed:
            print("Versiónalo con `factory brain commit` para que viaje con el repo.")
        return EXIT_OK
    if args.brain_cmd == "status":
        meta = read_metadata(config.principal_path)
        print(f"Cerebro principal: {config.principal_path}")
        if meta:
            print(
                f"  origen {meta['source']} · importado {meta['date']} · {meta['notes']} notas · "
                f"{meta['books']} libros · ~{meta['tokens']:,} tokens · catálogo "
                f"{meta['catalog_sha256'][:12]}"
            )
        else:
            print("  no importado: usa `factory brain import <ruta-del-vault>`")
        print(f"Mapa de la biblioteca: {config.map_path}")
        map_meta = config.map_path / "_map.json"
        if map_meta.is_file():
            info = json.loads(map_meta.read_text(encoding="utf-8"))
            mode = " · en uso (sin texto)" if brain_search.principal_from_map(config) else ""
            print(f"  {info['notes']} notas · {info['books']} libros{mode}")
        else:
            print("  no generado: se crea con `factory brain import`")
        return EXIT_OK
    if args.brain_cmd == "search":
        notice_to = sys.stderr if args.json else sys.stdout  # --json: stdout solo con el JSON
        if args.brain in ("all", "principal") and brain_search.principal_from_map(config):
            print(
                "Cerebro principal no importado en este equipo: resultados del mapa de la "
                "biblioteca (citas, sin texto). Importa tu copia con "
                "`factory brain import <ruta-del-vault>`.",
                file=notice_to,
            )
        elif (
            args.brain in ("all", "principal")
            and not (config.principal_path / "_catalog.jsonl").is_file()
        ):
            print(
                "Cerebro principal no disponible: impórtalo con "
                "`factory brain import <ruta-del-vault>`. Se busca solo en el diario.",
                file=notice_to,
            )
        hits = brain_search.search(config, args.query, args.brain, args.limit)
        if args.json:
            print(
                json.dumps(
                    [
                        {
                            "brain": h.entry.brain,
                            "path": h.entry.path,
                            "abs_path": str(h.entry.abs_path),
                            "title": h.entry.title,
                            "citation": h.entry.citation(),
                            "tokens": h.entry.tokens,
                            "score": h.score,
                        }
                        for h in hits
                    ],
                    indent=2,
                    ensure_ascii=False,
                )
            )
            return EXIT_OK
        if not hits:
            print(
                f"Sin resultados para '{args.query}'. El cerebro principal está en inglés: "
                "prueba con términos en inglés ('rate limiting' en lugar de 'límite de tasa')."
            )
            return EXIT_OK
        for hit in hits:
            print(f"[{hit.score:g}] {hit.entry.citation()} — {hit.entry.title}")
            print(f"      {hit.entry.brain}: {hit.entry.path} (~{hit.entry.tokens} tokens)")
        return EXIT_OK
    daily = DailyBrain(config.daily_path)
    if args.brain_cmd == "learn":
        text = Path(args.file).read_text(encoding="utf-8") if args.file else args.text
        if not text or not text.strip():
            raise BrainError('Falta el aprendizaje: `factory brain learn "…"` o `--file nota.md`.')
        tags = [t for t in (args.tags or "").split(",") if t.strip()]
        path = daily.add(text, kind=args.kind, title=args.title, tags=tags)
        print(f"Aprendizaje guardado: {path.relative_to(config.root)}")
        print("Recuerda versionarlo con `factory brain commit`.")
        return EXIT_OK
    if args.brain_cmd == "commit":
        commit, fallback = commit_daily(config, args.message)
        if commit is None:
            print("El cerebro diario no tiene cambios que commitear, y el mapa tampoco.")
            return EXIT_OK
        if fallback:
            print("AVISO: git no tiene identidad configurada; se usó la de reserva de factory.")
        print(f"Commit {commit[:10]} solo con el cerebro diario y el mapa (sin push).")
        return EXIT_OK
    captures = CaptureStore(config.state_path)
    if args.brain_cmd == "pending":
        pending = captures.pending()
        if not pending:
            print("No hay capturas pendientes.")
        for capture in pending:
            print(f"{capture.id}  [{capture.kind}] {capture.title}  ({capture.source})")
        return EXIT_OK
    if args.brain_cmd == "accept":
        capture = captures.load(captures.path(args.id))
        path = daily.add(
            capture.text,
            kind=capture.kind,
            title=capture.title,
            tags=capture.tags,
            source=capture.source,
        )
        captures.remove(capture.id)
        print(
            f"Captura aceptada: {path.relative_to(config.root)} "
            "(versiónala con factory brain commit)"
        )
        return EXIT_OK
    if args.brain_cmd == "reject":
        target = captures.reject(args.id)
        print(f"Captura descartada (queda constancia en {target.relative_to(config.root)})")
        return EXIT_OK
    if args.brain_cmd == "reindex":
        errors = daily.reindex()
        print(f"Cerebro diario reindexado: {len(daily.note_paths()) - len(errors)} nota(s).")
        for relative, error in errors:
            print(f"✗ {relative}: {error}")
        return EXIT_FAIL if errors else EXIT_OK
    raise AssertionError(args.brain_cmd)


def cmd_team(args: argparse.Namespace) -> int:
    from factory.team import TeamError
    from factory.team import lineup as team_lineup
    from factory.team import roster as team_roster

    config = load_config(args.root)
    plantilla = team_roster.load_roster(config.root)
    if args.team_cmd == "validate":
        if args.json:
            data = {"ok": plantilla.ok, "errores": plantilla.errors}
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            for error in plantilla.errors:
                print(f"✗ {error}")
            if plantilla.errors:
                print(f"Plantilla con {len(plantilla.errors)} error(es).")
            else:
                print(f"Plantilla válida: {len(plantilla.members)} miembro(s) del equipo.")
        return EXIT_OK if plantilla.ok else EXIT_FAIL
    for error in plantilla.errors:  # list y lineup siguen con los miembros válidos
        print(f"aviso: plantilla: {error}", file=sys.stderr)
    if args.team_cmd == "list":
        if args.json:
            print(json.dumps(plantilla.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(team_roster.render(plantilla))
        return EXIT_OK
    if args.team_cmd == "lineup":
        try:
            peticion = team_lineup.load_peticion(args.peticion, args.peticion_file)
            if args.paths is not None:
                if args.base is not None:
                    print("aviso: con --paths se ignora --base", file=sys.stderr)
                base, rutas = None, team_lineup.normalize_paths(args.paths)
            else:
                base = "HEAD" if args.base is None else args.base
                rutas = team_lineup.changed_paths(config.root, base)
        except TeamError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return EXIT_USAGE
        result = team_lineup.convocar(plantilla, rutas, peticion is not None, base)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        else:
            print(team_lineup.render(result))
        return EXIT_OK
    raise AssertionError(args.team_cmd)


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
    promote = goal_sub.add_parser(
        "promote", help="convierte un borrador del intake en objetivo ejecutable (con --yes)"
    )
    promote.add_argument("goal", help="ruta al borrador (goals/drafts/<id>.md)")
    promote.add_argument("--yes", action="store_true", help="confirma la promoción")
    rework = goal_sub.add_parser(
        "rework", help="continúa una ejecución atascada desde su rama, con tu respuesta"
    )
    rework.add_argument("run_id", help="identificador de la ejecución (factory status)")
    rework.add_argument("--answer", default=None, help="respuesta humana para el maker")
    rework.add_argument("--answer-file", default=None, help="archivo con la respuesta humana")
    rework.add_argument(
        "--rounds", type=int, default=None, help="rondas máximas (por defecto, las del objetivo)"
    )
    rework.add_argument("--budget", type=float, default=None, help="presupuesto en USD")
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

    intake_p = sub.add_parser(
        "intake", help="triaje de una petición: ACCEPT (borrador), NEEDS-INFO o REJECT"
    )
    intake_p.add_argument("text", nargs="?", default=None, help="texto de la petición o respuesta")
    intake_p.add_argument("--file", default=None, help="archivo con la petición o la respuesta")
    intake_p.add_argument(
        "--answer", default=None, metavar="REQUEST_ID", help="responde a una petición NEEDS-INFO"
    )
    intake_p.add_argument("--budget", type=float, default=1.0, help="presupuesto en USD (1.0)")
    intake_p.set_defaults(handler=cmd_intake)

    brain = sub.add_parser("brain", help="cerebros de conocimiento: principal y diario")
    brain_sub = brain.add_subparsers(dest="brain_cmd", required=True)
    brain_import = brain_sub.add_parser(
        "import", help="importa (o refresca) el vault de libros como cerebro principal"
    )
    brain_import.add_argument("source", help="carpeta del vault con _catalog.jsonl")
    brain_sub.add_parser("status", help="estado de los cerebros")
    search_p = brain_sub.add_parser("search", help="busca en los cerebros y cita las notas")
    search_p.add_argument("query")
    search_p.add_argument("--brain", choices=("all", "principal", "diario"), default="all")
    search_p.add_argument("--limit", type=int, default=None)
    search_p.add_argument("--json", action="store_true")
    learn = brain_sub.add_parser("learn", help="añade un aprendizaje al cerebro diario")
    learn.add_argument("text", nargs="?", default=None, help="texto del aprendizaje")
    learn.add_argument("--file", default=None, help="archivo con el aprendizaje")
    learn.add_argument("--kind", choices=KINDS, default="learning")
    learn.add_argument("--title", default=None)
    learn.add_argument("--tags", default=None, help="etiquetas separadas por comas")
    brain_sub.add_parser("reindex", help="reconstruye el catálogo e índices del cerebro diario")
    brain_sub.add_parser("pending", help="capturas de los loops pendientes de revisión")
    accept = brain_sub.add_parser("accept", help="convierte una captura en nota del cerebro diario")
    accept.add_argument("id")
    reject = brain_sub.add_parser("reject", help="descarta una captura")
    reject.add_argument("id")
    commit_p = brain_sub.add_parser(
        "commit", help="commit solo de los cambios del cerebro diario (sin push)"
    )
    commit_p.add_argument(
        "-m", "--message", default="Cerebro diario: nuevos aprendizajes", help="mensaje del commit"
    )
    brain.set_defaults(handler=cmd_brain)

    team = sub.add_parser("team", help="el equipo ideal: plantilla, validación y convocatoria")
    team_sub = team.add_subparsers(dest="team_cmd", required=True)
    team_list = team_sub.add_parser(
        "list", help="formación 4-3-3 con el técnico, el árbitro y las vacantes"
    )
    team_list.add_argument("--json", action="store_true", help="salida estructurada (JSON)")
    team_validate = team_sub.add_parser(
        "validate", help="valida el frontmatter de los agentes del equipo (.claude/agents/)"
    )
    team_validate.add_argument("--json", action="store_true", help="salida estructurada (JSON)")
    team_lineup = team_sub.add_parser(
        "lineup", help="sugiere la convocatoria a partir de los cambios y de la petición"
    )
    team_lineup.add_argument(
        "--base", default=None, metavar="REF", help="referencia git del diff (HEAD)"
    )
    team_lineup.add_argument(
        "--paths", nargs="+", default=None, metavar="RUTA", help="rutas cambiadas (sin git)"
    )
    team_peticion = team_lineup.add_mutually_exclusive_group()
    team_peticion.add_argument(
        "--peticion", default=None, metavar="TEXTO", help="texto de la petición de producto"
    )
    team_peticion.add_argument(
        "--peticion-file", default=None, metavar="ARCHIVO", help="archivo con la petición"
    )
    team_lineup.add_argument("--json", action="store_true", help="salida estructurada (JSON)")
    team.set_defaults(handler=cmd_team)

    land_p = sub.add_parser(
        "land", help="integra en main una ejecución completed, tras verificar el merge exacto"
    )
    land_p.add_argument("run_id", help="identificador de la ejecución")
    land_p.add_argument(
        "--dry-run", action="store_true", help="solo verifica; no cambia ramas ni la bandeja"
    )
    land_p.add_argument(
        "--delete-branch", action="store_true", help="borra la rama de la ejecución al integrar"
    )
    land_p.set_defaults(handler=cmd_land)

    panel_p = sub.add_parser(
        "panel", help="panel local de tokens, revisiones y tareas (solo lectura, 127.0.0.1)"
    )
    panel_p.add_argument("--port", type=_port, default=8765, help="puerto local (8765 por defecto)")
    panel_p.add_argument("--json", action="store_true", help="imprime la instantánea y termina")
    panel_p.add_argument("--open", action="store_true", help="abre el panel en el navegador")
    panel_p.add_argument(
        "--projects-dir",
        type=Path,
        help="proyectos de Claude Code (por defecto, $CLAUDE_CONFIG_DIR/projects o ~/.claude)",
    )
    panel_p.set_defaults(handler=cmd_panel)

    hook_p = sub.add_parser(
        "hook", help="registra un evento de hook de Claude Code para el panel (lee stdin)"
    )
    hook_p.set_defaults(handler=cmd_hook)

    stat = sub.add_parser("status", help="ejecuciones e indicadores de costes silenciosos")
    stat.set_defaults(handler=cmd_status)

    cx = sub.add_parser(
        "complexity", help="complejidad ciclomática por función (rangos A–F y delta frente a REF)"
    )
    cx.add_argument(
        "rutas",
        nargs="*",
        metavar="RUTAS",
        help="archivos o directorios (por defecto, los *.py versionados)",
    )
    cx.add_argument(
        "--base",
        default=None,
        metavar="REF",
        help="solo los *.py cambiados frente a REF, con su complejidad en REF y el delta",
    )
    cx.add_argument(
        "--max",
        type=int,
        default=None,
        metavar="N",
        help="termina en 1 si alguna función del alcance supera N",
    )
    cx.add_argument("--json", action="store_true", help="salida estructurada (JSON)")
    cx.set_defaults(handler=cmd_complexity)

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
        RequestError,
        BrainError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_USAGE
