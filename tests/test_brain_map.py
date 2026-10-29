"""Escenarios de `library-map`: mapa versionado de la biblioteca, sin texto de los libros."""

import json
import subprocess

import pytest
from conftest import VAULT_NOTES, make_loop_repo, make_vault, write_goal

from factory.agents.fake import FakeRunner, FakeStep, maker_done
from factory.brain import BrainError
from factory.brain.daily import commit_daily
from factory.brain.libmap import BOOK_FIELDS, MAX_HEADING_WORDS, NOTE_FIELDS, build_map
from factory.brain.search import principal_from_map
from factory.cli import main
from factory.config import ConfigError, load_config
from factory.doctor import audit
from factory.engine import LoopEngine
from factory.goal import load_goal
from factory.inbox import Inbox
from factory.state import RunStore

QUERIES = 'knowledge:\n  queries: ["rate limiting"]\n'


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _map_text(map_dir):
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(map_dir.iterdir()))


def _clone_with_map(tmp_path, vault):
    """Repo de loop con el mapa commiteado y SIN cerebro principal (un clon en otro equipo)."""
    root = make_loop_repo(tmp_path)
    build_map(vault, root / "brain-mapa")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "mapa")
    return root


def _check(config, check_id):
    return next(c for c in audit(config).checks if c.id == check_id)


def test_importacion_con_mapa(tmp_path, vault, capsys):
    root = tmp_path / "repo"
    root.mkdir()
    assert main(["--root", str(root), "brain", "import", str(vault)]) == 0
    out = capsys.readouterr().out
    map_dir = root / "brain-mapa"
    assert f"Mapa de la biblioteca en {map_dir}: 5 notas, 2 libros" in out
    lines = (map_dir / "_catalog.jsonl").read_text().splitlines()
    assert len(lines) == 5
    assert len(json.loads((map_dir / "_books.json").read_text())) == 2
    assert (map_dir / "AGENTS.md").is_file()


def test_reimportacion_sin_cambios(tmp_path, vault, capsys):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    main(["--root", str(root), "brain", "import", str(vault)])
    before = {p.name: p.read_bytes() for p in (root / "brain-mapa").iterdir()}
    _git(root, "add", "-A")
    _git(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "mapa")
    capsys.readouterr()
    assert main(["--root", str(root), "brain", "import", str(vault)]) == 0
    assert "sin cambios" in capsys.readouterr().out
    assert {p.name: p.read_bytes() for p in (root / "brain-mapa").iterdir()} == before
    assert _git(root, "status", "--porcelain", "--", "brain-mapa").stdout == ""


def test_catalogo_con_resumenes(tmp_path, vault):
    map_dir = tmp_path / "brain-mapa"
    build_map(vault, map_dir)
    for line in (map_dir / "_catalog.jsonl").read_text().splitlines():
        assert "abstract" not in json.loads(line)
    text = _map_text(map_dir)
    for note in VAULT_NOTES:  # ninguna frase de resúmenes ni cuerpos de los libros
        assert note["abstract"] not in text
        assert note["body"] not in text
        assert note["body"].split(".")[0] not in text
    assert not [p for p in map_dir.rglob("*.md") if p.name != "AGENTS.md"]
    books = json.loads((map_dir / "_books.json").read_text())
    assert all(list(book) == list(BOOK_FIELDS) for book in books)  # sin `subtitle`


def test_encabezado_sospechoso(tmp_path):
    vault = make_vault(tmp_path / "vault")
    catalog = vault / "_catalog.jsonl"
    rows = [json.loads(line) for line in catalog.read_text().splitlines()]
    long_heading = " ".join(f"palabra{i}" for i in range(40))
    rows[0]["section_path"] = [long_heading]
    rows[0]["title"] = long_heading
    catalog.write_text("".join(json.dumps(r) + "\n" for r in rows))
    build_map(vault, tmp_path / "brain-mapa")
    first = next(
        json.loads(line)
        for line in (tmp_path / "brain-mapa" / "_catalog.jsonl").read_text().splitlines()
        if json.loads(line)["path"] == rows[0]["path"]
    )
    assert first["title"].split() == long_heading.split()[:MAX_HEADING_WORDS]
    assert first["section_path"][0].split() == long_heading.split()[:MAX_HEADING_WORDS]


