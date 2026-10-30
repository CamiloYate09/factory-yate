"""Consumo de tokens del panel: loops (`events.jsonl`) y transcripciones de Claude Code."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from factory.panel import main_root
from factory.panel.tokens import (
    TranscriptReader,
    loop_usage,
    projects_dir,
    session_usage,
    slug,
    transcript_files,
)

SECRET = "SECRETO-123"


def agent_event(role: str, model: str, cost: float, inp: int, out: int, turns: int = 3) -> dict:
    return {
        "ts": "2026-10-28T04:04:41+00:00",
        "type": "agent",
        "round": 1,
        "role": role,
        "model": model,
        "cost_usd": cost,
        "input_tokens": inp,
        "output_tokens": out,
        "num_turns": turns,
        "output": {"summary": f"texto del agente {SECRET}"},
    }


def write_events(state: Path, run_id: str, lines: list[str]) -> Path:
    path = state / "runs" / run_id / "events.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return path


def assistant_row(
    msg_id: str,
    out: int = 10,
    model: str = "claude-opus-5-5",
    ts: str = "2026-10-29T11:15:46.932Z",
    session: str = "s1",
    inp: int = 2,
    cache_write: int = 100,
    cache_read: int = 1000,
    text: str = "hola",
) -> dict:
    return {
        "type": "assistant",
        "timestamp": ts,
        "sessionId": session,
        "isSidechain": False,
        "requestId": f"req-{msg_id}",
        "uuid": f"uuid-{msg_id}-{out}-{text}",
        "message": {
            "id": msg_id,
            "model": model,
            "role": "assistant",
            "content": [{"type": "text", "text": text}],
            "usage": {
                "input_tokens": inp,
                "cache_creation_input_tokens": cache_write,
                "cache_read_input_tokens": cache_read,
                "output_tokens": out,
            },
        },
    }


def write_rows(path: Path, rows: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    return path


@pytest.fixture
def layout(tmp_path: Path) -> tuple[Path, Path]:
    """Repo (sin crear) y directorio de proyectos de Claude Code en un temporal."""
    root = tmp_path / "work" / "mi-repo"
    root.mkdir(parents=True)
    projects = tmp_path / "claude" / "projects"
    projects.mkdir(parents=True)
    return root, projects


# --- Loops -------------------------------------------------------------------------------


def test_ejecucion_con_maker_y_checker(tmp_path: Path):
    state = tmp_path / ".factory"
    write_events(
        state,
        "20261028-040428-demo-90b9",
        [
            json.dumps({"type": "command", "name": "lint", "exit_code": 0}),
            json.dumps(agent_event("maker", "claude-sonnet-5-5", 0.13, 88340, 860, 4)),
            json.dumps(agent_event("checker", "claude-opus-5-5", 0.31, 88456, 2289, 6)),
        ],
    )
    loops = loop_usage(state)
    (run,) = loops["runs"]
    assert run["run_id"] == "20261028-040428-demo-90b9"
    assert run["cost_usd"] == pytest.approx(0.44)
    assert run["calls"] == 2
    assert run["input"] == 88340 + 88456
    assert run["turns"] == 10
    assert {r["role"]: r["cost_usd"] for r in run["by_role"]} == {"maker": 0.13, "checker": 0.31}
    assert {r["model"] for r in run["by_model"]} == {"claude-sonnet-5-5", "claude-opus-5-5"}
    assert loops["total"]["cost_usd"] == pytest.approx(0.44)
    assert loops["by_day"] == [{"day": "2026-10-28", **{k: run[k] for k in loops["total"]}}]


def test_linea_corrupta(tmp_path: Path):
    state = tmp_path / ".factory"
    good = json.dumps(agent_event("maker", "claude-sonnet-5-5", 0.1, 100, 10))
    write_events(state, "r1", [good, good[: len(good) // 2], good, "[1, 2]", ""])
    run = loop_usage(state)["runs"][0]
    assert run["calls"] == 2
    assert run["cost_usd"] == pytest.approx(0.2)


def test_evento_agent_sin_campos_de_consumo_se_ignora(tmp_path: Path):
    state = tmp_path / ".factory"
    write_events(
        state,
        "r1",
        [
            json.dumps({"type": "agent", "role": "maker", "cost_usd": True}),
            json.dumps({"type": "agent", "cost_usd": 1.0}),  # sin rol
            json.dumps(agent_event("checker", "claude-opus-5-5", 0.5, 10, 1)),
        ],
    )
    loops = loop_usage(state)
    assert loops["total"]["calls"] == 1
    assert loops["total"]["cost_usd"] == pytest.approx(0.5)


def test_sin_estado_no_hay_ejecuciones(tmp_path: Path):
    loops = loop_usage(tmp_path / ".factory")
    assert loops["runs"] == [] and loops["total"]["calls"] == 0


def test_raiz_principal_desde_un_worktree(git_repo: Path, tmp_path: Path):
    worktree = tmp_path / "wt"
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "rama", str(worktree)], cwd=git_repo, check=True
    )
    (worktree / "sub").mkdir()
    assert main_root(worktree / "sub") == git_repo.resolve()
    assert main_root(git_repo) == git_repo.resolve()


def test_raiz_sin_git_es_la_propia(tmp_path: Path):
    (tmp_path / "factory.toml").write_text("", encoding="utf-8")
    assert main_root(tmp_path) == tmp_path.resolve()


# --- Descubrimiento de transcripciones ---------------------------------------------------


def test_slug_como_claude_code():
    assert slug(Path("/Users/yo/PycharmProjects/factory-yate")) == (
        "-Users-yo-PycharmProjects-factory-yate"
    )
    assert slug(Path("/a/b/.claude/worktrees/agent-x")) == "-a-b--claude-worktrees-agent-x"


def test_directorio_de_proyectos(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    assert projects_dir() == tmp_path / "cfg" / "projects"
    assert projects_dir(tmp_path / "otro") == tmp_path / "otro"
    monkeypatch.delenv("CLAUDE_CONFIG_DIR")
    assert projects_dir() == Path.home() / ".claude" / "projects"


def test_sesion_en_un_worktree_del_equipo(layout):
    root, projects = layout
    write_rows(projects / slug(root) / "s1.jsonl", [assistant_row("m1", out=5)])
    team = slug(root / ".claude" / "worktrees" / "agent-x")
    write_rows(projects / team / "s2.jsonl", [assistant_row("m2", out=7, session="s2")])
    usage = session_usage(projects, root)
    assert usage["total"]["output"] == 12
    assert {s["project"] for s in usage["sessions"]} == {"principal", "agent-x"}


def test_worktree_de_un_loop(layout):
    root, projects = layout
    loop_wt = root.parent / f"{root.name}.factory-worktrees" / "20261028-run"
    write_rows(projects / slug(loop_wt) / "s9.jsonl", [assistant_row("m9", out=999)])
    other = root.parent / f"{root.name}-otro"  # otro repo con el mismo prefijo
    write_rows(projects / slug(other) / "s8.jsonl", [assistant_row("m8", out=888)])
    write_rows(projects / slug(root) / "s1.jsonl", [assistant_row("m1", out=1)])
    usage = session_usage(projects, root)
    assert usage["total"]["output"] == 1
    assert [t.project for t in transcript_files(projects, root)] == ["principal"]


def test_mensaje_repetido_por_bloques(layout):
    root, projects = layout
    rows = [assistant_row("msg_1", out=234, text=t) for t in ("pensar", "texto", "herramienta")]
    write_rows(projects / slug(root) / "s1.jsonl", rows)
    usage = session_usage(projects, root)
    assert usage["total"]["output"] == 234
    assert usage["total"]["messages"] == 1


def test_sin_id_de_mensaje_usa_el_de_la_peticion(layout):
    root, projects = layout
    rows = [assistant_row("x", out=3), assistant_row("x", out=3)]
    for row in rows:
        del row["message"]["id"]
    write_rows(projects / slug(root) / "s1.jsonl", rows)
    assert session_usage(projects, root)["total"]["output"] == 3


def test_filas_sin_usage_o_sinteticas_se_ignoran(layout):
    root, projects = layout
    synthetic = assistant_row("syn", out=50, model="<synthetic>")
    no_usage = assistant_row("nu", out=60)
    del no_usage["message"]["usage"]
    user = {"type": "user", "message": {"role": "user", "content": "hola", "usage": {}}}
    write_rows(projects / slug(root) / "s1.jsonl", [synthetic, no_usage, user])
    with (projects / slug(root) / "s1.jsonl").open("a") as handle:
        handle.write('{"type": "assistant", "message": {"usage": tru\n')
    assert session_usage(projects, root)["total"]["messages"] == 0


def test_desglose_por_dia_modelo_y_cache(layout):
    root, projects = layout
    write_rows(
        projects / slug(root) / "s1.jsonl",
        [
            assistant_row("a", out=10, ts="2026-10-28T23:59:00Z", inp=0, cache_write=0),
            assistant_row("b", out=20, ts="2026-10-29T00:01:00Z", model="claude-haiku-5-5"),
        ],
    )
    usage = session_usage(projects, root)
    assert [d["day"] for d in usage["by_day"]] == ["2026-10-28", "2026-10-29"]
    assert {m["model"] for m in usage["by_model"]} == {"claude-opus-5-5", "claude-haiku-5-5"}
    entering = 0 + 0 + 1000 + 2 + 100 + 1000
    assert usage["cache_ratio"] == round(2000 / entering, 4)
    (session,) = usage["sessions"]
    assert session["first"] == "2026-10-28T23:59:00Z"
    assert session["last"] == "2026-10-29T00:01:00Z"


def test_subagente_checker(layout):
    root, projects = layout
    project = projects / slug(root)
    write_rows(project / "s1.jsonl", [assistant_row("main", out=100)])
    sub = project / "s1" / "subagents"
    write_rows(sub / "agent-abc.jsonl", [assistant_row("sub1", out=40)])
    (sub / "agent-abc.meta.json").write_text(
        json.dumps({"agentType": "checker", "description": "Revisar panel", "toolUseId": "t1"}),
        encoding="utf-8",
    )
    write_rows(sub / "agent-def.jsonl", [assistant_row("sub2", out=5)])  # sin meta.json
    usage = session_usage(projects, root)
    agents = {a["agent"]: a["output"] for a in usage["by_agent"]}
    assert agents == {"principal": 100, "checker": 40, "subagente": 5}
    (session,) = usage["sessions"]
    assert session["session"] == "s1"
    assert [(s["agent"], s["description"]) for s in session["subagents"]] == [
        ("checker", "Revisar panel"),
        ("subagente", ""),
    ]


def test_sesion_interactiva_sin_usd(layout):
    root, projects = layout
    write_rows(projects / slug(root) / "s1.jsonl", [assistant_row("m1")])
    text = json.dumps(session_usage(projects, root))
    assert "cost" not in text and "usd" not in text.lower()


def test_mensaje_con_un_secreto(layout, tmp_path: Path):
    root, projects = layout
    project = projects / slug(root)
    tool_use = assistant_row("m1", text=SECRET)
    tool_use["message"]["content"].append(
        {"type": "tool_use", "name": "Bash", "input": {"command": f"echo {SECRET}"}}
    )
    result = {
        "type": "user",
        "message": {"role": "user", "content": [{"type": "tool_result", "content": SECRET}]},
        "toolUseResult": {"stdout": SECRET},
    }
    write_rows(project / "s1.jsonl", [tool_use, result])
    write_rows(project / "s1" / "subagents" / "agent-z.jsonl", [assistant_row("m2", text=SECRET)])
    state = tmp_path / ".factory"
    write_events(state, "r1", [json.dumps(agent_event("maker", "m", 0.1, 1, 1))])
    output = json.dumps([session_usage(projects, root), loop_usage(state)])
    assert SECRET not in output


def test_sin_directorio_de_proyectos(tmp_path: Path):
    usage = session_usage(tmp_path / "no-existe", tmp_path)
    assert usage["transcripts"] == 0 and usage["sessions"] == []


# --- Caché incremental -------------------------------------------------------------------


class CountingReader(TranscriptReader):
    """Cuenta las líneas que llega a decodificar."""

    def __init__(self) -> None:
        super().__init__()
        self.parsed = 0

    def _parse(self, line, rows):  # type: ignore[override]
        self.parsed += 1
        super()._parse(line, rows)


def test_archivo_que_crece_lee_solo_lo_nuevo(layout):
    root, projects = layout
    path = write_rows(projects / slug(root) / "s1.jsonl", [assistant_row("a", out=1)])
    reader = CountingReader()
    assert session_usage(projects, root, reader)["total"]["output"] == 1
    assert reader.parsed == 1
    write_rows(path, [assistant_row("b", out=2), assistant_row("c", out=4)])
    assert session_usage(projects, root, reader)["total"]["output"] == 7
    assert reader.parsed == 3  # solo las dos filas nuevas
    assert session_usage(projects, root, reader)["total"]["output"] == 7
    assert reader.parsed == 3


def test_linea_a_medias_se_lee_cuando_se_completa(layout):
    root, projects = layout
    path = projects / slug(root) / "s1.jsonl"
    line = json.dumps(assistant_row("a", out=8))
    path.parent.mkdir(parents=True)
    path.write_text(line[:30], encoding="utf-8")
    reader = TranscriptReader()
    assert session_usage(projects, root, reader)["total"]["output"] == 0
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line[30:] + "\n")
    assert session_usage(projects, root, reader)["total"]["output"] == 8


def test_archivo_truncado_se_relee_sin_contar_de_mas(layout):
    root, projects = layout
    path = write_rows(
        projects / slug(root) / "s1.jsonl", [assistant_row("a", out=1), assistant_row("b", out=2)]
    )
    reader = TranscriptReader()
    assert session_usage(projects, root, reader)["total"]["output"] == 3
    path.write_text(json.dumps(assistant_row("c", out=5)) + "\n", encoding="utf-8")
    assert session_usage(projects, root, reader)["total"]["output"] == 5


def test_archivo_borrado_deja_de_contar(layout):
    root, projects = layout
    path = write_rows(projects / slug(root) / "s1.jsonl", [assistant_row("a", out=1)])
    reader = TranscriptReader()
    assert session_usage(projects, root, reader)["total"]["output"] == 1
    path.unlink()
    assert session_usage(projects, root, reader)["total"]["output"] == 0
