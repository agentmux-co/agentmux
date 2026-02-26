"""Configuration loading for agentmux."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from agentmux.models import AgentmuxConfig

_ENV_PATTERN = re.compile(r"\$\{(\w+)(?::-(.*?))?\}")


def _substitute_env(value: str) -> str:
    """Replace ${VAR} and ${VAR:-default} patterns with env values."""

    def _replace(match: re.Match[str]) -> str:
        var_name = match.group(1)
        default = match.group(2)
        env_val = os.environ.get(var_name)
        if env_val is not None:
            return env_val
        if default is not None:
            return default
        return match.group(0)

    return _ENV_PATTERN.sub(_replace, value)


def _walk_substitute(obj: Any) -> Any:
    """Recursively substitute env vars in strings within a data structure."""
    if isinstance(obj, str):
        return _substitute_env(obj)
    if isinstance(obj, dict):
        return {k: _walk_substitute(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_substitute(item) for item in obj]
    return obj


def _find_config_file(explicit_path: str | None = None) -> Path | None:
    """Search for config file in standard locations."""
    if explicit_path:
        p = Path(explicit_path)
        return p if p.exists() else None

    candidates = [
        Path("agentmux.yaml"),
        Path.home() / ".config" / "agentmux" / "config.yaml",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def load_config(path: str | None = None) -> AgentmuxConfig:
    """Load and parse agentmux configuration."""
    config_file = _find_config_file(path)

    if config_file is None:
        return AgentmuxConfig()

    with open(config_file) as f:
        raw = yaml.safe_load(f)

    if not raw or not isinstance(raw, dict):
        return AgentmuxConfig()

    raw = _walk_substitute(raw)

    return AgentmuxConfig(
        default_provider=raw.get("default_provider", "claude"),
        working_dir=raw.get("working_dir", os.getcwd()),
        providers=raw.get("providers", {}),
        aliases=raw.get("aliases", {}),
    )