def test_resumen_anadido_a_mano(tmp_path, vault):
    root = _clone_with_map(tmp_path, vault)
    catalog = root / "brain-mapa" / "_catalog.jsonl"
    rows = [json.loads(line) for line in catalog.read_text().splitlines()]
    rows[1]["abstract"] = "Texto copiado de un libro."
    catalog.write_text("".join(json.dumps(r) + "\n" for r in rows))
    check = _check(load_config(root), "brain-map-sin-texto")
    assert check.severity == "critical" and not check.passed
    assert "línea 2" in check.detail and "abstract" in check.detail


def test_mapa_valido(tmp_path, vault):
    root = _clone_with_map(tmp_path, vault)
    assert _check(load_config(root), "brain-map-sin-texto").passed


def test_nota_md_forzada_en_el_indice_falla(tmp_path, vault):
    root = _clone_with_map(tmp_path, vault)
    (root / "brain-mapa" / "capitulo.md").write_text("Texto de un libro.")
    _git(root, "add", "-f", "brain-mapa/capitulo.md")  # saltándose el .gitignore del mapa
    check = _check(load_config(root), "brain-map-sin-texto")
    assert not check.passed and "capitulo.md" in check.detail


def test_archivos_del_sistema_no_cuentan_ni_se_commitean(tmp_path, vault, capsys):
    root = _clone_with_map(tmp_path, vault)
    (root / "brain-mapa" / ".DS_Store").write_bytes(b"x")  # Finder y Obsidian los crean solos
    (root / "brain-mapa" / ".obsidian").mkdir()
    (root / "brain-mapa" / ".obsidian" / "workspace.json").write_text("{}")
    (root / "brain-mapa" / "notas-sueltas.md").write_text("algo")
    assert _check(load_config(root), "brain-map-sin-texto").passed
    assert _git(root, "status", "--porcelain", "--", "brain-mapa").stdout == ""


def test_clon_nuevo_sin_libros(tmp_path, vault, capsys):
    root = _clone_with_map(tmp_path, vault)
    assert main(["--root", str(root), "brain", "search", "rate limiting"]) == 0
    out = capsys.readouterr().out
    assert "resultados del mapa de la biblioteca" in out and "factory brain import" in out
    assert "Securing APIs · cap. 3 · pp. 41–44 — Token bucket rate limiting" in out


def test_inyeccion_solo_con_el_mapa(tmp_path, vault):
    root = _clone_with_map(tmp_path, vault)
    config = load_config(root)
    goal = load_goal(write_goal(root, extra=QUERIES), config.loop)
    runner = FakeRunner(maker=[maker_done("creé a", **{"a.txt": "1"})])
    state = LoopEngine(config, goal, runner, echo=lambda _: None).run()
    prompt = runner.calls_for("maker")[0].prompt
    assert "Securing APIs · cap. 3" in prompt
    assert "texto no disponible en este equipo" in prompt
    for note in VAULT_NOTES:  # ningún texto completo de ningún libro
        assert note["body"] not in prompt
    assert state.status == "completed"


def test_principal_y_mapa_presentes(tmp_path, vault, capsys):
    root = _clone_with_map(tmp_path, vault)
    main(["--root", str(root), "brain", "import", str(vault)])
    capsys.readouterr()
    assert main(["--root", str(root), "brain", "search", "rate limiting", "--json"]) == 0
    hits = json.loads(capsys.readouterr().out)
    paths = [h["path"] for h in hits if h["brain"] == "principal"]
    assert paths and len(paths) == len(set(paths))  # una sola vez cada nota
    config = load_config(root)
    assert not principal_from_map(config)  # el catálogo usado es el del principal
    goal = load_goal(write_goal(root, extra=QUERIES), config.loop)
    runner = FakeRunner(maker=[maker_done("creé a", **{"a.txt": "1"})])
    LoopEngine(config, goal, runner, echo=lambda _: None).run()
    prompt = runner.calls_for("maker")[0].prompt
    assert "A token bucket refills at a fixed rate." in prompt  # con su texto disponible
    assert "texto no disponible en este equipo" not in prompt


