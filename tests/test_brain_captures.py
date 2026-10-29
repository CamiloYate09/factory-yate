"""Escenarios de `daily-brain`: capturas propuestas desde los loops y su revisión."""

from conftest import make_loop_repo, write_goal

from factory.agents.fake import FakeRunner, FakeStep, finding, maker_done, verdict
from factory.brain.captures import CaptureStore, Injected, redact
from factory.brain.importer import import_vault
from factory.config import load_config
from factory.engine import LoopEngine
from factory.goal import load_goal

MEDIUM = finding(
    "medium", "src/a.py:3", description="Falta validar la entrada vacía", evidence="a('')"
)


def _run(root, runner, **kwargs):
    config = load_config(root)
    goal = load_goal(write_goal(root, **kwargs), config.loop)
    return config, LoopEngine(config, goal, runner, echo=lambda _: None).run()


def test_hallazgo_corregido(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(
        maker=[maker_done("a", **{"a.txt": "1"}), maker_done("arreglado", **{"a.txt": "2"})],
        checker=[verdict("fail", MEDIUM), verdict("pass")],
    )
    config, state = _run(root, runner)
    assert state.status == "completed"
    [capture] = CaptureStore(config.state_path).pending()
    assert capture.kind == "gotcha" and capture.source == f"run:{state.run_id}"
    assert "Falta validar la entrada vacía" in capture.text and "a('')" in capture.text
    assert "ronda 1" in capture.text and "ronda aprobada (2)" in capture.text
    assert not (root / "brain-diario").exists()  # el cerebro diario no cambió


def test_ejecucion_sin_nada_que_capturar(tmp_path):
    root = make_loop_repo(tmp_path)
    config, state = _run(root, FakeRunner(maker=[maker_done("a", **{"a.txt": "1"})]))
    assert state.status == "completed" and CaptureStore(config.state_path).pending() == []


def test_captura_de_retrabajo(tmp_path):
    root = make_loop_repo(tmp_path)
    ask = FakeStep(
        output={"status": "needs_human", "summary": "?", "question": "¿SQLite o Postgres?"}
    )
    config, parent = _run(root, FakeRunner(maker=[ask]))
    goal = load_goal(write_goal(root), config.loop)
    child = LoopEngine(
        config,
        goal,
        FakeRunner(maker=[maker_done("a", **{"a.txt": "1"})]),
        echo=lambda _: None,
        parent=parent,
        answer="SQLite: es una herramienta local",
    ).run()
    decisions = [c for c in CaptureStore(config.state_path).pending() if c.kind == "decision"]
    [capture] = decisions
    assert (
        "¿SQLite o Postgres?" in capture.text and "SQLite: es una herramienta local" in capture.text
    )
    assert capture.source == f"run:{child.run_id}"


def test_captura_de_estancamiento(tmp_path):
    root = make_loop_repo(tmp_path)
    config, state = _run(root, FakeRunner(maker=[maker_done("nada")]), max_rounds=5, no_progress=2)
    assert state.status == "stalled"
    [capture] = CaptureStore(config.state_path).pending()
    assert capture.title == "Estancamiento en demo" and "a.txt" in capture.text


def _run_with_vault(tmp_path, vault, copied_text, toml=""):
    """Ejecución con el vault importado y un hallazgo del checker que copia texto de un libro."""
    root = make_loop_repo(tmp_path)
    if toml:
        (root / "factory.toml").write_text(toml)
    import_vault(vault, root / "brain-principal", root)
    copied = finding("medium", "src/rl.py:1", description=f"El código ignora que {copied_text}")
    runner = FakeRunner(
        maker=[maker_done("a", **{"a.txt": "1"}), maker_done("b", **{"a.txt": "2"})],
        checker=[verdict("fail", copied), verdict("pass")],
    )
    config, _ = _run(root, runner, extra='knowledge:\n  queries: ["token bucket"]\n')
    [capture] = CaptureStore(config.state_path).pending()
    return capture


def test_ejecucion_con_conocimiento_inyectado(tmp_path, vault):
    libro = "A token bucket refills at a fixed rate. Each request consumes one token."
    capture = _run_with_vault(tmp_path, vault, libro)
    assert "refills at a fixed rate" not in capture.text
    assert "[texto de referencia omitido: ver Securing APIs · cap. 3 · pp. 41–44]" in capture.text
    assert "fixed rate" not in capture.title


def test_resumen_de_una_nota_solo_citada(tmp_path, vault):
    """Con presupuesto mínimo la nota solo se cita, pero su resumen también es texto del libro."""
    resumen = "Rate limiting with a token bucket protects APIs from abuse and spikes."
    capture = _run_with_vault(tmp_path, vault, resumen, toml="[brain]\ninject_max_tokens = 1\n")
    assert "protects APIs from abuse" not in capture.text
    assert "[texto de referencia omitido: ver Securing APIs · cap. 3 · pp. 41–44]" in capture.text


def test_redact_conserva_frases_cortas_y_texto_propio():
    injected = [Injected("Libro", "one two three four five six seven eight nine ten")]
    assert redact("one two three cuatro", injected) == "one two three cuatro"
    out = redact("Inicio one two three four five six seven eight fin", injected)
    assert out == "Inicio [texto de referencia omitido: ver Libro] fin"


def _with_capture(tmp_path):
    root = make_loop_repo(tmp_path)
    runner = FakeRunner(
        maker=[maker_done("a", **{"a.txt": "1"}), maker_done("b", **{"a.txt": "2"})],
        checker=[verdict("fail", MEDIUM), verdict("pass")],
    )
    config, state = _run(root, runner)
    [capture] = CaptureStore(config.state_path).pending()
    return root, config, state, capture


def test_aceptar_una_captura(tmp_path, capsys):
    import json

    from factory.cli import main

    root, config, state, capture = _with_capture(tmp_path)
    assert main(["--root", str(root), "status"]) == 0
    assert "1 captura(s) pendiente(s)" in capsys.readouterr().out
    assert main(["--root", str(root), "brain", "pending"]) == 0
    assert capture.id in capsys.readouterr().out
    assert main(["--root", str(root), "brain", "accept", capture.id]) == 0
    [entry] = [
        json.loads(line)
        for line in (root / "brain-diario" / "_catalog.jsonl").read_text().splitlines()
    ]
    assert entry["source"] == f"run:{state.run_id}" and entry["type"] == "gotcha"
    assert CaptureStore(config.state_path).pending() == []


def test_rechazar_una_captura(tmp_path, capsys):
    from factory.cli import main

    root, config, _, capture = _with_capture(tmp_path)
    assert main(["--root", str(root), "brain", "reject", capture.id]) == 0
    assert CaptureStore(config.state_path).pending() == []
    assert not (root / "brain-diario").exists()
    rejected = config.state_path / "brain" / "rejected" / f"{capture.id}.md"
    assert rejected.exists() and "rejected_at" in rejected.read_text()
    assert main(["--root", str(root), "brain", "accept", capture.id]) == 2
