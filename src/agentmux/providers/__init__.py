"""Provider registry for agentmux."""

from __future__ import annotations

from typing import Any

from agentmux.providers.base import BaseProvider
from agentmux.providers.claude_code import ClaudeCodeProvider

_REGISTRY: dict[str, type[BaseProvider]] = {
    "claude": ClaudeCodeProvider,
}


def get_provider(name: str, config: dict[str, Any] | None = None) -> BaseProvider:
    """Get a provider instance by name."""
    provider_cls = _REGISTRY.get(name)
    if provider_cls is None:
        raise ValueError(f"Unknown provider: {name!r}. Available: {list(_REGISTRY.keys())}")
    return provider_cls(config=config or {})
