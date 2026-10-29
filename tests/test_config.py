"""Configuración de la fábrica: valores por defecto, roles y modos de permisos."""

import pytest

from factory.config import ConfigError, load_config


def _write(root, text):
    (root / "factory.toml").write_text(text, encoding="utf-8")


def test_valores_por_defecto_sin_archivo(tmp_path):
    config = load_config(tmp_path)
    assert config.source is None
    assert config.loop.max_rounds == 8
    assert config.loop.max_budget_usd == 5.0
    assert config.tick.daily_budget_usd == 10.0
    assert config.roles["maker"].model != config.roles["checker"].model
    assert config.roles["checker"].permission_mode == "dontAsk"
    assert "Bash" in config.roles["checker"].denied_tools
    assert "Bash(git push:*)" in config.roles["maker"].denied_tools


def test_worktrees_fuera_del_repo_por_defecto(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    config = load_config(root)
    assert config.worktrees_path == tmp_path / "repo.factory-worktrees"
    assert root not in config.worktrees_path.parents


def test_carga_secciones_y_roles(tmp_path):
    _write(
        tmp_path,
        """
[loop]
max_rounds = 3
max_budget_usd = 1
[roles.maker]
model = "haiku"
allowed_tools = ["Read"]
""",
    )
    config = load_config(tmp_path)
    assert config.loop.max_rounds == 3
    assert config.loop.max_budget_usd == 1.0
    assert config.roles["maker"].model == "haiku"
    assert config.roles["maker"].allowed_tools == ["Read"]
    assert config.roles["checker"].model == "opus"


def test_rechaza_bypass_permissions(tmp_path):
    _write(tmp_path, '[roles.maker]\npermission_mode = "bypassPermissions"\n')
    with pytest.raises(ConfigError, match="prohibido"):
        load_config(tmp_path)


def test_rechaza_modo_desconocido(tmp_path):
    _write(tmp_path, '[roles.checker]\npermission_mode = "yolo"\n')
    with pytest.raises(ConfigError, match="desconocido"):
        load_config(tmp_path)


@pytest.mark.parametrize(
    "text, match",
    [
        ("[loop]\nmax_rounds = 0\n", "mayor que 0"),
        ("[loop]\nmax_rondas = 3\n", "Clave desconocida"),
        ("[loops]\nx = 1\n", "Sección desconocida"),
        ("[roles.revisor]\nmodel = 'x'\n", "Rol desconocido"),
        ("[loop]\nmax_rounds = 'tres'\n", "numérico"),
        ("no es toml = = ", "TOML"),
    ],
)
def test_errores_de_configuracion(tmp_path, text, match):
    _write(tmp_path, text)
    with pytest.raises(ConfigError, match=match):
        load_config(tmp_path)


def test_factory_toml_del_repo_es_valido():
    from pathlib import Path

    config = load_config(Path(__file__).resolve().parents[1])
    assert config.harness.verify_command == "./scripts/check.sh"


def test_factory_toml_no_puede_quitar_denegaciones_obligatorias(tmp_path):
    _write(
        tmp_path,
        "[roles.maker]\ndenied_tools = []\n"
        '[roles.checker]\nallowed_tools = ["Read", "Bash", "Edit"]\ndenied_tools = []\n',
    )
    config = load_config(tmp_path)
    assert "Bash(git push:*)" in config.roles["maker"].denied_tools
    assert "Edit(feature_list.json)" in config.roles["maker"].denied_tools
    checker = config.roles["checker"]
    assert checker.allowed_tools == ["Read"]
    assert {"Bash", "Edit", "Write", "Bash(git push:*)"} <= set(checker.denied_tools)


def test_brain_valores_por_defecto_y_rutas(tmp_path):
    config = load_config(tmp_path)
    assert config.brain.inject_max_tokens == 3000 and config.brain.search_limit == 8
    assert config.principal_path == (tmp_path / "brain-principal").resolve()
    assert config.daily_path == (tmp_path / "brain-diario").resolve()
    _write(
        tmp_path,
        f'[brain]\nprincipal_dir = "{tmp_path / "fuera" / "libros"}"\ndaily_dir = "notas"\n',
    )
    config = load_config(tmp_path)
    assert config.principal_path == tmp_path / "fuera" / "libros"
    assert config.daily_path == (tmp_path / "notas").resolve()


@pytest.mark.parametrize("key", ["inject_max_tokens", "search_limit"])
def test_brain_valores_no_positivos(tmp_path, key):
    _write(tmp_path, f"[brain]\n{key} = 0\n")
    with pytest.raises(ConfigError, match="mayor que 0"):
        load_config(tmp_path)
