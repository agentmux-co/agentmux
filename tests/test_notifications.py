"""Tests for session notifications and question timeout."""

import asyncio

import pytest

from agentmux.models import AgentmuxConfig, Notification, NotificationType
from agentmux.session_manager import SessionManager


def _config(**overrides):
    defaults = {
        "default_provider": "claude",
        "providers": {"claude": {"command": "echo"}},
        "question_timeout": 300.0,
    }
    defaults.update(overrides)
    return AgentmuxConfig(**defaults)


class TestNotificationCallbacks:
    @pytest.mark.asyncio
    async def test_on_notify_registers_callback(self):
        manager = SessionManager(_config())
        received: list[Notification] = []

        async def callback(n: Notification) -> None:
            received.append(n)

        manager.on_notify(callback)
        assert len(manager._listeners) == 1

    @pytest.mark.asyncio
    async def test_emit_calls_listeners(self):
        manager = SessionManager(_config())
        received: list[Notification] = []

        async def callback(n: Notification) -> None:
            received.append(n)

        manager.on_notify(callback)
        notification = Notification(
            type=NotificationType.SESSION_COMPLETED,
            session_id="test",
            message="done",
        )
        await manager._emit(notification)
        assert len(received) == 1
        assert received[0].type == NotificationType.SESSION_COMPLETED

    @pytest.mark.asyncio
    async def test_emit_handles_listener_errors(self):
        manager = SessionManager(_config())

        async def bad_callback(n: Notification) -> None:
            raise RuntimeError("boom")

        received: list[Notification] = []

        async def good_callback(n: Notification) -> None:
            received.append(n)

        manager.on_notify(bad_callback)
        manager.on_notify(good_callback)

        notification = Notification(
            type=NotificationType.SESSION_STARTED,
            session_id="test",
            message="start",
        )
        await manager._emit(notification)
        # Good callback still gets called despite bad callback error
        assert len(received) == 1


class TestNotificationQueue:
    @pytest.mark.asyncio
    async def test_get_notifications_queue(self):
        manager = SessionManager(_config())
        queue = manager.get_notifications_queue()

        notification = Notification(
            type=NotificationType.SESSION_FAILED,
            session_id="x1y2",
            message="failed",
        )
        await manager._emit(notification)

        result = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert result.type == NotificationType.SESSION_FAILED
        assert result.session_id == "x1y2"


class TestQuestionTimeout:
    @pytest.mark.asyncio
    async def test_cancel_question_timeout(self):
        manager = SessionManager(_config(question_timeout=10.0))
        manager._start_question_timeout("fake")
        assert "fake" in manager._timeout_tasks

        manager._cancel_question_timeout("fake")
        assert "fake" not in manager._timeout_tasks

    @pytest.mark.asyncio
    async def test_timeout_disabled_when_zero(self):
        manager = SessionManager(_config(question_timeout=0))
        manager._start_question_timeout("fake")
        assert "fake" not in manager._timeout_tasks

    @pytest.mark.asyncio
    async def test_send_input_cancels_timeout(self):
        manager = SessionManager(_config(question_timeout=10.0))
        from agentmux.models import Session, SessionStatus

        session = Session(id="abcd", provider="claude", prompt="test")
        session.status = SessionStatus.WAITING
        manager._sessions["abcd"] = session
        manager._queues["abcd"] = asyncio.Queue()

        manager._start_question_timeout("abcd")
        assert "abcd" in manager._timeout_tasks

        await manager.send_input("abcd", "yes")
        assert "abcd" not in manager._timeout_tasks

        # Clean up the spawned task to avoid hanging
        import contextlib

        task = manager._tasks.get("abcd")
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
