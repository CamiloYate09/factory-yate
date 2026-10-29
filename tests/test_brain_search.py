"""Escenarios de `brain-retrieval`: búsqueda en los cerebros y consultas declaradas."""

import json

from factory.brain.catalog import PRINCIPAL, Entry
from factory.brain.daily import DailyBrain
from factory.brain.importer import import_vault
from factory.brain.search import score
from factory.brain.text import terms
from factory.cli import main
from factory.config import load_config


def _root_with_brains(tmp_path, vault):
    root = tmp_path / "repo"
    root.mkdir()
    import_vault(vault, root / "brain-principal", root)
    DailyBrain(root / "brain-diario").add(
        "El rate limiting por usuario se configura en el gateway", kind="decision", day="2026-10-28"
    )
    return root


def test_consulta_con_resultados(tmp_path, vault, capsys):
    root = _root_with_brains(tmp_path, vault)
    assert main(["--root", str(root), "brain", "search", "rate limiting", "--json"]) == 0
    hits = json.loads(capsys.readouterr().out)
    titles = [h["title"] for h in hits]
    assert titles[0] in ("Token bucket rate limiting", "Rate limiting")
    first = next(h for h in hits if h["title"] == "Token bucket rate limiting")
    assert first["citation"] == "Securing APIs · cap. 3 · pp. 41–44"
    assert first["path"] == "apisec/03-rate-limiting/02-token-bucket.md" and first["tokens"] > 0
    assert any(
        h["brain"] == "diario" and h["citation"].startswith("Cerebro diario · 2026-10-28")
        for h in hits
    )
    scores = [h["score"] for h in hits]
    assert scores == sorted(scores, reverse=True)


def test_consulta_sin_resultados(tmp_path, vault, capsys):
    root = _root_with_brains(tmp_path, vault)
    assert main(["--root", str(root), "brain", "search", "límite de tasa"]) == 0
    out = capsys.readouterr().out
    assert "Sin resultados" in out and "términos en inglés" in out


def test_cerebro_no_configurado_o_vacio(tmp_path, capsys):
    DailyBrain(tmp_path / "brain-diario").add("Usar SQLite en local", day="2026-10-28")
    assert main(["--root", str(tmp_path), "brain", "search", "sqlite"]) == 0
    out = capsys.readouterr().out
    assert "Cerebro principal no disponible" in out and "factory brain import" in out
    assert "Usar SQLite en local" in out


def test_filtro_por_cerebro_y_limite(tmp_path, vault, capsys):
    root = _root_with_brains(tmp_path, vault)
    main(
        [
            "--root",
            str(root),
            "brain",
            "search",
            "rate limiting",
            "--brain",
            "principal",
            "--limit",
            "1",
            "--json",
        ]
    )
    hits = json.loads(capsys.readouterr().out)
    assert len(hits) == 1 and hits[0]["brain"] == "principal"


def test_acentos_y_palabras_vacias(tmp_path, capsys):
    DailyBrain(tmp_path / "brain-diario").add("La migración de la base de datos", day="2026-10-28")
    config = load_config(tmp_path)
    from factory.brain.search import search

    assert search(config, "migracion")[0].entry.title == "La migración de la base de datos"
    assert search(config, "la de el") == []


GOAL = """---
id: g
objective: Limitar peticiones por usuario
acceptance:
  - name: t
    run: "true"
{knowledge}---
cuerpo
"""


def _goal(knowledge=""):
    from factory.config import LoopConfig
    from factory.goal import parse_goal_text

    return parse_goal_text(GOAL.format(knowledge=knowledge), LoopConfig())


def test_objetivo_con_consultas_declaradas():
    from factory.brain.inject import queries_for

    goal = _goal('knowledge:\n  queries: ["rate limiting", "api gateway"]\n')
    principal, daily = queries_for(goal)
    assert principal == ["rate limiting", "api gateway"]
    assert daily == ["rate limiting", "api gateway", "Limitar peticiones por usuario"]


def test_sin_consultas_usa_el_objetivo_como_ultimo_recurso():
    from factory.brain.inject import queries_for

    assert queries_for(_goal())[0] == ["Limitar peticiones por usuario"]


def test_inyeccion_desactivada_y_validacion():
    import pytest

    from factory.brain.inject import queries_for
    from factory.goal import GoalError

    assert queries_for(_goal("knowledge:\n  enabled: false\n")) == ([], [])
    with pytest.raises(GoalError, match="knowledge"):
        _goal("knowledge:\n  otro: 1\n")


def test_cobertura_de_la_consulta(tmp_path):
    """Una nota con todos los términos gana a otra con más peso en uno solo (vault real)."""

    def entry(title, keywords):
        return Entry(PRINCIPAL, "x.md", tmp_path / "x.md", title, keywords=keywords)

    query = terms("rate limiting")
    full = entry("Protecting APIs", ["rate-limiting"])
    partial = entry("Rate of Change Defines Architecture", ["rate", "change", "architecture"])
    assert score(full, query, "rate limiting") > score(partial, query, "rate limiting") > 0
    assert score(entry("Unrelated", ["sql"]), query, "rate limiting") == 0
