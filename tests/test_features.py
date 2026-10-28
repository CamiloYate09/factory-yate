"""Escenarios de `agent-harness`: lista de features como fuente de verdad."""

from conftest import feature_doc, make_feature

from factory import features


def test_feature_sin_verificacion_se_reporta_con_id_y_campo():
    data = feature_doc(make_feature("f-1", verification=[]))
    issues = features.validate(data)
    assert any(i.feature_id == "f-1" and i.field == "verification" for i in issues)


def test_feature_con_estado_invalido():
    data = feature_doc(make_feature("f-1", status="done"))
    issues = features.validate(data)
    assert [(i.feature_id, i.field) for i in issues] == [("f-1", "status")]
    assert "not_started" in issues[0].message


def test_feature_sin_campo_obligatorio():
    feature = make_feature("f-1")
    del feature["user_visible_behavior"]
    issues = features.validate(feature_doc(feature))
    assert [(i.feature_id, i.field) for i in issues] == [("f-1", "user_visible_behavior")]


def test_dos_features_activas_nombra_ambas():
    data = feature_doc(make_feature("f-1", "in_progress"), make_feature("f-2", "in_progress"))
    issues = features.validate(data)
    assert len(issues) == 1
    assert "f-1" in issues[0].message and "f-2" in issues[0].message


def test_promocion_manual_sin_evidencia_falla():
    data = feature_doc(make_feature("f-1", "passing", verification=["pytest -q"]))
    issues = features.validate(data)
    assert [(i.feature_id, i.field) for i in issues] == [("f-1", "evidence")]
    assert "pytest -q" in issues[0].message


def test_passing_con_evidencia_completa_es_valida():
    feature = make_feature(
        "f-1",
        "passing",
        verification=["pytest -q"],
        evidence=[{"command": "pytest -q", "exit_code": 0, "date": "x", "commit": "abc"}],
    )
    assert features.validate(feature_doc(feature)) == []


def test_evidencia_fallida_no_cuenta():
    feature = make_feature(
        "f-1",
        "passing",
        verification=["pytest -q"],
        evidence=[{"command": "pytest -q", "exit_code": 1, "date": "x", "commit": "abc"}],
    )
    assert [i.field for i in features.validate(feature_doc(feature))] == ["evidence"]


def test_ids_duplicados():
    data = feature_doc(make_feature("f-1"), make_feature("f-1"))
    assert any(i.field == "id" for i in features.validate(data))
