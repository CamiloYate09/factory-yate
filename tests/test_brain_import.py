"""Escenarios de `main-brain`: importación, validación, refresco atómico y registro."""

import hashlib
import json
import subprocess

import pytest
from conftest import init_git_repo, make_vault

import factory.brain.importer as importer
from factory.brain import BrainError
from factory.brain.importer import import_vault, leftovers, read_metadata


def _snapshot(root):
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_importar_un_vault(tmp_path, vault):
    before = _snapshot(vault)
    dest = tmp_path / "repo" / "brain-principal"
    result = import_vault(vault, dest, tmp_path / "repo")
    files = {str(p.relative_to(dest)) for p in dest.rglob("*") if p.is_file()}
    assert "apisec/03-rate-limiting/02-token-bucket.md" in files and "_catalog.jsonl" in files
    assert {"_books.json", "llms.txt", "AGENTS.md", ".factory-import.json"} <= files
    assert not any(f.endswith(".pdf") or f.startswith((".obsidian", "_build")) for f in files)
    assert _snapshot(vault) == before  # el origen no cambia
    assert (result.notes, result.books) == (5, 2) and result.tokens > 0


def test_catalogo_con_rutas_inexistentes(tmp_path, vault):
    dest = tmp_path / "brain-principal"
    import_vault(vault, dest, tmp_path)
    previous = _snapshot(dest)
    with (vault / "_catalog.jsonl").open("a") as handle:
        handle.write(json.dumps({"path": "apisec/no-existe.md", "book_id": "apisec"}) + "\n")
    with pytest.raises(BrainError, match="apisec/no-existe.md"):
        import_vault(vault, dest, tmp_path)
    assert _snapshot(dest) == previous and leftovers(dest) == []


def test_origen_sin_catalogo(tmp_path):
    origin = tmp_path / "carpeta"
    (origin / "x").mkdir(parents=True)
    (origin / "x" / "nota.md").write_text("# nota\n")
    dest = tmp_path / "brain-principal"
    with pytest.raises(BrainError, match="no es un vault con catálogo"):
        import_vault(origin, dest, tmp_path)
    assert not dest.exists() and leftovers(dest) == []


def test_refresco_tras_regenerar_el_vault(tmp_path, vault):
    dest = tmp_path / "brain-principal"
    import_vault(vault, dest, tmp_path)
    (vault / "archpy" / "02-repository" / "01-repository-pattern.md").unlink()
    lines = [
        line
        for line in (vault / "_catalog.jsonl").read_text().splitlines()
        if "repository-pattern" not in line
    ]
    (vault / "apisec" / "07-new").mkdir()
    (vault / "apisec" / "07-new" / "01-new.md").write_text("---\ntitle: New\n---\n# New\n")
    lines.append(json.dumps({"path": "apisec/07-new/01-new.md", "book_id": "apisec", "tokens": 3}))
    (vault / "_catalog.jsonl").write_text("\n".join(lines) + "\n")
    import_vault(vault, dest, tmp_path)
    assert (dest / "apisec" / "07-new" / "01-new.md").exists()
    assert not (dest / "archpy" / "02-repository" / "01-repository-pattern.md").exists()
    assert (dest / "_catalog.jsonl").read_text() == (vault / "_catalog.jsonl").read_text()


def test_importacion_interrumpida(tmp_path, vault, monkeypatch):
    dest = tmp_path / "brain-principal"
    import_vault(vault, dest, tmp_path)
    previous = _snapshot(dest)
    calls = {"n": 0}
    original = importer._copy_file

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 3:
            raise OSError("disco lleno")
        original(src, dst)

    monkeypatch.setattr(importer, "_copy_file", flaky)
    with pytest.raises(OSError, match="disco lleno"):
        import_vault(vault, dest, tmp_path)
    assert _snapshot(dest) == previous
    assert leftovers(dest) == []


def test_primera_importacion_dentro_del_repo(tmp_path):
    repo = init_git_repo(tmp_path / "repo")
    vault = make_vault(tmp_path / "vault")
    result = import_vault(vault, repo / "brain-principal", repo)
    assert result.gitignore_added
    assert "/brain-principal/" in (repo / ".gitignore").read_text()
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True
    )
    assert "brain-principal" not in status.stdout
    assert import_vault(vault, repo / "brain-principal", repo).gitignore_added is False


def test_metadatos_de_la_importacion(tmp_path, vault):
    dest = tmp_path / "brain-principal"
    import_vault(vault, dest, tmp_path)
    meta = read_metadata(dest)
    assert meta["source"] == str(vault) and meta["notes"] == 5 and meta["books"] == 2
    assert (
        meta["catalog_sha256"]
        == hashlib.sha256((vault / "_catalog.jsonl").read_bytes()).hexdigest()
    )


def test_destino_dentro_del_origen(tmp_path, vault):
    with pytest.raises(BrainError, match="no puede estar dentro"):
        import_vault(vault, vault / "copia", tmp_path)


def test_estado_del_cerebro_principal(tmp_path, vault, capsys):
    from factory.cli import main

    root = init_git_repo(tmp_path / "repo")
    assert main(["--root", str(root), "brain", "import", str(vault)]) == 0
    out = capsys.readouterr().out
    assert "5 notas, 2 libros" in out and "Añadido a .gitignore" in out
    assert main(["--root", str(root), "brain", "status"]) == 0
    status = capsys.readouterr().out
    assert f"origen {vault}" in status and "5 notas" in status and "2 libros" in status
    assert "catálogo" in status and "tokens" in status


def test_import_de_origen_invalido_por_cli(tmp_path, capsys):
    from factory.cli import main

    root = init_git_repo(tmp_path / "repo")
    assert main(["--root", str(root), "brain", "import", str(tmp_path / "nada")]) == 2
    assert "No existe el directorio de origen" in capsys.readouterr().err


def test_huella_de_integridad(tmp_path, vault):
    from factory.brain.integrity import fingerprint

    dest = tmp_path / "brain-principal"
    import_vault(vault, dest, tmp_path)
    first = fingerprint(dest)
    assert first and fingerprint(dest) == first  # estable sin cambios
    note = dest / "apisec" / "05-injection" / "01-sql-injection.md"
    note.write_text(note.read_text() + "\nañadido\n")
    assert fingerprint(dest) != first
    assert fingerprint(tmp_path / "no-existe") == ""
