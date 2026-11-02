"""Escenarios de `agent-backends`: selección del backend, precios y Strands no instalado."""

import sys

import pytest
from conftest import make_loop_repo, write_goal

import factory.cli as cli
from factory.agents.base import AgentRequest
from factory.agents.claude_code import ClaudeCodeRunner
from factory.agents.pricing import DEFAULT_PRICES, ModelPrice, cost_usd
from factory.agents.strands import StrandsRunner
from factory.cli import main
from factory.config import ConfigError, load_config


def _write(root, text):
    (root / "factory.toml").write_text(text, encoding="utf-8")


@pytest.fixture
def sin_strands(monkeypatch):
    """Simula que el extra no está instalado: `import strands_harness` lanza ImportError."""
    monkeypatch.setitem(sys.modules, "strands_harness", None)


def test_configuracion_sin_backend(tmp_path):
    _write(tmp_path, '[agent]\ncommand = "claude"\n')
    config = load_config(tmp_path)
    assert config.agent.backend == "claude-code"
    assert isinstance(cli.make_runner(config), ClaudeCodeRunner)


def test_sin_archivo_el_backend_es_claude_code(tmp_path):
    assert isinstance(cli.make_runner(load_config(tmp_path)), ClaudeCodeRunner)


def test_backend_desconocido(tmp_path, capsys):
    _write(tmp_path, '[agent]\nbackend = "otro"\n')
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path)
    assert "claude-code" in str(exc.value) and "strands" in str(exc.value)


def test_backend_desconocido_hace_fallar_los_comandos(tmp_path, capsys):
    root = make_loop_repo(tmp_path)
    _write(root, '[agent]\nbackend = "otro"\n')
    assert main(["--root", str(root), "status"]) != 0
    err = capsys.readouterr().err
    assert "claude-code" in err and "strands" in err


def test_backend_strands_elige_el_runner_de_strands(tmp_path):
    _write(tmp_path, '[agent]\nbackend = "strands"\n')
    runner = cli.make_runner(load_config(tmp_path))
    assert isinstance(runner, StrandsRunner)


def test_alias_de_modelo_y_proveedor(tmp_path):
    _write(
        tmp_path,
        """
[agent]
backend = "strands"
[agent.strands]
provider = "bedrock"
[agent.strands.models]
sonnet = "bedrock/global.anthropic.claude-sonnet-5-5"
""",
    )
    strands = load_config(tmp_path).agent.strands
    assert strands.resolve_model("sonnet") == "bedrock/global.anthropic.claude-sonnet-5-5"
    assert strands.resolve_model("opus") == "anthropic/claude-opus-5-5"  # alias por defecto
    assert strands.resolve_model("mi-modelo") == "bedrock/mi-modelo"
    assert strands.resolve_model("openai/gpt-x") == "openai/gpt-x"
    # Bedrock tiene precios propios: sin declararlos, el modelo no tiene precio.
    assert strands.price_for("sonnet") is None


def test_sobrescritura_de_un_precio(tmp_path):
    _write(
        tmp_path,
        """
[agent.strands.prices."anthropic/claude-haiku-5-5"]
input = 0.10
output = 0.50
cache_read = 0.01
cache_write = 0.125
[agent.strands.prices."ollama/llama"]
input = 0
output = 0
""",
    )
    strands = load_config(tmp_path).agent.strands
    assert strands.price_for("haiku") == ModelPrice(0.10, 0.50, 0.01, 0.125)
    assert strands.price_for("opus") == DEFAULT_PRICES["anthropic/claude-opus-5-5"]
    assert strands.price_for("ollama/llama") == ModelPrice(0.0, 0.0, 0.0, 0.0)


def test_precio_sin_cache_no_subestima(tmp_path):
    _write(tmp_path, '[agent.strands.prices."anthropic/x"]\ninput = 2\noutput = 8\n')
    price = load_config(tmp_path).agent.strands.price_for("anthropic/x")
    assert price.cache_read == 2.0  # sin dato, la lectura en caché cuesta como la entrada
    assert price.cache_write == 2.5  # y la escritura como la de 5 minutos


@pytest.mark.parametrize(
    "tabla, mensaje",
    [
        ("input = 1\n", "output"),
        ("input = -1\noutput = 1\n", "mayor o igual que 0"),
        ('input = "1"\noutput = 1\n', "número"),
        ("input = 1\noutput = 1\nbatch = 1\n", "batch"),
    ],
)
def test_precio_invalido(tmp_path, tabla, mensaje):
    _write(tmp_path, f'[agent.strands.prices."anthropic/x"]\n{tabla}')
    with pytest.raises(ConfigError, match=mensaje):
        load_config(tmp_path)


def test_clave_desconocida_en_strands(tmp_path):
    _write(tmp_path, '[agent.strands]\nproveedor = "anthropic"\n')
    with pytest.raises(ConfigError, match="proveedor"):
        load_config(tmp_path)


def test_coste_con_cache():
    price = DEFAULT_PRICES["anthropic/claude-sonnet-5-5"]
    # 1M de entrada (2) + 0,5M de salida (5) + 2M leídos de caché (0,4) + 0,1M escritos (0,25)
    assert cost_usd(price, 1_000_000, 500_000, 2_000_000, 100_000) == pytest.approx(7.65)


def _request(tmp_path):
    return AgentRequest(
        role="checker",
        prompt="revisa",
        system_prompt="",
        cwd=tmp_path,
        model="opus",
        permission_mode="dontAsk",
    )


def test_strands_no_instalado(tmp_path, sin_strands):
    runner = StrandsRunner(load_config(tmp_path).agent.strands)
    result = runner.run(_request(tmp_path))
    assert not result.ok
    assert result.cost_usd == 0
    assert "pip install -e '.[strands]'" in result.error


def test_intake_usa_el_backend_configurado(tmp_path, sin_strands, capsys):
    root = make_loop_repo(tmp_path)
    _write(root, '[agent]\nbackend = "strands"\n')
    code = main(["--root", str(root), "intake", "Añadir un comando de saludo"])
    assert code != 0
    salida = capsys.readouterr()
    assert "pip install -e '.[strands]'" in salida.out + salida.err


def test_goal_run_usa_el_backend_configurado(tmp_path, sin_strands, capsys):
    root = make_loop_repo(tmp_path)
    _write(root, '[agent]\nbackend = "strands"\n')
    (root / ".gitignore").write_text(".factory/\nfactory.toml\ngoals/\n")
    goal = write_goal(root)
    code = main(["--root", str(root), "goal", "run", str(goal)])
    assert code == 7  # agent_error: el loop aplica su regla de fallos consecutivos
    eventos = (root / ".factory").rglob("events.jsonl")
    assert any("pip install -e '.[strands]'" in p.read_text() for p in eventos)


def test_claves_de_precio_normalizadas(tmp_path):
    _write(
        tmp_path,
        """
[agent.strands.prices.sonnet]
input = 1
output = 5
[agent.strands.prices."claude-nuevo"]
input = 3
output = 9
""",
    )
    strands = load_config(tmp_path).agent.strands
    assert strands.price_for("sonnet") == ModelPrice(1.0, 5.0, 1.0, 1.25)
    assert strands.price_for("anthropic/claude-nuevo").output == 9.0
