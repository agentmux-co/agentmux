"""Provider registry for agentmux."""

from __future__ import annotations

from typing import Any

from agentmux.providers.base import BaseProvider
from agentmux.providers.claude_code import ClaudeCodeProvider
from agentmux.providers.codex import CodexProvider
from agentmux.providers.ollama import OllamaProvider

_REGISTRY: dict[str, type[BaseProvider]] = {
    "claude": ClaudeCodeProvider,
    "ollama": OllamaProvider,
    "codex": CodexProvider,
}


def get_provider(name: str, config: dict[str, Any] | None = None) -> BaseProvider:
    """Get a provider instance by name."""
    provider_cls = _REGISTRY.get(name)
    if provider_cls is None:
        raise ValueError(f"Unknown provider: {name!r}. Available: {list(_REGISTRY.keys())}")
    return provider_cls(config=config or {})


def register_provider(name: str, provider_cls: type[BaseProvider]) -> None:
    """Register a custom provider at runtime."""
    _REGISTRY[name] = provider_cls


def list_providers() -> list[str]:
    """Return the names of all registered providers."""
    return list(_REGISTRY.keys())
