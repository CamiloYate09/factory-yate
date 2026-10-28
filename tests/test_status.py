"""Escenarios de `loop-state`: indicadores de costes silenciosos en `factory status`."""

from factory.cli import main
from factory.inbox import Inbox, InboxEntry
from factory.state import RoundRecord, RunState, RunStore


def _toml(root, text):
    (root / "factory.toml").write_text(text, encoding="utf-8")


def test_bandeja_acumulada_avisa_con_numero_y_mas_antigua(tmp_path, capsys):
    _toml(tmp_path, "[alerts]\ninbox_pending_max = 2\n")
    inbox = Inbox(tmp_path / ".factory")
    for i, created in enumerate(["2026-10-01T00:00:00+00:00", "2026-10-20T00:00:00+00:00"] * 2):
        inbox.save(InboxEntry(id=f"run-{i}", goal_id="g", created=created, lines_changed=10))
    assert main(["--root", str(tmp_path), "status"]) == 0
    out = capsys.readouterr().out
    assert "[AVISO] Rendición cognitiva: 4 entrada(s) pendiente(s); la más antigua: run-0" in out
    assert "[OK] Deterioro de la comprensión: 40 líneas" in out


def test_crecimiento_de_tokens(tmp_path, capsys):
    store = RunStore(tmp_path / ".factory")
    state = RunState(run_id="r-tokens", goal_id="g", objective="o", status="max_rounds")
    for n, tokens in enumerate([1000, 1500, 2600], 1):
        state.rounds.append(RoundRecord(number=n, started="x", maker_input_tokens=tokens))
    store.create(state, "g")
    assert main(["--root", str(tmp_path), "status"]) == 0
    out = capsys.readouterr().out
    assert "[AVISO] Explosión de tokens: 1 ejecución(es)" in out
    assert "r-tokens (1000 → 2600 tokens de entrada)" in out


def test_sin_avisos_y_listado(tmp_path, capsys):
    store = RunStore(tmp_path / ".factory")
    store.create(
        RunState(
            run_id="r-ok",
            goal_id="g",
            objective="o",
            status="completed",
            criteria_total=3,
            branch="factory/r-ok",
        ),
        "g",
    )
    assert main(["--root", str(tmp_path), "status"]) == 0
    out = capsys.readouterr().out
    assert "r-ok  completed" in out and "rama=factory/r-ok" in out
    assert "[OK] Deuda de verificación: 100% de los criterios verificados por máquina" in out
    assert "AVISO" not in out


def test_deuda_de_verificacion_y_comprension(tmp_path, capsys):
    _toml(tmp_path, "[alerts]\npending_lines_max = 50\n")
    store = RunStore(tmp_path / ".factory")
    store.create(
        RunState(run_id="r", goal_id="g", objective="o", criteria_total=2, manual_checks=2), "g"
    )
    Inbox(tmp_path / ".factory").save(InboxEntry(id="r", goal_id="g", lines_changed=120))
    main(["--root", str(tmp_path), "status"])
    out = capsys.readouterr().out
    assert "[AVISO] Deuda de verificación: 50%" in out
    assert "[AVISO] Deterioro de la comprensión: 120 líneas" in out


def test_ejecucion_huerfana(tmp_path, capsys):
    store = RunStore(tmp_path / ".factory")
    store.create(RunState(run_id="r-dead", goal_id="g", objective="o", pid=999999), "g")
    main(["--root", str(tmp_path), "status"])
    assert "Huérfanas" in capsys.readouterr().out
