"""Tests for the session manager."""

import pytest

from agentmux.models import AgentmuxConfig, SessionStatus
from agentmux.session_manager import SessionManager


def _config():
    return AgentmuxConfig(
        default_provider="claude",
        providers={"claude": {"command": "echo", "skip_permissions": False}},
    )


class TestInitState:
    def test_empty_on_init(self):
        manager = SessionManager(_config())
        assert manager.get_status() == []

    def test_get_session_returns_none(self):
        manager = SessionManager(_config())
        assert manager.get_session("nonexistent") is None


class TestEmptyStatus:
    def test_status_returns_empty_list(self):
        manager = SessionManager(_config())
        summaries = manager.get_status()
        assert isinstance(summaries, list)
        assert len(summaries) == 0


class TestKillNonexistent:
    @pytest.mark.asyncio
    async def test_kill_unknown_session_raises(self):
        manager = SessionManager(_config())
        with pytest.raises(KeyError, match="not found"):
            await manager.kill("xxxx")

    @pytest.mark.asyncio
    async def test_send_input_unknown_session_raises(self):
        manager = SessionManager(_config())
        with pytest.raises(KeyError, match="not found"):
            await manager.send_input("xxxx", "hello")
