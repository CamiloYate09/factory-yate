"""Plantillas del harness empaquetadas con factory (8.1)."""

from importlib import resources
from pathlib import Path

from factory.config import load_config
from factory.engine import load_prompt
from factory.scaffold import FILES, read_template

ROOT = Path(__file__).resolve().parents[1]


def test_todas_las_plantillas_se_cargan_desde_el_paquete():
    base = resources.files("factory") / "templates"
    for template, _relative, _exe in FILES:
        assert (base / template).is_file(), template
        assert read_template(template).strip()


def test_plantillas_con_atribucion():
    for template, _relative, _exe in FILES:
        text = read_template(template)
        assert "walkinglabs" in text or "learn-harness-engineering" in text, template


def test_prompts_empaquetados_iguales_a_los_del_repo():
    for role in ("maker", "checker"):
        repo = (ROOT / "prompts" / f"{role}.md").read_text(encoding="utf-8")
        assert read_template(f"prompts/{role}.md") == repo, f"prompts/{role}.md divergió"


def test_plantilla_de_goal_igual_a_la_del_repo():
    assert read_template("goals/_template.md") == (ROOT / "goals" / "_template.md").read_text()


def test_load_prompt_usa_la_plantilla_empaquetada_si_falta_en_el_repo(tmp_path):
    config = load_config(tmp_path)
    text = load_prompt(config, config.roles["checker"])
    assert "Rol: Checker" in text
