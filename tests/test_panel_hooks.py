"""`factory hook`: registro de lanzamientos y fines de subagentes, veredictos y seguridad."""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from factory.cli import main
from factory.panel.hooks import (
    EXCERPT_MAX,
    LOG,
    NO_VERDICT,
    run,
    severities_of,
    verdict_of,
)

SECRET = "PROMPT-SECRETO-42"
REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / ".claude" / "hooks" / "panel-hook.sh"

CHECKER_FAIL = """## Veredicto
❌ fail

## Hallazgos

### 1. [medium] El hook bloquea con código 2
- Ubicación: src/factory/panel/hooks.py:10
- Descripción: …

## Verificación recibida
- ./scripts/check.sh → 0
"""

PLAYER_MINOR = """## Jugador: qa (#2)

## Veredicto
⚠️ pass_with_minor

## Hallazgos

### 1. [minor] Falta un caso límite
### 2. [Minor] Nombre poco claro
"""


def hook(payload: dict | str, capsys=None) -> tuple[int, str]:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    stderr = io.StringIO()
    code = run(io.StringIO(raw), stderr)
    if capsys is not None:
        assert capsys.readouterr().out == ""
    return code, stderr.getvalue()


def log_lines(root: Path) -> list[dict]:
    path = root / ".factory" / LOG
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def pre_tool_use(cwd: Path, subagent: str | None = "checker", **extra) -> dict:
    tool_input = {"description": "Revisar panel", "prompt": f"Revisa esto {SECRET}"}
    if subagent is not None:
        tool_input["subagent_type"] = subagent
    return {
        "session_id": "sess-1",
        "transcript_path": str(cwd / "sess-1.jsonl"),
        "cwd": str(cwd),
        "permission_mode": "default",
        "hook_event_name": "PreToolUse",
        "tool_name": "Agent",
        "tool_input": tool_input,
        "tool_use_id": "toolu_01",
        **extra,
    }


