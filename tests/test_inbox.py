"""Escenarios de `loop-state`: bandeja de revisión humana."""

from factory.cli import main
from factory.inbox import Inbox, run_entry
from factory.state import RoundRecord, RunState


def _blocked_state():
    state = RunState(
        run_id="20261027-100000-demo-ab12",
        goal_id="demo",
        objective="Añadir validación",
        status="blocked",
        stop_reason="el maker necesita una decisión humana",
        branch="factory/20261027-100000-demo-ab12",
        base_commit="0123456789abcdef",
        question="¿Validamos en el cliente o en el servidor?",
        total_cost_usd=0.42,
    )
    state.rounds.append(
        RoundRecord(
            number=1,
            started="x",
            maker_summary="Añadí el esqueleto de validación",
            findings=[{"severity": "medium", "location": "src/a.py:3", "description": "sin test"}],
        )
    )
    return state


def test_ejecucion_bloqueada_crea_entrada_pendiente_con_pregunta(tmp_path, capsys):
    inbox = Inbox(tmp_path / ".factory")
    entry = run_entry(_blocked_state(), ["src/a.py"], 12, " src/a.py | 12 ++++")
    inbox.save(entry)
    [pending] = inbox.pending()
    assert pending.status == "pending" and pending.result == "blocked"
    assert pending.question == "¿Validamos en el cliente o en el servidor?"
    assert pending.branch == "factory/20261027-100000-demo-ab12"
    for text in ("¿Validamos en el cliente", "src/a.py | 12", "Añadí el esqueleto", "[medium]"):
        assert text in pending.body
    assert main(["--root", str(tmp_path), "inbox", "list"]) == 0
    out = capsys.readouterr().out
    assert "20261027-100000-demo-ab12" in out and "pregunta: ¿Validamos" in out


def test_marcar_como_revisada(tmp_path, capsys):
    inbox = Inbox(tmp_path / ".factory")
    inbox.save(run_entry(_blocked_state(), [], 0))
    assert main(["--root", str(tmp_path), "inbox", "ack", "20261027-100000-demo-ab12"]) == 0
    assert inbox.pending() == []
    [entry] = inbox.entries()
    assert entry.status == "reviewed" and entry.reviewed_at
    capsys.readouterr()
    assert main(["--root", str(tmp_path), "inbox", "list"]) == 0
    assert "No hay entradas pendientes" in capsys.readouterr().out


def test_ack_inexistente(tmp_path, capsys):
    assert main(["--root", str(tmp_path), "inbox", "ack", "nada"]) == 2
    assert "No hay ninguna entrada" in capsys.readouterr().err


def test_pending_for_goal(tmp_path):
    inbox = Inbox(tmp_path / ".factory")
    inbox.save(run_entry(_blocked_state(), [], 0))
    assert len(inbox.pending_for("demo")) == 1
    assert inbox.pending_for("otro") == []
