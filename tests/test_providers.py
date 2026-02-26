"""Tests for provider registry and individual providers."""

import pytest

from agentmux.providers import get_provider, list_providers, register_provider
from agentmux.providers.base import BaseProvider
from agentmux.providers.claude_code import ClaudeCodeProvider
from agentmux.providers.codex import CodexProvider
from agentmux.providers.ollama import OllamaProvider


class TestRegistry:
    def test_list_providers(self):
        names = list_providers()
        assert "claude" in names
        assert "ollama" in names
        assert "codex" in names

    def test_get_claude(self):
        provider = get_provider("claude")
        assert isinstance(provider, ClaudeCodeProvider)

    def test_get_ollama(self):
        provider = get_provider("ollama")
        assert isinstance(provider, OllamaProvider)

    def test_get_codex(self):
        provider = get_provider("codex")
        assert isinstance(provider, CodexProvider)

    def test_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_provider("nonexistent")

    def test_register_custom_provider(self):
        class DummyProvider(BaseProvider):
            async def execute(self, prompt, working_dir, conversation_id=""):
                yield  # pragma: no cover

            async def cancel(self, pid):
                pass  # pragma: no cover

        register_provider("dummy", DummyProvider)
        assert "dummy" in list_providers()
        provider = get_provider("dummy")
        assert isinstance(provider, DummyProvider)


class TestClaudeCodeProvider:
    def test_default_config(self):
        provider = ClaudeCodeProvider()
        assert provider.command == "claude"
        assert provider.skip_permissions is False

    def test_custom_config(self):
        provider = ClaudeCodeProvider(config={
            "command": "/usr/local/bin/claude",
            "skip_permissions": True,
        })
        assert provider.command == "/usr/local/bin/claude"
        assert provider.skip_permissions is True

    def test_last_pid_initially_none(self):
        provider = ClaudeCodeProvider()
        assert provider.last_pid is None


class TestOllamaProvider:
    def test_default_config(self):
        provider = OllamaProvider()
        assert provider.base_url == "http://localhost:11434"
        assert provider.model == "codellama"

    def test_custom_config(self):
        provider = OllamaProvider(config={
            "base_url": "http://gpu-server:11434",
            "model": "deepseek-coder",
        })
        assert provider.base_url == "http://gpu-server:11434"
        assert provider.model == "deepseek-coder"


class TestCodexProvider:
    def test_default_config(self):
        provider = CodexProvider()
        assert provider.command == "codex"
        assert provider.approval_mode == "auto-edit"

    def test_custom_config(self):
        provider = CodexProvider(config={
            "command": "/opt/codex",
            "approval_mode": "suggest",
        })
        assert provider.command == "/opt/codex"
        assert provider.approval_mode == "suggest"

    def test_last_pid_initially_none(self):
        provider = CodexProvider()
        assert provider.last_pid is None