def test_el_maker_edita_el_mapa(tmp_path, vault):
    root = _clone_with_map(tmp_path, vault)
    config = load_config(root)
    goal = load_goal(write_goal(root, max_rounds=2), config.loop)
    runner = FakeRunner(
        maker=[
            maker_done("toqué el mapa", **{"a.txt": "1", "brain-mapa/_catalog.jsonl": "{}\n"}),
            maker_done("ahora bien", **{"a.txt": "1"}),
        ]
    )
    state = LoopEngine(config, goal, runner, echo=lambda _: None).run()
    assert state.rounds[0].decision == "scope_revert"
    assert "brain-mapa/_catalog.jsonl" in runner.calls_for("maker")[1].prompt
    request = runner.calls_for("maker")[0]
    absolute = config.map_path.as_posix().lstrip("/")
    assert f"Edit(//{absolute}/**)" in request.denied_tools
    assert f"Write(//{absolute}/**)" in request.denied_tools
    assert state.status == "completed"


def test_el_mapa_se_construye_y_no_se_copia(tmp_path):
    """Campos desconocidos del vault (como los reales `source` y `readme`) nunca pasan."""
    vault = make_vault(tmp_path / "vault")
    catalog = vault / "_catalog.jsonl"
    rows = [json.loads(line) for line in catalog.read_text().splitlines()]
    for row in rows:
        row.update({"source": "x.pdf", "body": "Texto del libro.", "foo": 1, "readme": "r.md"})
    catalog.write_text("".join(json.dumps(r) + "\n" for r in rows))
    books_file = vault / "_books.json"
    books = json.loads(books_file.read_text())
    for book in books:
        book.update({"source": "x.pdf", "readme": "r.md", "subtitle": "Copyright © Editorial"})
    books_file.write_text(json.dumps(books))
    map_dir = tmp_path / "brain-mapa"
    build_map(vault, map_dir)
    for line in (map_dir / "_catalog.jsonl").read_text().splitlines():
        assert list(json.loads(line)) == list(NOTE_FIELDS)
    for book in json.loads((map_dir / "_books.json").read_text()):
        assert list(book) == list(BOOK_FIELDS)
    text = _map_text(map_dir)
    for leaked in ("Texto del libro", "x.pdf", "Copyright", "Guía del vault", "# Biblioteca"):
        assert leaked not in text  # ni campos sueltos ni las guías del vault


@pytest.mark.parametrize(
    ("target", "tamper", "expected"),
    [
        ("_catalog.jsonl", "keyword", "valor fuera de formato en ['keywords']"),
        ("_books.json", "author", "valor fuera de formato en ['authors']"),
        ("llms.txt", "append", "llms.txt: contenido distinto"),
        ("AGENTS.md", "append", "AGENTS.md: contenido distinto"),
    ],
)
def test_texto_pegado_en_un_valor_permitido(tmp_path, vault, capsys, target, tamper, expected):
    root = _clone_with_map(tmp_path, vault)
    path = root / "brain-mapa" / target
    sentence = "The primary way to protect against the overuse of API resources is rate limiting."
    if tamper == "keyword":
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]["keywords"].append(sentence)
        path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    elif tamper == "author":
        books = json.loads(path.read_text())
        books[0]["authors"].append(sentence + " " + sentence)
        path.write_text(json.dumps(books, ensure_ascii=False, indent=2) + "\n")
    else:
        path.write_text(path.read_text() + "\n" + sentence + "\n")
    check = _check(load_config(root), "brain-map-sin-texto")
    assert not check.passed and expected in check.detail
    assert main(["--root", str(root), "doctor"]) != 0
    assert expected in capsys.readouterr().out  # visible en la salida, no solo en --json


def test_busqueda_json_en_un_clon_sin_libros(tmp_path, vault, capsys):
    root = _clone_with_map(tmp_path, vault)
    assert main(["--root", str(root), "brain", "search", "rate limiting", "--json"]) == 0
    captured = capsys.readouterr()
    hits = json.loads(captured.out)  # stdout solo con el JSON
    assert hits and hits[0]["citation"].startswith("Securing APIs")
    assert "mapa de la biblioteca" in captured.err