def write_subagent(
    projects: Path,
    text: str,
    agent_type: str | None = "checker",
    agent_id: str = "a1",
    interrupted: bool = False,
    handback: str | None = None,
) -> Path:
    """Transcripción de un subagente en `<proyecto>/sess-1/subagents/` con su meta.json."""
    sub = projects / "sess-1" / "subagents"
    sub.mkdir(parents=True, exist_ok=True)
    rows = [
        {"type": "user", "message": {"role": "user", "content": f"prompt {SECRET}"}},
        {
            "type": "assistant",
            "message": {"id": "m1", "content": [{"type": "text", "text": "Leyendo…"}]},
        },
        {"type": "assistant", "message": {"id": "m2", "content": [{"type": "thinking"}]}},
        {"type": "assistant", "message": {"id": "m2", "content": [{"type": "text", "text": text}]}},
        {"type": "system", "subtype": "turn_duration"},
    ]
    if interrupted:  # como en la captura real: acaba en un tool_result, sin respuesta final
        rows += [
            {"type": "assistant", "message": {"id": "m3", "content": [{"type": "tool_use"}]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "x"}]}},
        ]
    if handback is not None:  # como en la captura real: entrega la respuesta con una herramienta
        tool_use = {"type": "tool_use", "name": "SubagentHandback", "input": {"message": handback}}
        rows += [
            {"type": "assistant", "message": {"id": "m4", "content": [tool_use]}},
            {"type": "user", "message": {"content": [{"type": "tool_result", "content": "ok"}]}},
        ]
    path = sub / f"agent-{agent_id}.jsonl"
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    if agent_type is not None:
        meta = {"agentType": agent_type, "description": "Revisar panel", "toolUseId": "toolu_01"}
        (sub / f"agent-{agent_id}.meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return path


def subagent_stop(cwd: Path, projects: Path, agent_id: str = "a1", **extra) -> dict:
    return {
        "session_id": "sess-1",
        "transcript_path": str(projects / "sess-1.jsonl"),
        "cwd": str(cwd),
        "permission_mode": "default",
        "hook_event_name": "SubagentStop",
        "stop_hook_active": False,
        "agent_id": agent_id,
        **extra,
    }


def write_agent(root: Path, name: str, tipo: str | None) -> None:
    agents = root / ".claude" / "agents"
    agents.mkdir(parents=True, exist_ok=True)
    extra = f"tipo: {tipo}\ndorsal: 2\n" if tipo else ""
    (agents / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: x\ntools: Read\n{extra}---\n\nCuerpo.\n",
        encoding="utf-8",
    )


# --- Registro ----------------------------------------------------------------------------


def test_lanzamiento_del_checker(git_repo: Path, capsys):
    code, _ = hook(pre_tool_use(git_repo), capsys)
    assert code == 0
    (line,) = log_lines(git_repo)
    assert line["event"] == "PreToolUse"
    assert line["subagent_type"] == "checker"
    assert line["description"] == "Revisar panel"
    assert line["tool_use_id"] == "toolu_01"
    assert line["session_id"] == "sess-1"
    assert line["review"] is True
    assert line["ts"]


@pytest.mark.parametrize("valid", [True, False])
def test_subcomando_factory_hook(git_repo: Path, valid: bool, capsys, monkeypatch):
    monkeypatch.chdir(git_repo)
    raw = json.dumps(pre_tool_use(git_repo)) if valid else "no es json"
    monkeypatch.setattr(sys, "stdin", io.StringIO(raw))
    assert main(["hook"]) == 0
    out = capsys.readouterr()
    assert out.out == ""
    assert len(log_lines(git_repo)) == (1 if valid else 0)
    assert valid or "factory hook" in out.err


def test_el_prompt_no_se_registra(git_repo: Path):
    hook(pre_tool_use(git_repo))
    assert SECRET not in (git_repo / ".factory" / LOG).read_text(encoding="utf-8")


def test_subagente_que_no_revisa(git_repo: Path):
    hook(pre_tool_use(git_repo, subagent="Explore"))
    hook(pre_tool_use(git_repo, subagent=None))  # sin tipo: general-purpose
    lines = log_lines(git_repo)
    assert [(x["subagent_type"], x["review"]) for x in lines] == [
        ("Explore", False),
        ("general-purpose", False),
    ]


def test_otras_herramientas_y_eventos_no_se_registran(git_repo: Path, capsys):
    other_tool = {**pre_tool_use(git_repo), "tool_name": "Bash"}
    other_event = {**pre_tool_use(git_repo), "hook_event_name": "Stop"}
    assert hook(other_tool, capsys)[0] == 0
    assert hook(other_event, capsys)[0] == 0
    assert log_lines(git_repo) == []


def test_hook_desde_un_worktree(git_repo: Path, tmp_path: Path):
    worktree = tmp_path / "wt"
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "rama", str(worktree)], cwd=git_repo, check=True
    )
    hook(pre_tool_use(worktree))
    assert len(log_lines(git_repo)) == 1
    assert not (worktree / ".factory").exists()


def test_directorio_de_estado_configurado(git_repo: Path):
    (git_repo / "factory.toml").write_text('[loop]\nstate_dir = ".estado"\n', encoding="utf-8")
    hook(pre_tool_use(git_repo))
    assert (git_repo / ".estado" / LOG).exists()


@pytest.mark.parametrize("raw", ["no es json", "", "   ", "[1, 2]", '"texto"'])
def test_entrada_invalida(git_repo: Path, raw: str, capsys, monkeypatch):
    monkeypatch.chdir(git_repo)
    code, err = hook(raw, capsys)
    assert code == 0
    assert "factory hook" in err
    assert log_lines(git_repo) == []


def test_registro_no_escribible(git_repo: Path, capsys):
    (git_repo / ".factory").write_text("soy un archivo", encoding="utf-8")
    code, err = hook(pre_tool_use(git_repo), capsys)
    assert code == 0
    assert "factory hook" in err


def test_campos_raros_no_rompen(git_repo: Path, capsys):
    payload = pre_tool_use(git_repo)
    payload["tool_input"] = "no es un dict"
    payload["session_id"] = 42
    code, _ = hook(payload, capsys)
    assert code == 0
    (line,) = log_lines(git_repo)
    assert line["session_id"] == "" and line["subagent_type"] == "general-purpose"


def test_cwd_inexistente_usa_el_directorio_actual(git_repo: Path, monkeypatch):
    monkeypatch.chdir(git_repo)
    hook(pre_tool_use(git_repo / "no-existe"))
    assert len(log_lines(git_repo)) == 1


