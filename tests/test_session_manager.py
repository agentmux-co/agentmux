"""Tests for the session manager."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import patch

import pytest

from agentmux.models import AgentmuxConfig, SessionStatus, StreamEvent
from agentmux.providers.base import BaseProvider
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


class _QuestionThenFinalProvider(BaseProvider):
    """Yields a question event then a result with is_final=True."""

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        conversation_id: str = "",
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type="assistant", text="Which approach do you prefer?")
        yield StreamEvent(type="result", text="", is_final=True)

    async def cancel(self, pid: int) -> None:
        pass


class _StreamingChunksProvider(BaseProvider):
    """Yields small text_delta chunks where no single chunk triggers detection."""

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        conversation_id: str = "",
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type="text_delta", text="Here are my questions:\n")
        yield StreamEvent(type="text_delta", text="1. **What feature do ")
        yield StreamEvent(type="text_delta", text="you want to add?**\n")
        yield StreamEvent(type="text_delta", text="Let me know.")
        yield StreamEvent(type="result", text="", is_final=True)

    async def cancel(self, pid: int) -> None:
        pass


class TestWaitingPreserved:
    @pytest.mark.asyncio
    async def test_waiting_not_overwritten_by_is_final(self):
        config = _config()
        manager = SessionManager(config)

        with patch("agentmux.session_manager.get_provider", return_value=_QuestionThenFinalProvider()):
            session = await manager.create("claude", "ask me something")
            task = manager._tasks[session.id]
            await task

        assert session.status == SessionStatus.WAITING

    @pytest.mark.asyncio
    async def test_accumulated_output_detects_question(self):
        """Streaming chunks don't individually trigger detection,
        but the accumulated output does."""
        config = _config()
        manager = SessionManager(config)

        with patch("agentmux.session_manager.get_provider", return_value=_StreamingChunksProvider()):
            session = await manager.create("claude", "ask me something")
            task = manager._tasks[session.id]
            await task

        assert session.status == SessionStatus.WAITING
