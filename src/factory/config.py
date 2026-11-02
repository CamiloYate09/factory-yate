"""Configuración de la fábrica (`factory.toml`).

Todas las secciones son opcionales; lo que falte toma los valores por defecto de abajo
(diseño D3). Las claves desconocidas son un error, para que una errata no pase inadvertida.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from factory.agents.pricing import CACHE_WRITE_FACTOR, DEFAULT_PRICES, ModelPrice

CONFIG_FILE = "factory.toml"

# Modos de `claude --permission-mode` aceptados. `bypassPermissions` está prohibido siempre.
VALID_PERMISSION_MODES = ("acceptEdits", "auto", "manual", "dontAsk", "plan")
FORBIDDEN_PERMISSION_MODES = ("bypassPermissions",)

ROLES = ("maker", "checker", "intake")
READ_ONLY_ROLES = ("checker", "intake")


class ConfigError(ValueError):
    pass


@dataclass
class HarnessConfig:
    entry_file: str = "AGENTS.md"
    feature_list: str = "feature_list.json"
    progress_file: str = "progress.md"
    handoff_file: str = "session-handoff.md"
    checklist_file: str = "docs/harness/clean-state-checklist.md"
    start_command: str = "./init.sh"
    # None: se detecta (scripts/check.sh) si existe.
    verify_command: str | None = None


@dataclass
class LoopConfig:
    max_rounds: int = 8
    max_budget_usd: float = 5.0
    no_progress_rounds: int = 3
    consecutive_passes: int = 1
    round_timeout_min: float = 20
    verify_timeout_min: float = 10
    agent_error_rounds: int = 2
    summary_max_chars: int = 4000
    main_branch: str = "main"
    state_dir: str = ".factory"
    # Vacío: ../<repo>.factory-worktrees (fuera del árbol del repo; diseño D5).
    worktrees_dir: str = ""
    # Globs de archivos existentes que una ronda no puede modificar, borrar ni renombrar.
    protected_paths: list[str] = field(default_factory=list)


@dataclass
class TickConfig:
    max_rounds: int = 3
    budget_per_tick_usd: float = 2.0
    daily_budget_usd: float = 10.0
    circuit_after: int = 3
    # 0: se calcula como round_timeout_min * max_rounds.
    lock_stale_min: float = 0


@dataclass
class AlertsConfig:
    inbox_pending_max: int = 3
    # Avisa si los tokens de entrada de la última ronda superan este múltiplo de la primera.
    token_growth_ratio: float = 2.0
    # Avisa si las líneas cambiadas pendientes de revisión superan este número.
    pending_lines_max: int = 500


VALID_BACKENDS = ("claude-code", "strands")


def _default_strands_models() -> dict[str, str]:
    return {
        "opus": "anthropic/claude-opus-5-5",
        "sonnet": "anthropic/claude-sonnet-5-5",
        "haiku": "anthropic/claude-haiku-5-5",
    }


@dataclass
class StrandsConfig:
    """Backend Strands: alias de modelo de los roles y precios por modelo (diseño D4)."""

    provider: str = "anthropic"
    models: dict[str, str] = field(default_factory=_default_strands_models)
    prices: dict[str, ModelPrice] = field(default_factory=lambda: dict(DEFAULT_PRICES))

    def resolve_model(self, model: str) -> str:
        """Alias del rol (`sonnet`) → id de Strands; un id con proveedor se usa tal cual."""
        if model in self.models:
            return self.models[model]
        return model if "/" in model else f"{self.provider}/{model}"

    def price_for(self, model: str) -> ModelPrice | None:
        return self.prices.get(self.resolve_model(model))


@dataclass
class AgentConfig:
    command: str = "claude"
    backend: str = "claude-code"
    strands: StrandsConfig = field(default_factory=StrandsConfig)


@dataclass
class BrainConfig:
    """Cerebros de conocimiento: principal (libros, fuera de git) y diario (versionado)."""

    principal_dir: str = "brain-principal"
    daily_dir: str = "brain-diario"
    map_dir: str = "brain-mapa"  # mapa de la biblioteca: metadatos versionados, sin texto
    inject_max_tokens: int = 3000
    search_limit: int = 8


@dataclass
class RoleConfig:
    model: str
    prompt: str
    permission_mode: str
    allowed_tools: list[str]
    denied_tools: list[str]


PUBLISH_DENIED = [
    "Bash(git push:*)",
    "Bash(gh:*)",
    "Bash(git commit:*)",
    "Bash(git reset:*)",
    "Bash(git checkout:*)",
    "Bash(git rebase:*)",
    "Bash(git merge:*)",
]


# Políticas que ninguna configuración ni goal.md puede quitar (spec maker-checker-loop):
# publicar está denegado para ambos roles y el checker es de solo lectura.
CHECKER_READ_ONLY = ("Read", "Glob", "Grep")
MANDATORY_DENIED = {
    "maker": [*PUBLISH_DENIED, "Edit(feature_list.json)", "Write(feature_list.json)"],
    "checker": ["Edit", "Write", "NotebookEdit", "Bash", *PUBLISH_DENIED],
    "intake": ["Edit", "Write", "NotebookEdit", "Bash", *PUBLISH_DENIED],
}


def brain_denials(paths: list[Path]) -> list[str]:
    """Denegaciones obligatorias de escritura sobre los cerebros (rutas absolutas: `//ruta`)."""
    rules = []
    for path in paths:
        absolute = "//" + path.resolve().as_posix().lstrip("/")
        rules += [f"Edit({absolute}/**)", f"Write({absolute}/**)"]
    return rules


def enforce_role_policy(name: str, role: RoleConfig) -> RoleConfig:
    """Rol efectivo: añade las denegaciones obligatorias y limita el checker a lectura."""
    check_permission_mode(role.permission_mode, f"[roles.{name}]")
    denied = list(role.denied_tools)
    denied += [tool for tool in MANDATORY_DENIED[name] if tool not in denied]
    allowed = list(role.allowed_tools)
    if name in READ_ONLY_ROLES:
        allowed = [tool for tool in allowed if tool in CHECKER_READ_ONLY]
    return RoleConfig(role.model, role.prompt, role.permission_mode, allowed, denied)


def default_roles() -> dict[str, RoleConfig]:
    return {
        "maker": RoleConfig(
            model="sonnet",
            prompt="prompts/maker.md",
            permission_mode="acceptEdits",
            allowed_tools=[
                "Read",
                "Edit",
                "Write",
                "Glob",
                "Grep",
                "Bash(git status:*)",
                "Bash(git diff:*)",
                "Bash(python -m pytest:*)",
                "Bash(python -m ruff:*)",
            ],
            denied_tools=[*PUBLISH_DENIED, "Edit(feature_list.json)", "Write(feature_list.json)"],
        ),
        "checker": RoleConfig(
            model="opus",
            prompt="prompts/checker.md",
            permission_mode="dontAsk",
            allowed_tools=["Read", "Glob", "Grep"],
            denied_tools=["Edit", "Write", "NotebookEdit", "Bash", *PUBLISH_DENIED],
        ),
        # Triaje de peticiones: una sola invocación por petición, solo lectura (request-intake).
        "intake": RoleConfig(
            model="opus",
            prompt="prompts/intake.md",
            permission_mode="dontAsk",
            allowed_tools=["Read", "Glob", "Grep"],
            denied_tools=["Edit", "Write", "NotebookEdit", "Bash", *PUBLISH_DENIED],
        ),
    }


@dataclass
class Config:
    root: Path
    harness: HarnessConfig = field(default_factory=HarnessConfig)
    loop: LoopConfig = field(default_factory=LoopConfig)
    tick: TickConfig = field(default_factory=TickConfig)
    alerts: AlertsConfig = field(default_factory=AlertsConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    brain: BrainConfig = field(default_factory=BrainConfig)
    roles: dict[str, RoleConfig] = field(default_factory=default_roles)
    source: Path | None = None

    def path(self, relative: str) -> Path:
        return self.root / relative

    def effective_verify_command(self) -> str | None:
        if self.harness.verify_command:
            return self.harness.verify_command
        if (self.root / "scripts" / "check.sh").exists():
            return "./scripts/check.sh"
        return None

    @property
    def state_path(self) -> Path:
        return self.root / self.loop.state_dir

    @property
    def principal_path(self) -> Path:
        """Ruta absoluta del cerebro principal, siempre desde la raíz del repo principal."""
        return self._abs(self.brain.principal_dir)

    @property
    def daily_path(self) -> Path:
        return self._abs(self.brain.daily_dir)

    @property
    def map_path(self) -> Path:
        return self._abs(self.brain.map_dir)

    def _abs(self, value: str) -> Path:
        path = Path(value).expanduser()  # resuelta: --add-dir y las denegaciones usan la misma ruta
        return (path if path.is_absolute() else self.root / path).resolve()

    @property
    def worktrees_path(self) -> Path:
        if self.loop.worktrees_dir:
            path = Path(self.loop.worktrees_dir)
            return path if path.is_absolute() else (self.root / path).resolve()
        return self.root.parent / f"{self.root.name}.factory-worktrees"

    @property
    def lock_stale_s(self) -> float:
        minutes = self.tick.lock_stale_min or self.loop.round_timeout_min * self.tick.max_rounds
        return minutes * 60


def _section(data: dict, name: str) -> dict:
    value = data.get(name, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{name}] debe ser una tabla en {CONFIG_FILE}")
    return value


def _coerce(value: object, current: object, key: str, section: str) -> object:
    if isinstance(current, bool) or current is None:
        return value
    if isinstance(current, (int, float)):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"[{section}].{key} debe ser numérico")
        if value <= 0 and key not in {"lock_stale_min"}:
            raise ConfigError(f"[{section}].{key} debe ser mayor que 0")
        return type(current)(value) if isinstance(current, float) else value
    if isinstance(current, list):
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ConfigError(f"[{section}].{key} debe ser una lista de texto")
        return list(value)
    if not isinstance(value, str):
        raise ConfigError(f"[{section}].{key} debe ser texto")
    return value


def apply_values(target: object, values: dict, section: str) -> None:
    known = {f.name for f in fields(target)}  # type: ignore[arg-type]
    for key, value in values.items():
        if key not in known:
            raise ConfigError(f"Clave desconocida '{key}' en [{section}] de {CONFIG_FILE}")
        setattr(target, key, _coerce(value, getattr(target, key), key, section))


def _load_agent(agent: AgentConfig, values: dict) -> None:
    values = dict(values)
    strands = values.pop("strands", {})
    if not isinstance(strands, dict):
        raise ConfigError(f"[agent.strands] debe ser una tabla en {CONFIG_FILE}")
    apply_values(agent, values, "agent")
    if agent.backend not in VALID_BACKENDS:
        raise ConfigError(
            f"[agent].backend '{agent.backend}' desconocido; "
            f"usa uno de: {', '.join(VALID_BACKENDS)}"
        )
    strands = dict(strands)
    models = strands.pop("models", {})
    prices = strands.pop("prices", {})
    apply_values(agent.strands, strands, "agent.strands")
    if not isinstance(models, dict) or not all(
        isinstance(k, str) and isinstance(v, str) and v for k, v in models.items()
    ):
        raise ConfigError("[agent.strands.models] debe asociar cada alias a un id de modelo")
    agent.strands.models.update(models)
    if not isinstance(prices, dict):
        raise ConfigError("[agent.strands.prices] debe ser una tabla")
    for model, price in prices.items():
        # La clave se normaliza como los modelos de los roles: `sonnet` o `claude-x` sin proveedor
        # se guardan con su id resuelto y la sobrescritura no se pierde en silencio.
        agent.strands.prices[agent.strands.resolve_model(model)] = _model_price(model, price)


def _model_price(model: str, values: object) -> ModelPrice:
    """`input` y `output` obligatorios; la caché, si falta, se estima sin subestimar."""
    where = f'[agent.strands.prices."{model}"]'
    if not isinstance(values, dict):
        raise ConfigError(f"{where} debe ser una tabla")
    unknown = set(values) - {"input", "output", "cache_read", "cache_write"}
    if unknown:
        raise ConfigError(f"Clave desconocida en {where}: {', '.join(sorted(unknown))}")
    numbers: dict[str, float] = {}
    for key, value in values.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise ConfigError(f"{where}.{key} debe ser un número mayor o igual que 0")
        numbers[key] = float(value)
    for key in ("input", "output"):
        if key not in numbers:
            raise ConfigError(f"{where} necesita '{key}' (USD por millón de tokens)")
    return ModelPrice(
        input=numbers["input"],
        output=numbers["output"],
        cache_read=numbers.get("cache_read", numbers["input"]),
        cache_write=numbers.get("cache_write", numbers["input"] * CACHE_WRITE_FACTOR),
    )


def check_permission_mode(mode: str, where: str) -> None:
    if mode in FORBIDDEN_PERMISSION_MODES:
        raise ConfigError(
            f"{where}: el modo '{mode}' omite las comprobaciones de permisos y está prohibido. "
            f"Usa uno de: {', '.join(VALID_PERMISSION_MODES)}"
        )
    if mode not in VALID_PERMISSION_MODES:
        raise ConfigError(
            f"{where}: modo de permisos '{mode}' desconocido; usa uno de: "
            f"{', '.join(VALID_PERMISSION_MODES)}"
        )


def load_config(root: Path) -> Config:
    """Carga `factory.toml` de `root`; si no existe, devuelve los valores por defecto."""
    config = Config(root=root)
    path = root / CONFIG_FILE
    if path.exists():
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"{CONFIG_FILE} no es TOML válido: {exc}") from exc
        config.source = path
        known = {"harness", "loop", "tick", "alerts", "agent", "roles", "brain"}
        unknown = set(data) - known
        if unknown:
            raise ConfigError(f"Sección desconocida en {CONFIG_FILE}: {', '.join(sorted(unknown))}")
        apply_values(config.harness, _section(data, "harness"), "harness")
        apply_values(config.loop, _section(data, "loop"), "loop")
        apply_values(config.tick, _section(data, "tick"), "tick")
        apply_values(config.alerts, _section(data, "alerts"), "alerts")
        _load_agent(config.agent, _section(data, "agent"))
        apply_values(config.brain, _section(data, "brain"), "brain")
        roles = _section(data, "roles")
        for name, values in roles.items():
            if name not in ROLES:
                raise ConfigError(f"Rol desconocido [roles.{name}]; roles válidos: {ROLES}")
            if not isinstance(values, dict):
                raise ConfigError(f"[roles.{name}] debe ser una tabla")
            apply_values(config.roles[name], values, f"roles.{name}")
    config.roles = {name: enforce_role_policy(name, role) for name, role in config.roles.items()}
    _check_brain_paths(config)
    return config


def _check_brain_paths(config: Config) -> None:
    """Los tres cerebros en rutas distintas, sin anidarse ni ser la raíz del repo."""
    paths = {
        "principal_dir": config.principal_path,
        "daily_dir": config.daily_path,
        "map_dir": config.map_path,
    }
    root = config.root.resolve()
    for key, path in paths.items():
        if path == root or path in root.parents:
            raise ConfigError(f"[brain].{key} no puede ser la raíz del repo ni contenerla")
    items = list(paths.items())
    for i, (key_a, a) in enumerate(items):
        for key_b, b in items[i + 1 :]:
            if a == b or a in b.parents or b in a.parents:
                raise ConfigError(f"[brain].{key_a} y [brain].{key_b} no pueden solaparse")