def test_ocho_procesos_concurrentes_sin_lineas_mezcladas(git_repo: Path, tmp_path: Path):
    projects = tmp_path / "projects"
    for index in range(8):
        write_subagent(projects, CHECKER_FAIL + "x" * 3500, agent_id=f"a{index}")
    procs = [
        subprocess.Popen(
            [sys.executable, "-m", "factory.panel.hooks"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=git_repo,
        )
        for _ in range(8)
    ]
    for index, proc in enumerate(procs):
        payload = json.dumps(subagent_stop(git_repo, projects, agent_id=f"a{index}"))
        out, _ = proc.communicate(payload.encode(), timeout=60)
        assert proc.returncode == 0 and out == b""
    lines = log_lines(git_repo)
    assert sorted(x["agent_id"] for x in lines) == [f"a{i}" for i in range(8)]
    assert all(len(x["excerpt"]) > 3500 for x in lines)


# --- Veredicto y revisores ---------------------------------------------------------------


def test_checker_con_un_hallazgo_medio(git_repo: Path, tmp_path: Path):
    projects = tmp_path / "projects"
    write_subagent(projects, CHECKER_FAIL)
    hook(subagent_stop(git_repo, projects))
    (line,) = log_lines(git_repo)
    assert line["event"] == "SubagentStop"
    assert line["agent_type"] == "checker"
    assert line["tool_use_id"] == "toolu_01"
    assert line["review"] is True
    assert line["verdict"] == "fail"
    assert line["severities"] == {"critical": 0, "medium": 1, "minor": 0, "low": 0}
    assert line["excerpt"].startswith("## Veredicto")
    assert line["final"] is True
    assert SECRET not in json.dumps(line)


def test_revisor_interrumpido(git_repo: Path, tmp_path: Path):
    projects = tmp_path / "projects"
    write_subagent(projects, "Ahora reviso roles.md y los tests.", interrupted=True)
    hook(subagent_stop(git_repo, projects))
    (line,) = log_lines(git_repo)
    assert (line["verdict"], line["final"]) == (NO_VERDICT, False)
    assert line["excerpt"] == "Ahora reviso roles.md y los tests."


def test_respuesta_entregada_con_handback(git_repo: Path, tmp_path: Path):
    projects = tmp_path / "projects"
    write_subagent(projects, "Ahora reviso los tests.", interrupted=True, handback=CHECKER_FAIL)
    hook(subagent_stop(git_repo, projects))
    (line,) = log_lines(git_repo)
    assert (line["verdict"], line["final"]) == ("fail", True)
    assert line["severities"]["medium"] == 1
    assert line["excerpt"].startswith("## Veredicto")


def test_ultimo_mensaje_del_payload_si_la_transcripcion_no_acabo(git_repo: Path, tmp_path: Path):
    projects = tmp_path / "projects"
    write_subagent(projects, "Ahora reviso los tests.", interrupted=True)
    hook(subagent_stop(git_repo, projects, last_assistant_message=PLAYER_MINOR))
    (line,) = log_lines(git_repo)
    assert (line["verdict"], line["final"]) == ("pass_with_minor", True)


def test_ultimo_mensaje_del_payload_no_pisa_la_respuesta_final(git_repo: Path, tmp_path: Path):
    projects = tmp_path / "projects"
    write_subagent(projects, CHECKER_FAIL)
    hook(subagent_stop(git_repo, projects, last_assistant_message="Leyendo…"))
    (line,) = log_lines(git_repo)
    assert line["verdict"] == "fail"


def test_nombres_de_campos_sin_valores(git_repo: Path):
    hook(pre_tool_use(git_repo, extra_field="VALOR-OCULTO"))
    (line,) = log_lines(git_repo)
    assert "extra_field" in line["payload_keys"] and "tool_input" in line["payload_keys"]
    assert "VALOR-OCULTO" not in json.dumps(line)


def test_respuesta_sin_veredicto(git_repo: Path, tmp_path: Path):
    projects = tmp_path / "projects"
    write_subagent(projects, "He leído el diff y no tengo nada que decir.")
    hook(subagent_stop(git_repo, projects))
    (line,) = log_lines(git_repo)
    assert line["verdict"] == NO_VERDICT
    assert line["severities"] == {"critical": 0, "medium": 0, "minor": 0, "low": 0}


def test_formato_de_jugador_revisor(git_repo: Path, tmp_path: Path):
    write_agent(git_repo, "qa", "revisor")
    projects = tmp_path / "projects"
    write_subagent(projects, PLAYER_MINOR, agent_type="qa")
    hook(subagent_stop(git_repo, projects))
    (line,) = log_lines(git_repo)
    assert line["review"] is True
    assert line["verdict"] == "pass_with_minor"
    assert line["severities"]["minor"] == 2


def test_agente_del_payload_y_ruta_directa(git_repo: Path, tmp_path: Path):
    write_agent(git_repo, "qa", "revisor")
    projects = tmp_path / "projects"
    path = write_subagent(projects, PLAYER_MINOR, agent_type=None, agent_id="zz")
    elsewhere = tmp_path / "otra" / "agent-zz.jsonl"
    elsewhere.parent.mkdir()
    path.rename(elsewhere)
    payload = subagent_stop(
        git_repo, projects, agent_id="zz", agent_type="qa", agent_transcript_path=str(elsewhere)
    )
    hook(payload)
    (line,) = log_lines(git_repo)
    assert (line["agent_type"], line["verdict"]) == ("qa", "pass_with_minor")


def test_constructor_no_cuenta_como_revision(git_repo: Path, tmp_path: Path):
    write_agent(git_repo, "documentador", "constructor")
    write_agent(git_repo, "ajeno", None)
    projects = tmp_path / "projects"
    write_subagent(projects, CHECKER_FAIL, agent_type="documentador", agent_id="d1")
    hook(subagent_stop(git_repo, projects, agent_id="d1"))
    hook(pre_tool_use(git_repo, subagent="ajeno"))
    stop, start = log_lines(git_repo)
    assert stop["review"] is False and stop["verdict"] == "" and stop["excerpt"] == ""
    assert start["review"] is False


def test_jugador_de_un_worktree(git_repo: Path, tmp_path: Path):
    worktree = tmp_path / "wt"
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "rama", str(worktree)], cwd=git_repo, check=True
    )
    write_agent(worktree, "seguridad", "revisor")  # solo existe en el worktree
    hook(pre_tool_use(worktree, subagent="seguridad"))
    (line,) = log_lines(git_repo)
    assert line["review"] is True


