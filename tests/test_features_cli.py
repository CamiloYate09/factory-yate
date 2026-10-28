"""Escenarios de `agent-harness`: promoción a passing solo con evidencia."""

import json

from conftest import make_feature, write_features

from factory.cli import main
from factory.util import git_head


def _load(repo):
    return json.loads((repo / "feature_list.json").read_text())["features"]


def test_verificacion_exitosa_promueve_con_evidencia(git_repo, capsys):
    write_features(git_repo, make_feature("f-1", verification=["true", "echo ok"]))
    assert main(["--root", str(git_repo), "features", "verify", "f-1"]) == 0
    feature = _load(git_repo)[0]
    assert feature["status"] == "passing"
    assert [e["command"] for e in feature["evidence"]] == ["true", "echo ok"]
    for record in feature["evidence"]:
        assert record["exit_code"] == 0
        assert record["commit"] == git_head(git_repo)
        assert record["date"]


def test_verificacion_fallida_no_promueve_e_informa_comando(git_repo, capsys):
    write_features(git_repo, make_feature("f-1", verification=["true", "echo roto; exit 3"]))
    assert main(["--root", str(git_repo), "features", "verify", "f-1"]) == 1
    feature = _load(git_repo)[0]
    assert feature["status"] == "not_started"
    assert feature["evidence"] == []
    out = capsys.readouterr().out
    assert "Comando que falló: echo roto; exit 3" in out
    assert "roto" in out


def test_start_respeta_wip(git_repo, capsys):
    write_features(git_repo, make_feature("f-1", "in_progress"), make_feature("f-2"))
    assert main(["--root", str(git_repo), "features", "start", "f-2"]) == 2
    assert "WIP=1" in capsys.readouterr().err
    assert _load(git_repo)[1]["status"] == "not_started"


def test_start_activa_feature(git_repo):
    write_features(git_repo, make_feature("f-1"))
    assert main(["--root", str(git_repo), "features", "start", "f-1"]) == 0
    assert _load(git_repo)[0]["status"] == "in_progress"


def test_validate_reporta_problemas(git_repo, capsys):
    write_features(git_repo, make_feature("f-1", "passing"))
    assert main(["--root", str(git_repo), "features", "validate"]) == 1
    assert "[f-1] evidence" in capsys.readouterr().out


def test_verify_usa_python_del_entorno(git_repo):
    write_features(git_repo, make_feature("f-1", verification=["python -c 'import yaml'"]))
    assert main(["--root", str(git_repo), "features", "verify", "f-1"]) == 0