def test_mapa_ignorado_por_git(tmp_path, vault, capsys):
    root = make_loop_repo(tmp_path)
    (root / ".gitignore").write_text(".factory/\nbrain-mapa/\n")
    _git(root, "commit", "-qam", "ignorar el mapa")
    assert main(["--root", str(root), "brain", "import", str(vault)]) == 0
    assert "está en .gitignore" in capsys.readouterr().out
    config = load_config(root)
    assert not _check(config, "brain-map-versionable").passed
    main(["--root", str(root), "brain", "learn", "Una ficha propia"])
    assert main(["--root", str(root), "brain", "commit", "-m", "fichas"]) == 0  # no se bloquea
    files = _git(root, "show", "--name-only", "--format=", "HEAD").stdout.split()
    assert files and all(f.startswith("brain-diario/") for f in files)


def test_cambio_en_el_mapa_durante_una_ejecucion(tmp_path, vault):
    root = _clone_with_map(tmp_path, vault)
    config = load_config(root)
    catalog = config.map_path / "_catalog.jsonl"

    def tamper(_request):
        catalog.write_text(catalog.read_text() + "\n")

    step = FakeStep(output={"status": "done", "summary": "x"}, edits={"a.txt": "1"}, action=tamper)
    goal = load_goal(write_goal(root), config.loop)
    state = LoopEngine(config, goal, FakeRunner(maker=[step]), echo=lambda _: None).run()
    [warning] = [b for b in state.blockers if "integridad" in b]
    assert "cerebro mapa" in warning and "factory brain import" in warning
    run_dir = RunStore(config.state_path).run_dir(state.run_id)
    assert "cerebro mapa" in (run_dir / "decision.md").read_text()
    [entry] = Inbox(config.state_path).pending()
    assert "cerebro mapa" in entry.body


def test_paginas_con_tipos_raros(tmp_path):
    vault = make_vault(tmp_path / "vault")
    catalog = vault / "_catalog.jsonl"
    rows = [json.loads(line) for line in catalog.read_text().splitlines()]
    rows[0]["pages"], rows[1]["pages"], rows[2]["section_path"] = 41, "41-44", "Rate limiting"
    catalog.write_text("".join(json.dumps(r) + "\n" for r in rows))
    build_map(vault, tmp_path / "brain-mapa")  # sin traceback
    lines = [
        json.loads(x) for x in (tmp_path / "brain-mapa" / "_catalog.jsonl").read_text().splitlines()
    ]
    by_path = {line["path"]: line for line in lines}
    assert by_path[rows[0]["path"]]["pages"] == [] and by_path[rows[1]["path"]]["pages"] == []
    assert by_path[rows[2]["path"]]["section_path"] == []


@pytest.mark.parametrize(
    "toml",
    [
        '[brain]\nmap_dir = "."\n',
        '[brain]\nmap_dir = "brain-diario"\n',
        '[brain]\nmap_dir = "brain-principal/mapa"\n',
    ],
)
def test_rutas_de_cerebros_que_se_solapan(tmp_path, toml):
    (tmp_path / "factory.toml").write_text(toml)
    with pytest.raises(ConfigError, match="brain"):
        load_config(tmp_path)


def test_clave_repetida_escondiendo_texto(tmp_path, vault):
    """JSON se queda con el último valor: doctor compara el texto, no el objeto."""
    root = _clone_with_map(tmp_path, vault)
    catalog = root / "brain-mapa" / "_catalog.jsonl"
    lines = catalog.read_text().splitlines()
    first = json.loads(lines[0])
    hidden = json.dumps(first, ensure_ascii=False)[:-1]
    lines[0] = (
        '{"title": "A token bucket refills at a fixed rate. Each request consumes one.", '
        + hidden[1:]
        + "}"
    )
    assert json.loads(lines[0]) == first  # al interpretarlo, el párrafo desaparece
    catalog.write_text("\n".join(lines) + "\n")
    check = _check(load_config(root), "brain-map-sin-texto")
    assert not check.passed and "línea 1: texto distinto" in check.detail


