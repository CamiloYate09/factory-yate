"""Motor del loop maker-checker (diseño D3).

Cada ronda: maker en sesión nueva → comprobación de alcance → instantánea → verificación
determinista → checker de solo lectura (con guarda de árbol) → decisión del orquestador →
ratchet → persistencia → retroalimentación. Las decisiones de control viven aquí, en código
determinista, nunca en los prompts.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import resources

from factory import artifacts, features
from factory.agents.base import AgentRequest, AgentResult, AgentRunner
from factory.config import Config, RoleConfig
from factory.gitops import Worktree, create_worktree, diffstat, preflight, remove_worktree
from factory.goal import Goal, out_of_scope
from factory.inbox import Inbox, InboxError, run_entry
from factory.protection import violations as find_protected
from factory.records import EventLog, append_result
from factory.schemas import (
    CHECKER_VERDICT_SCHEMA,
    MAKER_REPORT_SCHEMA,
    Verdict,
    parse_maker_report,
    parse_verdict,
)
from factory.state import (
    COMPLETED,
    INTERRUPTED,
    RoundRecord,
    RunState,
    RunStore,
    build_summary,
    new_run_id,
)
from factory.util import atomic_write_text, git, now_iso
from factory.verify import Verification, run_criteria

EXIT_CODES = {
    COMPLETED: 0,
    "stalled": 3,
    "max_rounds": 4,
    "budget_exhausted": 5,
    "blocked": 6,
    "agent_error": 7,
    INTERRUPTED: 130,
}
DIFF_LIMIT = 60_000


class EngineError(RuntimeError):
    pass


def load_prompt(config: Config, role: RoleConfig) -> str:
    """Prompt del rol desde el repo; si no existe, la plantilla empaquetada con factory."""
    path = config.root / role.prompt
    if path.exists():
        return path.read_text(encoding="utf-8")
    packaged = resources.files("factory") / "templates" / role.prompt
    if packaged.is_file():
        return packaged.read_text(encoding="utf-8")
    raise EngineError(f"No existe el prompt del rol: {role.prompt}")


@dataclass
class Limits:
    max_rounds: int
    max_budget_usd: float
    no_progress_rounds: int
    consecutive_passes: int
    round_timeout_s: float

    @classmethod
    def from_goal(
        cls, goal: Goal, max_rounds: int | None = None, budget: float | None = None
    ) -> Limits:
        return cls(
            max_rounds=max_rounds or goal.stop.max_rounds,
            max_budget_usd=budget if budget is not None else goal.stop.max_budget_usd,
            no_progress_rounds=goal.stop.no_progress_rounds,
            consecutive_passes=goal.stop.consecutive_passes,
            round_timeout_s=goal.stop.round_timeout_min * 60,
        )


@dataclass
class RoundOutcome:
    record: RoundRecord
    feedback: str = ""
    stall_signature: str = ""
    agent_error: bool = False
    blocked: bool = False
    verification: Verification | None = None
    verdict: Verdict | None = None


@dataclass
class LoopEngine:
    config: Config
    goal: Goal
    runner: AgentRunner
    limits: Limits | None = None
    kind: str = "goal"
    echo: Callable[[str], None] = print
    parent: RunState | None = None  # retrabajo: ejecución padre
    answer: str = ""  # retrabajo: respuesta humana
    store: RunStore = field(init=False)
    inbox: Inbox = field(init=False)

    def __post_init__(self) -> None:
        self.limits = self.limits or Limits.from_goal(self.goal)
        self.store = RunStore(self.config.state_path)
        self.inbox = Inbox(self.config.state_path)
        self.roles = {
            name: self.goal.role(name, self.config.roles[name]) for name in ("maker", "checker")
        }
        self.prompts = {name: load_prompt(self.config, role) for name, role in self.roles.items()}
        self.protection = self.goal.protection_for(
            self.config.root,
            self.config.loop.protected_paths,
            self.config.effective_verify_command(),
        )
        self.state: RunState | None = None

    # ------------------------------------------------------------------ ciclo de vida
    def run(self) -> RunState:
        self.goal.require_executable()  # defensa en profundidad: un borrador nunca se ejecuta
        root = self.config.root
        base = preflight(root, self.config.loop.main_branch)
        start = base
        if self.parent:
            base = self.parent.base_commit
            start = git(root, "rev-parse", f"refs/heads/{self.parent.branch}")
        self._check_feature()
        state = RunState(
            run_id=new_run_id(self.goal.id),
            goal_id=self.goal.id,
            objective=self.goal.objective,
            base_commit=base,
            feature=self.goal.feature,
            kind=self.kind,
            criteria_total=len(self.goal.acceptance),
            manual_checks=self._manual_checks(),
            parent_run_id=self.parent.run_id if self.parent else "",
            start_commit=start,
        )
        self.store.create(state, self.goal.raw)
        self.state = state
        self.events = EventLog(self.store.run_dir(state.run_id))
        worktree: Worktree | None = None
        try:
            worktree = create_worktree(
                root, self.config.worktrees_path, state.run_id, base, start_point=start
            )
            if self.parent:
                self._ack_parent(state)
            state.branch, state.worktree = worktree.branch, str(worktree.path)
            self.store.save(state, self.limits.max_rounds)
            self.echo(f"Ejecución {state.run_id} en {worktree.path} (rama {worktree.branch})")
            self._loop(state, worktree)
        except KeyboardInterrupt:
            if worktree:
                worktree.reset_to(worktree.head())
            self._stop(state, INTERRUPTED, "interrumpido por el usuario (SIGINT)")
        except Exception as exc:
            self._stop(state, INTERRUPTED, f"error interno del orquestador: {exc}")
            raise
        finally:
            self._finalize(state, worktree)
        return state

    def _initial_feedback(self) -> str:
        """En un retrabajo, la respuesta humana y el contexto de la ejecución padre."""
        if not self.parent:
            return ""
        parts = [f"RESPUESTA HUMANA (retrabajo de {self.parent.run_id}): {self.answer}"]
        if self.parent.question:
            parts.append(f"Pregunta que hizo la ejecución anterior: {self.parent.question}")
        parts.append(
            f"La ejecución anterior terminó {self.parent.status}: {self.parent.stop_reason}"
        )
        if self.parent.rounds:
            last = self.parent.rounds[-1]
            failed = [name for name, ok in last.criteria.items() if not ok]
            if failed:
                parts.append("Criterios que fallaban: " + ", ".join(failed))
            if last.note:
                parts.append("Notas de su última ronda: " + last.note)
        parts.append("Partes de la punta de su rama: su trabajo ya está en el árbol.")
        return "\n".join(parts)

    def _ack_parent(self, state: RunState) -> None:
        try:
            self.inbox.ack(self.parent.run_id, resolution=f"retrabajo → {state.run_id}")
        except InboxError:
            pass  # sin entrada o ya revisada: nada que cerrar

    def _check_feature(self) -> None:
        if not self.goal.feature:
            return
        data = features.load(self.config.path(self.config.harness.feature_list))
        features.find(data, self.goal.feature)

    def _manual_checks(self) -> int:
        if not self.goal.feature:
            return 0
        data = features.load(self.config.path(self.config.harness.feature_list))
        return len(features.find(data, self.goal.feature).get("manual_checks") or [])

    def _loop(self, state: RunState, wt: Worktree) -> None:
        limits = self.limits
        baseline = self._verify(wt, 0)
        state.best_score, state.best_commit, state.best_round = baseline.score, wt.start, 0
        self.store.save(state, limits.max_rounds)
        feedback, passes, errors, stall = self._initial_feedback(), 0, 0, []
        for number in range(1, limits.max_rounds + 1):
            if state.total_cost_usd >= limits.max_budget_usd:
                return self._stop(state, "budget_exhausted", self._budget_reason(state))
            outcome = self._round(state, wt, number, feedback)
            state.rounds.append(outcome.record)
            self._write_round(state, outcome)
            self.store.save(state, limits.max_rounds)
            self._result_row(state, outcome.record)
            self.echo(self._round_line(outcome.record))
            feedback = outcome.feedback
            if outcome.blocked:
                return self._stop(state, "blocked", "el maker necesita una decisión humana")
            errors = errors + 1 if outcome.agent_error else 0
            if errors >= self.config.loop.agent_error_rounds:
                return self._stop(
                    state,
                    "agent_error",
                    f"{errors} ronda(s) seguidas con error del agente: {outcome.record.note}",
                )
            passes = passes + 1 if outcome.record.approved else 0
            if passes >= limits.consecutive_passes:
                return self._stop(
                    state, COMPLETED, f"criterios y checker aprobados en {passes} ronda(s) seguidas"
                )
            stall = stall + [outcome.stall_signature] if outcome.stall_signature else []
            recent = stall[-limits.no_progress_rounds :]
            if len(recent) == limits.no_progress_rounds and len(set(recent)) == 1:
                state.blockers.append(
                    f"la misma firma de fallo ({recent[0]}) se repitió {len(recent)} rondas"
                )
                return self._stop(
                    state,
                    "stalled",
                    f"sin progreso: firma {recent[0]} repetida {len(recent)} veces",
                )
            if state.total_cost_usd >= limits.max_budget_usd:
                return self._stop(state, "budget_exhausted", self._budget_reason(state))
        self._stop(state, "max_rounds", f"se alcanzaron las {limits.max_rounds} rondas máximas")

    def _budget_reason(self, state: RunState) -> str:
        return (
            f"presupuesto agotado: {state.total_cost_usd:.4f} de "
            f"{self.limits.max_budget_usd:.2f} USD"
        )

    def _stop(self, state: RunState, status: str, reason: str) -> None:
        state.status, state.stop_reason = status, reason

    # ------------------------------------------------------------------ una ronda
    def _round(self, state: RunState, wt: Worktree, number: int, feedback: str) -> RoundOutcome:
        started = time.monotonic()
        record = RoundRecord(number=number, started=now_iso())
        pre_commit = wt.head()
        maker = self._invoke(
            state, number, "maker", self._maker_prompt(state, number, feedback), wt
        )
        record.cost_usd += maker.cost_usd
        record.maker_input_tokens = maker.input_tokens
        record.maker_model = maker.model or self.roles["maker"].model
        if not maker.ok:
            wt.reset_to(pre_commit)
            record.reverted_to = pre_commit
            record.decision, record.note = "error", f"error del maker: {maker.error}"
            record.next_plan = "reintentar la ronda"
            return self._close(record, started, agent_error=True, feedback=feedback)

        report, report_errors = parse_maker_report(maker.output)
        if report:
            record.maker_status, record.maker_summary = report.status, report.summary
        else:
            record.maker_status = "informe inválido"
            record.note = "informe del maker inválido: " + "; ".join(report_errors)

        changed = wt.changed_files(pre_commit)
        violations = out_of_scope(changed, self.goal)
        if violations:
            wt.reset_to(pre_commit)
            record.reverted_to = pre_commit
            record.changed_files = changed
            record.decision = "scope_revert"
            record.note = "violación de alcance (ronda revertida): " + ", ".join(violations)
            record.next_plan = "repetir sin tocar rutas fuera del alcance"
            fb = (
                "La ronda anterior se REVIRTIÓ por tocar rutas fuera del alcance: "
                + ", ".join(violations)
                + ". No modifiques esos archivos."
            )
            return self._close(record, started, feedback=fb, stall="scope:" + ",".join(violations))

        record.changed_files = changed
        commit = wt.snapshot(f"factory({state.run_id}): ronda {number}") or pre_commit
        record.commit = commit

        found = find_protected(wt.name_status(state.base_commit), self.protection)
        if found:
            wt.reset_to(pre_commit)
            record.reverted_to = pre_commit
            listed = ", ".join(str(v) for v in found)
            record.protected_violations = [str(v) for v in found]
            record.decision = "protected_revert"
            record.note = _join(record.note, f"rutas protegidas (ronda revertida): {listed}")
            record.next_plan = "repetir sin modificar, borrar ni renombrar archivos protegidos"
            fb = (
                f"La ronda anterior se REVIRTIÓ por cambiar archivos protegidos: {listed}. "
                "Puedes CREAR archivos nuevos (por ejemplo, tests nuevos), pero no modificar, "
                "borrar ni renombrar los existentes protegidos. Si de verdad hace falta, termina "
                "con status needs_human y explica por qué."
            )
            return self._close(
                record, started, feedback=fb, stall="protected:" + ",".join(v.path for v in found)
            )

        if report and report.status == "needs_human":
            record.human_needed = True
            state.question = report.question or report.summary
            record.decision = "keep"
            record.next_plan = "esperar la decisión humana"
            return self._close(record, started, blocked=True)

        verification = self._verify(wt, number)
        record.criteria, record.score = verification.criteria, verification.score
        record.signature = verification.signature

        verdict: Verdict | None = None
        if state.total_cost_usd >= self.limits.max_budget_usd:
            record.checker_verdict = "omitido"
            record.note = _join(
                record.note, "presupuesto agotado tras el maker: checker no invocado"
            )
            self._ratchet(state, wt, record, verification.score, commit)
            return self._close(record, started, stall=record.signature, verification=verification)
        before = wt.tree_hash()
        checker = self._invoke(
            state,
            number,
            "checker",
            self._checker_prompt(state, number, wt, pre_commit, verification),
            wt,
        )
        record.cost_usd += checker.cost_usd
        record.checker_model = checker.model or self.roles["checker"].model
        role_violation = wt.tree_hash() != before
        if role_violation:
            wt.reset_to(commit)
            record.note = _join(record.note, "el checker modificó archivos: veredicto descartado")
        elif not checker.ok:
            record.note = _join(record.note, f"error del checker: {checker.error}")
        else:
            verdict, errors = parse_verdict(checker.output)
            if verdict is None:
                record.note = _join(record.note, "veredicto inválido: " + "; ".join(errors))
        if verdict:
            record.checker_verdict = verdict.verdict
            record.findings = [f.__dict__ for f in verdict.findings]
        else:
            record.checker_verdict = "inválido"
        record.approved = verification.passed and verdict is not None and verdict.approves

        self._ratchet(state, wt, record, verification.score, commit)
        record.next_plan = (
            "ninguno: ronda aprobada"
            if record.approved
            else "corregir: "
            + ", ".join(verification.failed + [f"{len(_blocking(verdict))} hallazgo(s)"])
        )
        fb = self._feedback(state, record, verification, verdict)
        agent_error = not checker.ok and not role_violation
        return self._close(
            record,
            started,
            feedback=fb,
            stall=record.signature,
            agent_error=agent_error,
            verification=verification,
            verdict=verdict,
        )

    def _ratchet(
        self, state: RunState, wt: Worktree, record: RoundRecord, score: int, commit: str
    ) -> None:
        """Solo avanza: si la ronda empeora, la rama vuelve a la mejor; si iguala o mejora, la
        ronda pasa a ser la nueva referencia."""
        if score < state.best_score:
            wt.reset_to(state.best_commit)
            record.reverted_to = state.best_commit
            record.decision = "revert"
            record.note = _join(
                record.note,
                f"ratchet: {score} < mejor {state.best_score} (ronda {state.best_round}); "
                f"la rama vuelve a {state.best_commit[:10]}",
            )
        else:
            record.decision = "keep"
            state.best_score, state.best_commit, state.best_round = score, commit, record.number

    def _close(
        self,
        record: RoundRecord,
        started: float,
        feedback: str = "",
        stall: str = "",
        agent_error: bool = False,
        blocked: bool = False,
        verification: Verification | None = None,
        verdict: Verdict | None = None,
    ) -> RoundOutcome:
        record.finished = now_iso()
        record.duration_s = round(time.monotonic() - started, 3)
        return RoundOutcome(record, feedback, stall, agent_error, blocked, verification, verdict)

    def _write_round(self, state: RunState, outcome: RoundOutcome) -> None:
        """Artefactos legibles de la ronda en rounds/<n>/ (spec loop-state)."""
        directory = self.store.run_dir(state.run_id) / "rounds" / str(outcome.record.number)
        files = {
            "maker.md": artifacts.render_maker(outcome.record),
            "checks.md": artifacts.render_checks(outcome.record, outcome.verification),
            "review.md": artifacts.render_review(outcome.record, outcome.verdict),
        }
        for name, text in files.items():
            atomic_write_text(directory / name, text)

    # ------------------------------------------------------------------ agentes y verificación
    def _invoke(
        self, state: RunState, number: int, role_name: str, prompt: str, wt: Worktree
    ) -> AgentResult:
        role = self.roles[role_name]
        allowed = list(role.allowed_tools)
        if role_name == "maker":
            allowed += [f"Bash({c.run})" for c in self.goal.acceptance]
        remaining = max(self.limits.max_budget_usd - state.total_cost_usd, 0.0)
        request = AgentRequest(
            role=role_name,
            prompt=prompt,
            system_prompt=self.prompts[role_name],
            cwd=wt.path,
            model=role.model,
            permission_mode=role.permission_mode,
            allowed_tools=allowed,
            denied_tools=list(role.denied_tools),
            max_budget_usd=remaining,
            timeout_s=self.limits.round_timeout_s,
            json_schema=MAKER_REPORT_SCHEMA if role_name == "maker" else CHECKER_VERDICT_SCHEMA,
        )
        result = self.runner.run(request)
        state.total_cost_usd += result.cost_usd
        self.events.agent(number, request, result)
        return result

    def _verify(self, wt: Worktree, number: int) -> Verification:
        timeout = self.config.loop.verify_timeout_min * 60
        return run_criteria(
            self.goal.acceptance,
            wt.path,
            timeout,
            on_result=lambda name, result: self.events.command(number, name, result),
        )

    # ------------------------------------------------------------------ prompts
    def _scope_text(self) -> str:
        return "\n".join(
            [
                f"Permitido: {', '.join(self.goal.allow)}",
                f"Prohibido: {', '.join(self.goal.deny)}",
                *self.protection.describe(),
                "Los archivos protegidos existentes no se pueden modificar, borrar ni renombrar; "
                "sí se pueden crear archivos nuevos.",
            ]
        )

    def _criteria_text(self) -> str:
        return "\n".join(f"- {c.name}: `{c.run}`" for c in self.goal.acceptance)

    def _maker_prompt(self, state: RunState, number: int, feedback: str) -> str:
        return "\n\n".join(
            [
                f"# Objetivo `{self.goal.id}` — ronda {number} de {self.limits.max_rounds}",
                self.goal.objective,
                "## Criterios de aceptación (los ejecuta el orquestador tras tu ronda)\n"
                + self._criteria_text(),
                "## Alcance\n" + self._scope_text(),
                "## Metodología\n" + (self.goal.body or "(sin indicaciones adicionales)"),
                "## Estado del loop\n" + build_summary(state, self.config.loop.summary_max_chars),
                "## Retroalimentación de la ronda anterior\n" + (feedback or "Primera ronda."),
                "Termina con el informe JSON (status, summary, changed_files, self_check, risks, "
                "question).",
            ]
        )

    def _checker_prompt(
        self,
        state: RunState,
        number: int,
        wt: Worktree,
        pre_commit: str,
        verification: Verification,
    ) -> str:
        cumulative = wt.diff(state.base_commit)
        round_diff = wt.diff(pre_commit)
        changed = wt.git("diff", "--name-only", f"{state.base_commit}..HEAD").splitlines()
        return "\n\n".join(
            [
                f"# Revisión de la ronda {number} del objetivo `{self.goal.id}`",
                "## Objetivo\n" + self.goal.objective,
                "## Criterios de aceptación\n" + self._criteria_text(),
                "## Alcance\n" + self._scope_text(),
                "## Resultados de la verificación determinista (ejecutada por el orquestador)\n"
                + verification.report(),
                "## Archivos cambiados en toda la ejecución\n"
                + ("\n".join(f"- {p}" for p in changed) or "(ninguno)"),
                f"## Diff acumulado desde el commit base {state.base_commit[:10]}\n"
                + _fenced(cumulative),
                "## Diff de esta ronda\n" + _fenced(round_diff),
                "Lee los archivos que necesites y responde solo con el veredicto JSON.",
            ]
        )

    def _feedback(
        self,
        state: RunState,
        record: RoundRecord,
        verification: Verification,
        verdict: Verdict | None,
    ) -> str:
        if record.approved:
            return "La ronda anterior fue aprobada: mantén el estado sin cambios innecesarios."
        parts = []
        if record.decision == "revert":
            parts.append(
                "La ronda anterior EMPEORÓ la verificación y se revirtió: la rama vuelve al "
                f"estado de la ronda {state.best_round}, la mejor registrada."
            )
        if verification.failed:
            parts.append("Criterios fallidos:\n" + verification.report())
        if verdict and verdict.findings:
            parts.append(
                "Hallazgos del checker (corrige primero los critical y medium):\n"
                + "\n".join(f.render() for f in verdict.findings)
            )
        if record.note:
            parts.append("Notas del orquestador: " + record.note)
        return "\n\n".join(parts) or "La ronda anterior no fue aprobada."

    # ------------------------------------------------------------------ cierre
    def _result_row(self, state: RunState, record: RoundRecord) -> None:
        append_result(
            self.config.state_path,
            run_id=state.run_id,
            round=record.number,
            commit=record.commit[:10],
            score=f"{record.score}/{record.total}",
            verdict=record.checker_verdict or "-",
            decision=record.decision,
            cost_usd=f"{record.cost_usd:.4f}",
            duration_s=record.duration_s,
            description=record.maker_summary or record.note,
        )

    def _finalize(self, state: RunState, wt: Worktree | None) -> None:
        if not state.is_final:
            self._stop(state, INTERRUPTED, state.stop_reason or "terminado de forma inesperada")
        if wt and state.status == COMPLETED and self.goal.feature:
            self._promote(state, wt)
        state.finished = now_iso()
        state.summary = self._summary(state)
        atomic_write_text(
            self.store.run_dir(state.run_id) / "decision.md", artifacts.render_decision(state)
        )
        files, lines, stat = (
            diffstat(self.config.root, state.base_commit, wt.branch) if wt else ([], 0, "")
        )
        self.inbox.save(run_entry(state, files, lines, stat))
        if wt:
            remove_worktree(wt)
        self.store.save(state, self.limits.max_rounds)
        self.echo(f"Resultado: {state.status} — {state.stop_reason}")

    def _promote(self, state: RunState, wt: Worktree) -> None:
        path = wt.path / self.config.harness.feature_list
        data = features.load(path)
        timeout = self.config.loop.verify_timeout_min * 60
        outcome = features.verify(
            data, self.goal.feature, cwd=wt.path, run_id=state.run_id, timeout_s=timeout
        )
        if outcome.ok:
            features.save(path, data)
            wt.snapshot(f"factory({state.run_id}): promover feature {self.goal.feature}")
            state.summary = f"feature {self.goal.feature} promovida a passing en la rama"
        else:
            warning = (
                f"AVISO: la feature {self.goal.feature} NO se promovió; falló "
                f"`{outcome.failed.command}`"
            )
            state.blockers.append(warning)
            state.stop_reason = f"{state.stop_reason} ({warning})"

    def _summary(self, state: RunState) -> str:
        approved = sum(1 for r in state.rounds if r.approved)
        promoted = f"; {state.summary}" if state.summary else ""
        return (
            f"{len(state.rounds)} ronda(s), {approved} aprobada(s), mejor ronda "
            f"{state.best_round} con {max(state.best_score, 0)}/{len(self.goal.acceptance)} "
            f"criterios; coste {state.total_cost_usd:.4f} USD{promoted}"
        )

    @staticmethod
    def _round_line(record: RoundRecord) -> str:
        return (
            f"  ronda {record.number}: {record.score}/{record.total} criterios, checker "
            f"{record.checker_verdict or '—'}, decisión {record.decision}"
            + (" ✅" if record.approved else "")
        )


def _blocking(verdict: Verdict | None) -> list:
    return verdict.blocking if verdict else []


def _join(*parts: str) -> str:
    return "; ".join(p for p in parts if p)


def _fenced(diff: str) -> str:
    if not diff.strip():
        return "(sin cambios)"
    if len(diff) > DIFF_LIMIT:
        diff = diff[:DIFF_LIMIT] + "\n… (diff truncado; lee los archivos cambiados)"
    return f"```diff\n{diff}\n```"


def exit_code(state: RunState) -> int:
    return EXIT_CODES.get(state.status, 1)
