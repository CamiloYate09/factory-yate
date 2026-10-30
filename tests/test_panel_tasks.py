"""Estado de implementación del panel e instantánea (`factory panel --json`)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from conftest import make_feature, write_features

from factory.cli import main
from factory.inbox import Inbox, InboxEntry
from factory.panel import snapshot
from factory.panel.tasks import collect, parse_tasks
from factory.panel.tokens import slug
from factory.state import RUNNING, RoundRecord, RunState, RunStore

TASKS_MD = """# Tasks

> Nota: - [x] esto no es una tarea

## 1. Preparación

- [x] 1.1 Crear el cambio.
- [ x] 1.2 Añadir features.

## 2. Plantilla y convocatoria (`team-roster`)

- [x] 2.1 Implementar `src/factory/team/`.
- [ ] 2.2 Implementar `factory team list`.
  - [x] subviñeta que no cuenta
- [~] 2.3 Convocatoria a medias.
- [] 2.4 Doctor.

## 3. Complejidad (`no-existe`, `complexity-metrics`)

- [ ] 3.1 Medir.

## Workflow follow-up

- [ ] Archivar el cambio.
"""


def make_change(root: Path, name: str, text: str = TASKS_MD, archived: bool = False) -> Path:
    base = root / "openspec" / "changes"
    directory = base / "archive" / name if archived else base / name
    directory.mkdir(parents=True)
    (directory / "tasks.md").write_text(text, encoding="utf-8")
    return directory


def dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def save_run(state: Path, run_id: str, **values) -> RunState:
    run = RunState(run_id=run_id, goal_id="demo", objective="x", **values)
    RunStore(state).save(run)
    return run


def test_parse_tasks():
    groups = parse_tasks(TASKS_MD)
    assert [(g["number"], g["done"], g["total"]) for g in groups] == [
        (1, 2, 2),
        (2, 1, 4),
        (3, 0, 1),
    ]
    assert groups[1]["ids"] == ["team-roster"]
    assert groups[1]["tasks"][0] == {
        "id": "2.1",
        "text": "Implementar `src/factory/team/`.",
        "done": True,
    }


def test_grupo_enlazado(tmp_path: Path):
    write_features(
        tmp_path,
        make_feature("team-roster", priority=16),
        make_feature("complexity-metrics", priority=17),
    )
    make_change(tmp_path, "add-equipo-ideal")
    tasks = collect(tmp_path, tmp_path / ".factory", [], [])
    roster, metrics = tasks["features"]
    (group,) = roster["groups"]
    assert group["change"] == "add-equipo-ideal"
    assert (group["number"], group["done"], group["total"]) == (2, 1, 4)
    assert [g["number"] for g in metrics["groups"]] == [3]  # primer id que es una feature
    (change,) = tasks["changes"]
    assert (change["done"], change["total"]) == (3, 7)
    assert [g["feature"] for g in change["groups"]] == [None, "team-roster", "complexity-metrics"]


def test_cambio_archivado_no_aparece(tmp_path: Path):
    make_change(tmp_path, "add-viejo", archived=True)
    make_change(tmp_path, "add-activo")
    assert [c["name"] for c in collect(tmp_path, tmp_path, [], [])["changes"]] == ["add-activo"]


def test_features_con_evidencia_y_wip(tmp_path: Path):
    evidence = [
        {"command": "pytest a", "exit_code": 1, "date": "2026-10-28", "commit": "aaa"},
        {"command": "pytest a", "exit_code": 0, "date": "2026-10-29", "commit": "bbb"},
    ]
    write_features(
        tmp_path,
        make_feature("b", "passing", priority=2, evidence=evidence, verification=["pytest a"]),
        make_feature("a", "in_progress", priority=1),
    )
    tasks = collect(tmp_path, tmp_path / ".factory", [], [])
    assert [f["id"] for f in tasks["features"]] == ["a", "b"]
    assert tasks["in_progress"] == ["a"]
    assert tasks["status_counts"] == {"in_progress": 1, "passing": 1}
    assert tasks["features"][1]["evidence"] == [evidence[1]]


def test_ejecucion_huerfana(tmp_path: Path):
    state = tmp_path / ".factory"
    orphan = save_run(state, "20261029-100000-demo-aaaa", pid=dead_pid(), status=RUNNING)
    live = save_run(state, "20261029-110000-demo-bbbb", status=RUNNING, feature="a")
    live.rounds = [
        RoundRecord(number=1, started="x", score=2, checker_verdict="fail"),
        RoundRecord(number=2, started="y", score=3),
    ]
    live.criteria_total = 3
    live.total_cost_usd = 1.23456
    RunStore(state).save(live)
    write_features(tmp_path, make_feature("a"))
    runs = RunStore(state).list_runs()
    tasks = collect(tmp_path, state, runs, [])
    rows = {r["run_id"]: r for r in tasks["runs"]}
    assert rows[orphan.run_id]["alive"] is False
    current = rows[live.run_id]
    assert current["alive"] is True  # el pid por defecto es el de este proceso
    assert (current["round"], current["score"], current["criteria_total"]) == (2, 3, 3)
    assert current["verdict"] == "fail"
    assert current["cost_usd"] == 1.2346
    assert tasks["features"][0]["runs"] == [live.run_id]


def test_bandeja_pendiente_y_mal_formada(tmp_path: Path):
    state = tmp_path / ".factory"
    Inbox(state).save(InboxEntry(id="r1", goal_id="g", result="completed", created="2026-10-29"))
    assert collect(tmp_path, state, [], [])["inbox"] == {"pending": 1, "ids": ["r1"]}
    (state / "inbox" / "roto.md").write_text("sin frontmatter", encoding="utf-8")
    warnings: list[str] = []
    assert collect(tmp_path, state, [], warnings)["inbox"]["pending"] == 0
    assert any("bandeja" in w for w in warnings)


# --- Instantánea -------------------------------------------------------------------------


def test_repo_sin_ejecuciones(tmp_path: Path):
    snap = snapshot.build(tmp_path, tmp_path / "projects")
    assert set(snap) >= {"generated", "repo", "tokens", "reviews", "tasks", "warnings"}
    assert snap["reviews"] == []
    assert snap["tasks"]["features"] == [] and snap["tasks"]["runs"] == []
    assert snap["tokens"]["loops"]["runs"] == [] and snap["tokens"]["sessions"]["sessions"] == []
    assert snap["warnings"] == []
    json.loads(snapshot.to_json(snap))


def test_lista_de_features_corrupta(tmp_path: Path):
    (tmp_path / "feature_list.json").write_text("{ no es json", encoding="utf-8")
    make_change(tmp_path, "add-x")
    snap = snapshot.build(tmp_path, tmp_path / "projects")
    assert any("feature_list.json" in w for w in snap["warnings"])
    assert snap["tasks"]["features"] == []
    assert snap["tasks"]["changes"][0]["name"] == "add-x"


def test_archivos_ilegibles_avisan(tmp_path: Path):
    state = tmp_path / ".factory"
    (state / "hooks" / "events.jsonl").mkdir(parents=True)  # existe, pero no se puede leer
    (state / "runs" / "r1" / "events.jsonl").mkdir(parents=True)
    projects = tmp_path / "projects"
    (projects / slug(tmp_path) / "s1.jsonl").mkdir(parents=True)
    snap = snapshot.build(tmp_path, projects)
    for name in ("hooks/events.jsonl", "r1/events.jsonl", "s1.jsonl"):
        assert any(name in w and "no se pudo leer" in w for w in snap["warnings"]), name
    assert snap["reviews"] == []


def test_state_json_corrupto_avisa_y_no_tumba_las_demas(tmp_path: Path):
    save_run(tmp_path / ".factory", "20261029-100000-demo-aaaa", pid=dead_pid())
    broken = tmp_path / ".factory" / "runs" / "20261029-110000-demo-bbbb"
    broken.mkdir(parents=True)
    (broken / "state.json").write_text("{ roto", encoding="utf-8")
    snap = snapshot.build(tmp_path, tmp_path / "projects")
    assert any("demo-bbbb/state.json" in w for w in snap["warnings"])
    assert [r["run_id"] for r in snap["tasks"]["runs"]] == ["20261029-100000-demo-aaaa"]


def test_factory_toml_invalido_usa_el_estado_por_defecto(tmp_path: Path):
    (tmp_path / "factory.toml").write_text("[[[ roto", encoding="utf-8")
    save_run(tmp_path / ".factory", "20261029-100000-demo-aaaa", pid=dead_pid())
    snap = snapshot.build(tmp_path, tmp_path / "projects")
    assert any("factory.toml" in w for w in snap["warnings"])
    assert len(snap["tasks"]["runs"]) == 1


def test_una_seccion_que_falla_no_tumba_las_demas(tmp_path: Path, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("explota")

    monkeypatch.setattr("factory.panel.reviews.review_feed", boom)
    write_features(tmp_path, make_feature("a"))
    snap = snapshot.build(tmp_path, tmp_path / "projects")
    assert snap["reviews"] == []
    assert any("reviews" in w and "explota" in w for w in snap["warnings"])
    assert snap["tasks"]["features"][0]["id"] == "a"


def test_instantanea_sin_efectos(tmp_path: Path):
    write_features(tmp_path, make_feature("a"))
    make_change(tmp_path, "add-x")
    save_run(tmp_path / ".factory", "20261029-100000-demo-aaaa", pid=dead_pid())
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in tmp_path.rglob("*") if p.is_file()}
    snapshot.build(tmp_path, tmp_path / "projects")
    after = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in tmp_path.rglob("*") if p.is_file()}
    assert before == after
    assert {"feature_list.json", "openspec", ".factory"} <= {p.name for p in tmp_path.iterdir()}


def panel_json(root: Path, capsys) -> tuple[int, dict]:
    argv = ["--root", str(root), "panel", "--json", "--projects-dir", str(root / "projects")]
    code = main(argv)
    return code, json.loads(capsys.readouterr().out)


def test_cli_json_en_un_repo_sin_factory(tmp_path: Path, capsys):
    code, snap = panel_json(tmp_path, capsys)
    assert code == 0
    assert {"tokens", "reviews", "tasks", "warnings"} <= set(snap)
    assert snap["reviews"] == [] and snap["tasks"]["runs"] == []
    assert not (tmp_path / ".factory").exists()


def test_cli_json_con_features_corruptas(tmp_path: Path, capsys):
    (tmp_path / "feature_list.json").write_text("{ no es json", encoding="utf-8")
    code, snap = panel_json(tmp_path, capsys)
    assert code == 0
    assert any("feature_list.json" in w for w in snap["warnings"])