@pytest.mark.parametrize(
    "tamper",
    [
        lambda m: {
            **m,
            "source_catalog_sha256": "Rate limiting with a token bucket protects APIs.",
        },
        lambda m: {**m, "note_fields": [*m["note_fields"], "A paragraph copied from a book."]},
        lambda m: {**m, "notes": m["notes"] + 1},
    ],
)
def test_map_json_manipulado(tmp_path, vault, tamper):
    root = _clone_with_map(tmp_path, vault)
    meta = root / "brain-mapa" / "_map.json"
    meta.write_text(json.dumps(tamper(json.loads(meta.read_text())), indent=2) + "\n")
    check = _check(load_config(root), "brain-map-sin-texto")
    assert not check.passed and "_map.json" in check.detail


def test_archivo_del_mapa_ausente(tmp_path, vault):
    root = _clone_with_map(tmp_path, vault)
    (root / "brain-mapa" / "AGENTS.md").unlink()
    check = _check(load_config(root), "brain-map-sin-texto")
    assert not check.passed and "AGENTS.md: falta" in check.detail


def test_notas_descartadas_se_avisan(tmp_path, capsys):
    vault = make_vault(tmp_path / "vault")
    catalog = vault / "_catalog.jsonl"
    rows = [json.loads(line) for line in catalog.read_text().splitlines()]
    rows[0]["path"] = "apisec/una ruta con espacios.md"
    (vault / rows[0]["path"]).write_text("# x\n")
    catalog.write_text("".join(json.dumps(r) + "\n" for r in rows))
    root = tmp_path / "repo"
    root.mkdir()
    assert main(["--root", str(root), "brain", "import", str(vault)]) == 0
    assert "1 nota(s) del catálogo no entran en el mapa" in capsys.readouterr().out


def test_el_intake_recibe_el_mapa(tmp_path, vault, monkeypatch):
    from test_intake import ACCEPT

    import factory.cli as cli

    root = _clone_with_map(tmp_path, vault)
    (root / "prompts" / "intake.md").write_text("Eres el intake de prueba.\n")
    runner = FakeRunner(intake=[FakeStep(output=ACCEPT)])
    monkeypatch.setattr(cli, "make_runner", lambda _c: runner)
    assert main(["--root", str(root), "intake", "Configurar el rate limiting"]) == 0
    request = runner.calls_for("intake")[0]
    config = load_config(root)
    assert config.map_path in request.add_dirs
    assert str(config.map_path / "_catalog.jsonl") in request.prompt


def test_clave_repetida_en_los_libros(tmp_path, vault):
    root = _clone_with_map(tmp_path, vault)
    books = root / "brain-mapa" / "_books.json"
    text = books.read_text()
    books.write_text(
        text.replace('"slug": ', '"title": "A paragraph copied from a book.",\n    "slug": ', 1)
    )
    check = _check(load_config(root), "brain-map-sin-texto")
    assert not check.passed and "_books.json: texto distinto" in check.detail


def test_mapa_con_bytes_invalidos(tmp_path, vault):
    root = _clone_with_map(tmp_path, vault)
    (root / "brain-mapa" / "llms.txt").write_bytes(b"\xff\xfe texto")
    check = _check(load_config(root), "brain-map-sin-texto")
    assert not check.passed and "llms.txt: no es UTF-8 válido" in check.detail


def test_commit_rechaza_un_mapa_manipulado(tmp_path, vault):
    root = _clone_with_map(tmp_path, vault)
    catalog = root / "brain-mapa" / "_catalog.jsonl"
    rows = [json.loads(line) for line in catalog.read_text().splitlines()]
    rows[0]["abstract"] = "Texto copiado de un libro."
    catalog.write_text("".join(json.dumps(r) + "\n" for r in rows))
    head = _git(root, "rev-parse", "HEAD").stdout
    with pytest.raises(BrainError, match="no se commitea nada"):
        commit_daily(load_config(root), "mapa")
    assert _git(root, "rev-parse", "HEAD").stdout == head  # nada entró en git