def test_tipo_con_ruta_no_se_resuelve(git_repo: Path, tmp_path: Path):
    write_agent(tmp_path, "evil", "revisor")
    hook(pre_tool_use(git_repo, subagent="../../../" + tmp_path.name + "/evil"))
    (line,) = log_lines(git_repo)
    assert line["review"] is False


def test_agent_id_con_ruta_no_se_lee(git_repo: Path, tmp_path: Path):
    projects = tmp_path / "projects"
    write_subagent(projects, CHECKER_FAIL)
    # Con el tipo en el payload el fin se registra, pero la ruta inyectada no se lee.
    hook(subagent_stop(git_repo, projects, agent_id="../a1", agent_type="checker"))
    (line,) = log_lines(git_repo)
    assert line["verdict"] == NO_VERDICT and line["excerpt"] == ""


def test_extracto_recortado(git_repo: Path, tmp_path: Path):
    projects = tmp_path / "projects"
    write_subagent(projects, CHECKER_FAIL + "y" * 10_000)
    hook(subagent_stop(git_repo, projects))
    (line,) = log_lines(git_repo)
    assert len(line["excerpt"]) == EXCERPT_MAX
    assert line["verdict"] == "fail"


def test_fin_sin_tipo_no_se_registra(git_repo: Path, tmp_path: Path):
    # Sin agent_type ni meta.json (agentes internos, como los hooks de tipo prompt, que en
    # la captura real terminaban cada ~30 s): no es una revisión y solo haría ruido.
    code, _ = hook(subagent_stop(git_repo, tmp_path / "nada"))
    assert code == 0
    assert log_lines(git_repo) == []


