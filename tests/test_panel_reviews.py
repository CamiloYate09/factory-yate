"""Feed de revisiones del panel: unión de inicio y fin, revisiones en curso y de los loops."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from factory.panel.hooks import LOG
from factory.panel.reviews import IN_PROGRESS, UNCLOSED, review_feed
from factory.state import RoundRecord, RunState

NOW = datetime(2026, 10, 29, 12, 0, 0, tzinfo=UTC)


def start(ts: str, tool_use_id: str = "t1", reviewer: str = "checker", **extra) -> dict:
    return {
        "ts": ts,
        "event": "PreToolUse",
        "session_id": "s1",
        "tool_use_id": tool_use_id,
        "subagent_type": reviewer,
        "description": "Revisar panel",
        "review": True,
        **extra,
    }


def stop(ts: str, tool_use_id: str = "t1", reviewer: str = "checker", **extra) -> dict:
    return {
        "ts": ts,
        "event": "SubagentStop",
        "session_id": "s1",
        "agent_id": "a1",
        "agent_type": reviewer,
        "tool_use_id": tool_use_id,
        "review": True,
        "verdict": "fail",
        "severities": {"critical": 0, "medium": 2, "minor": 1, "low": 0},
        "excerpt": "## Veredicto\n❌ fail",
        **extra,
    }


def write_log(state: Path, records: list[dict]) -> None:
    path = state / LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")


def make_run(verdict: str = "pass_with_minor") -> RunState:
    run = RunState(run_id="20261028-052249-demo-a254", goal_id="demo", objective="x", pid=1)
    run.rounds = [
        RoundRecord(
            number=1,
            started="2026-10-28T05:23:25+00:00",
            finished="2026-10-28T05:27:47+00:00",
            checker_verdict="fail",
            checker_model="claude-opus-5-5",
            findings=[{"severity": "medium", "location": "a.py:1", "description": "roto"}],
        ),
        RoundRecord(
            number=2,
            started="2026-10-28T05:27:47+00:00",
            finished="2026-10-28T05:31:32+00:00",
            checker_verdict=verdict,
            findings=[{"severity": "minor", "location": "b.py:2", "description": "nombre"}],
        ),
        RoundRecord(number=3, started="2026-10-28T05:32:00+00:00"),  # sin veredicto aún
    ]
    return run


def test_inicio_y_fin_se_unen(tmp_path: Path):
    write_log(tmp_path, [start("2026-10-29T11:00:00+00:00"), stop("2026-10-29T11:02:30+00:00")])
    (entry,) = review_feed(tmp_path, [], NOW)
    assert entry["source"] == "hook"
    assert entry["reviewer"] == "checker"
    assert entry["status"] == "fail" and entry["verdict"] == "fail"
    assert entry["duration_s"] == 150.0
    assert entry["severities"]["medium"] == 2
    assert entry["description"] == "Revisar panel"
    assert entry["final"] is None  # el registro no lo trae


def test_revision_interrumpida(tmp_path: Path):
    write_log(
        tmp_path,
        [
            start("2026-10-29T11:00:00+00:00"),
            stop("2026-10-29T11:01:00+00:00", verdict="sin_veredicto", final=False),
        ],
    )
    (entry,) = review_feed(tmp_path, [], NOW)
    assert (entry["status"], entry["final"]) == ("sin_veredicto", False)


def test_revision_en_curso(tmp_path: Path):
    write_log(tmp_path, [start("2026-10-29T11:59:00+00:00")])
    (entry,) = review_feed(tmp_path, [], NOW)
    assert entry["status"] == IN_PROGRESS
    assert entry["duration_s"] == 60.0
    assert entry["verdict"] == ""


def test_fin_adelantado_no_cierra_otra_revision_paralela(tmp_path: Path):
    write_log(
        tmp_path,
        [
            start("2026-10-29T11:00:00+00:00", tool_use_id="t2"),
            stop("2026-10-29T11:05:00+00:00", tool_use_id="t1", verdict="fail"),
            start("2026-10-29T11:01:00+00:00", tool_use_id="t1"),  # hook asíncrono tardío
        ],
    )
    by_id = {e["tool_use_id"]: e for e in review_feed(tmp_path, [], NOW)}
    assert by_id["t1"]["status"] == "fail" and by_id["t1"]["duration_s"] == 240.0
    assert by_id["t2"]["status"] == IN_PROGRESS


def test_revision_sin_cierre(tmp_path: Path):
    write_log(
        tmp_path, [start("2026-10-29T09:59:00+00:00"), start("2026-10-29T10:01:00+00:00", "t2")]
    )
    old, recent = sorted(review_feed(tmp_path, [], NOW), key=lambda e: e["started"])
    assert (old["status"], old["duration_s"]) == (UNCLOSED, None)
    assert recent["status"] == IN_PROGRESS


def test_un_fin_tardio_cierra_tambien_una_revision_antigua(tmp_path: Path):
    write_log(
        tmp_path,
        [start("2026-10-29T04:00:00+00:00"), stop("2026-10-29T11:00:00+00:00", verdict="pass")],
    )
    (entry,) = review_feed(tmp_path, [], NOW)
    assert entry["status"] == "pass"


def test_fin_sin_tool_use_id_cierra_el_ultimo_abierto_de_la_sesion(tmp_path: Path):
    write_log(
        tmp_path,
        [
            start("2026-10-29T11:00:00+00:00", tool_use_id="t1"),
            start("2026-10-29T11:01:00+00:00", tool_use_id="t2", reviewer="qa"),
            start("2026-10-29T11:02:00+00:00", tool_use_id="t3"),
            stop("2026-10-29T11:03:00+00:00", tool_use_id="", verdict="pass"),
        ],
    )
    feed = review_feed(tmp_path, [], NOW)
    by_tool = {e["tool_use_id"]: e["status"] for e in feed}
    assert by_tool == {"t1": IN_PROGRESS, "t2": IN_PROGRESS, "t3": "pass"}


def test_revisiones_paralelas_por_tool_use_id(tmp_path: Path):
    write_log(
        tmp_path,
        [
            start("2026-10-29T11:00:00+00:00", tool_use_id="t1"),
            start("2026-10-29T11:00:01+00:00", tool_use_id="t2"),
            stop("2026-10-29T11:05:00+00:00", tool_use_id="t1", verdict="pass"),
        ],
    )
    by_tool = {e["tool_use_id"]: e["status"] for e in review_feed(tmp_path, [], NOW)}
    assert by_tool == {"t1": "pass", "t2": IN_PROGRESS}


def test_fin_sin_inicio(tmp_path: Path):
    write_log(tmp_path, [stop("2026-10-29T11:00:00+00:00", tool_use_id="", verdict="")])
    (entry,) = review_feed(tmp_path, [], NOW)
    assert entry["status"] == "sin_veredicto"
    assert entry["duration_s"] is None
    assert entry["finished"] == "2026-10-29T11:00:00+00:00"


def test_inicio_que_llega_tras_el_fin(tmp_path: Path):
    write_log(
        tmp_path,
        [
            stop("2026-10-29T11:02:00+00:00", tool_use_id="t1", verdict="pass"),
            start("2026-10-29T11:00:00+00:00", tool_use_id="t1"),
        ],
    )
    (entry,) = review_feed(tmp_path, [], NOW)
    assert entry["status"] == "pass"
    assert entry["started"] == "2026-10-29T11:00:00+00:00"
    assert entry["duration_s"] == 120.0
    assert entry["description"] == "Revisar panel"


def test_eventos_que_no_son_revision_no_entran(tmp_path: Path):
    write_log(
        tmp_path,
        [start("2026-10-29T11:00:00+00:00", reviewer="Explore", review=False), "basura"],
    )
    path = tmp_path / LOG
    path.write_text(path.read_text(encoding="utf-8") + "{truncado\n", encoding="utf-8")
    assert review_feed(tmp_path, [], NOW) == []


def test_revision_de_un_loop(tmp_path: Path):
    feed = review_feed(tmp_path, [make_run()], NOW)
    assert [(e["round"], e["status"]) for e in feed] == [(2, "pass_with_minor"), (1, "fail")]
    second = feed[0]
    assert second["source"] == "loop"
    assert second["run_id"] == "20261028-052249-demo-a254"
    assert second["reviewer"] == "checker"
    assert second["severities"]["minor"] == 1
    assert "b.py:2" in second["excerpt"]
    assert feed[1]["model"] == "claude-opus-5-5"


def test_orden_y_limite(tmp_path: Path):
    write_log(
        tmp_path,
        [
            start("2026-10-29T10:00:00+00:00", tool_use_id="old"),
            stop("2026-10-29T10:01:00+00:00", tool_use_id="old", verdict="pass"),
            start("2026-10-29T11:30:00+00:00", tool_use_id="live"),
        ],
    )
    feed = review_feed(tmp_path, [make_run()], NOW)
    assert [e["tool_use_id"] or e["round"] for e in feed] == ["live", "old", 2, 1]
    assert len(review_feed(tmp_path, [make_run()], NOW, limit=2)) == 2


def test_sin_registro(tmp_path: Path):
    assert review_feed(tmp_path / "no-existe", [], NOW) == []