def test_transcripcion_ausente_con_tipo(git_repo: Path, tmp_path: Path):
    hook(subagent_stop(git_repo, tmp_path / "nada", agent_type="checker"))
    (line,) = log_lines(git_repo)
    assert (line["agent_type"], line["review"], line["verdict"]) == ("checker", True, NO_VERDICT)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("## Veredicto\n✅ pass\n", "pass"),
        ("## Veredicto\n\n⚠️ pass_with_minor\n", "pass_with_minor"),
        ("**Veredicto:** fail", "fail"),
        ("Veredicto: PASS", "pass"),
        ("## Veredicto\n\n## Hallazgos\npass", NO_VERDICT),
        ("Todo passing, nada failed", NO_VERDICT),
        ('{"verdict": "pass_with_minor", "findings": []}', "pass_with_minor"),
        ("## Veredicto\nfail (antes era pass)\n", "fail"),
        ("## Veredicto\n⚠️ pass_with_minor (no es fail)\n", "pass_with_minor"),
    ],
)
def test_extraccion_del_veredicto(text: str, expected: str):
    assert verdict_of(text) == expected


def test_severidades_en_titulos_y_vinetas():
    text = (
        "### 1. [critical] a\n- [medium] b\n2. [low] c\n"
        "Texto suelto con [minor] que no es un hallazgo\n### 3. [Medium] d"
    )
    assert severities_of(text) == {"critical": 1, "medium": 2, "minor": 0, "low": 1}


def test_severidades_solo_de_la_seccion_hallazgos():
    text = (
        "## Veredicto\nfail\n\n## Hallazgos\n\n### 1. [medium] nuevo\n- detalle [minor] citado\n"
        "## Estado de los hallazgos de la primera revisión\n- 1. [critical] viejo: cerrado\n"
        "- 2. [medium] viejo: cerrado\n"
    )
    assert severities_of(text) == {"critical": 0, "medium": 1, "minor": 1, "low": 0}


# --- Script y configuración de Claude Code -----------------------------------------------


def run_script(project_dir: Path, payload: str) -> subprocess.CompletedProcess:
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
        "CLAUDE_PROJECT_DIR": str(project_dir),
    }
    return subprocess.run(
        ["bash", str(SCRIPT)], input=payload, capture_output=True, text=True, env=env, timeout=30
    )


def fake_python(root: Path) -> Path:
    """`.venv/bin/python` falso: guarda sus argumentos y su stdin junto al repo."""
    python = root / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text(
        '#!/bin/sh\necho "$@" > "$(dirname "$0")/../../args.txt"\n'
        'cat > "$(dirname "$0")/../../stdin.txt"\necho "esto no debe salir"\n',
        encoding="utf-8",
    )
    python.chmod(0o755)
    return python


def test_worktree_sin_entorno_virtual(git_repo: Path, tmp_path: Path):
    worktree = tmp_path / "wt"
    subprocess.run(
        ["git", "worktree", "add", "-q", "-b", "rama", str(worktree)], cwd=git_repo, check=True
    )
    proc = run_script(worktree, json.dumps(pre_tool_use(worktree)))
    assert proc.returncode == 0 and proc.stdout == ""
    fake_python(git_repo)
    payload = json.dumps(pre_tool_use(worktree))
    proc = run_script(worktree, payload)
    assert proc.returncode == 0
    assert proc.stdout == ""  # la salida del módulo nunca llega a Claude Code
    assert (git_repo / "stdin.txt").read_text(encoding="utf-8") == payload
    assert (git_repo / "args.txt").read_text(encoding="utf-8").split() == [
        "-m",
        "factory.panel.hooks",
    ]


def test_script_fuera_de_git(tmp_path: Path):
    proc = run_script(tmp_path, "{}")
    assert proc.returncode == 0 and proc.stdout == ""


def test_script_con_el_entorno_real(git_repo: Path):
    (git_repo / ".venv").symlink_to(sys.prefix)
    proc = run_script(git_repo, json.dumps(pre_tool_use(git_repo)))
    assert proc.returncode == 0 and proc.stdout == ""
    (line,) = log_lines(git_repo)
    assert line["subagent_type"] == "checker"


def test_settings_registra_el_hook():
    settings = json.loads((REPO / ".claude" / "settings.json").read_text(encoding="utf-8"))
    hooks = settings["hooks"]
    (pre,) = [h for h in hooks["PreToolUse"] if h.get("matcher") == "Agent|Task"]
    stop_hooks = [h for entry in hooks["SubagentStop"] for h in entry["hooks"]]
    for hook_def in [*pre["hooks"], *stop_hooks]:
        assert hook_def["type"] == "command"
        assert ".claude/hooks/panel-hook.sh" in hook_def["command"]
        assert hook_def["timeout"] <= 10
    assert SCRIPT.stat().st_mode & 0o111
