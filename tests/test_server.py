"""Tests for the MCP server tools."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from unittest.mock import patch

import pytest

from agentmux.models import AgentmuxConfig, ParsedCommand, RouteAction, SessionStatus, StreamEvent
from agentmux.providers.base import BaseProvider
from agentmux.session_manager import SessionManager

import agentmux.server as server


def _config(**overrides):
    defaults = {
        "default_provider": "claude",
        "providers": {"claude": {"command": "echo"}},
    }
    defaults.update(overrides)
    return AgentmuxConfig(**defaults)


def _install(config=None):
    """Set server globals to a fresh manager+config. Returns (manager, config)."""
    cfg = config or _config()
    mgr = SessionManager(cfg)
    server._config = cfg
    server._manager = mgr
    return mgr, cfg


# ---------------------------------------------------------------------------
# Mock providers (same pattern as test_session_manager.py)
# ---------------------------------------------------------------------------


class _CompletedProvider(BaseProvider):
    """Yields text then completes normally."""

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        conversation_id: str = "",
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type="assistant", text="Here are the projects:\n- kaalisi_api\n- kaalisi_android")
        yield StreamEvent(type="result", text="", is_final=True)

    async def cancel(self, pid: int) -> None:
        pass


class _StreamingCompletedProvider(BaseProvider):
    """Yields multiple text_delta chunks then completes."""

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        conversation_id: str = "",
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type="text_delta", text="Hello ")
        yield StreamEvent(type="text_delta", text="from ")
        yield StreamEvent(type="text_delta", text="Claude!")
        yield StreamEvent(type="result", text="", is_final=True)

    async def cancel(self, pid: int) -> None:
        pass


class _QuestionProvider(BaseProvider):
    """Yields a question then waits for input."""

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        conversation_id: str = "",
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type="assistant", text="Which database do you prefer?")
        yield StreamEvent(type="result", text="", is_final=True)

    async def cancel(self, pid: int) -> None:
        pass


class _ToolUseThenTextProvider(BaseProvider):
    """Yields tool_use, tool_result, then text — mimics a real Claude session."""

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        conversation_id: str = "",
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type="tool_use", raw={"name": "Read"})
        yield StreamEvent(type="tool_result", raw={})
        yield StreamEvent(type="assistant", text="I read the file. Here is the summary.")
        yield StreamEvent(type="result", text="", is_final=True)

    async def cancel(self, pid: int) -> None:
        pass


class _EmptyOutputProvider(BaseProvider):
    """Completes without producing any text."""

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        conversation_id: str = "",
    ) -> AsyncIterator[StreamEvent]:
        yield StreamEvent(type="result", text="", is_final=True)

    async def cancel(self, pid: int) -> None:
        pass


class _FailingProvider(BaseProvider):
    """Raises an exception during execution."""

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        conversation_id: str = "",
    ) -> AsyncIterator[StreamEvent]:
        raise RuntimeError("provider crashed")
        yield  # make it a generator  # noqa: unreachable

    async def cancel(self, pid: int) -> None:
        pass


# ---------------------------------------------------------------------------
# route() — EXECUTE action: the full Telegram path
# ---------------------------------------------------------------------------


class TestRouteExecuteCompleted:
    """route() waits for output and returns it — this is the Telegram flow."""

    @pytest.mark.asyncio
    async def test_returns_assistant_text(self):
        _install()
        with patch("agentmux.session_manager.get_provider", return_value=_CompletedProvider()):
            result = await server.route("fix the bug")
        assert "kaalisi_api" in result
        assert "kaalisi_android" in result

    @pytest.mark.asyncio
    async def test_returns_streamed_text_delta_chunks(self):
        _install()
        with patch("agentmux.session_manager.get_provider", return_value=_StreamingCompletedProvider()):
            result = await server.route("say hello")
        assert result == "Hello from Claude!"

    @pytest.mark.asyncio
    async def test_tool_use_events_excluded_from_output(self):
        _install()
        with patch("agentmux.session_manager.get_provider", return_value=_ToolUseThenTextProvider()):
            result = await server.route("read the file")
        assert "Read" not in result
        assert "I read the file" in result

    @pytest.mark.asyncio
    async def test_empty_output_completed(self):
        _install()
        with patch("agentmux.session_manager.get_provider", return_value=_EmptyOutputProvider()):
            result = await server.route("do nothing")
        assert "completed" in result
        assert "no text output" in result


class TestRouteExecuteWaiting:
    """route() returns text + session_input instructions when Claude asks a question."""

    @pytest.mark.asyncio
    async def test_waiting_returns_question_and_session_id(self):
        _install()
        with patch("agentmux.session_manager.get_provider", return_value=_QuestionProvider()):
            result = await server.route("help me decide")
        assert "Which database do you prefer?" in result
        assert "session_input" in result
        assert "waiting for your answer" in result

    @pytest.mark.asyncio
    async def test_waiting_includes_session_id_for_reply(self):
        mgr, _ = _install()
        with patch("agentmux.session_manager.get_provider", return_value=_QuestionProvider()):
            result = await server.route("help me decide")
        # The session_input instruction must contain the actual session ID
        assert "session_id='" in result
        # Extract session ID from the manager
        sessions = mgr.get_status()
        assert len(sessions) == 1
        assert sessions[0].id in result


class TestRouteExecuteFailed:

    @pytest.mark.asyncio
    async def test_failed_returns_error_status(self):
        _install()
        with patch("agentmux.session_manager.get_provider", return_value=_FailingProvider()):
            result = await server.route("crash please")
        assert "failed" in result


class TestRouteExecuteNoPrompt:

    @pytest.mark.asyncio
    async def test_empty_prompt_returns_error(self):
        _install()
        result = await server.route("")
        assert "Error" in result or "no prompt" in result


# ---------------------------------------------------------------------------
# route() — STATUS and KILL actions
# ---------------------------------------------------------------------------


class TestRouteStatus:

    @pytest.mark.asyncio
    async def test_status_empty(self):
        _install()
        result = await server.route("claude:status")
        assert "No active sessions" in result

    @pytest.mark.asyncio
    async def test_status_shows_running_session(self):
        _install()
        with patch("agentmux.session_manager.get_provider", return_value=_QuestionProvider()):
            await server.route("do something")
        result = await server.route("claude:status")
        assert "waiting" in result


class TestRouteKill:

    @pytest.mark.asyncio
    async def test_kill_missing_session_id(self):
        _install()
        result = await server.route("claude:kill")
        assert "session ID required" in result

    @pytest.mark.asyncio
    async def test_kill_unknown_session(self):
        _install()
        result = await server.route("claude:kill xxxx")
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_kill_existing_session(self):
        mgr, _ = _install()
        with patch("agentmux.session_manager.get_provider", return_value=_QuestionProvider()):
            await server.route("do something")
        sessions = mgr.get_status()
        sid = sessions[0].id
        result = await server.route(f"claude:kill {sid}")
        assert "killed" in result


# ---------------------------------------------------------------------------
# session_input() — the reply path for Telegram Q&A
# ---------------------------------------------------------------------------


class TestSessionInput:

    @pytest.mark.asyncio
    async def test_send_input_to_waiting_session(self):
        mgr, _ = _install()
        with patch("agentmux.session_manager.get_provider", return_value=_QuestionProvider()):
            route_result = await server.route("help me decide")
        sessions = mgr.get_status()
        sid = sessions[0].id
        assert mgr.get_session(sid).status == SessionStatus.WAITING

        # Now nanobot sends the user's answer via session_input
        with patch("agentmux.session_manager.get_provider", return_value=_CompletedProvider()):
            result = await server.session_input(sid, "PostgreSQL")
        assert "Input sent" in result
        assert sid in result

        # Clean up the spawned task to avoid hanging (same as test_notifications.py)
        task = mgr._tasks.get(sid)
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    @pytest.mark.asyncio
    async def test_send_input_unknown_session(self):
        _install()
        result = await server.session_input("zzzz", "hello")
        assert "not found" in result


# ---------------------------------------------------------------------------
# session_control()
# ---------------------------------------------------------------------------


class TestSessionControl:

    @pytest.mark.asyncio
    async def test_status_action(self):
        _install()
        result = await server.session_control("status")
        assert "No active sessions" in result

    @pytest.mark.asyncio
    async def test_kill_action_no_id(self):
        _install()
        result = await server.session_control("kill")
        assert "session_id required" in result

    @pytest.mark.asyncio
    async def test_kill_action_unknown(self):
        _install()
        result = await server.session_control("kill", "zzzz")
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_fg_action_no_id(self):
        _install()
        result = await server.session_control("fg")
        assert "session_id required" in result

    @pytest.mark.asyncio
    async def test_bg_action_no_id(self):
        _install()
        result = await server.session_control("bg")
        assert "session_id required" in result

    @pytest.mark.asyncio
    async def test_unknown_action(self):
        _install()
        result = await server.session_control("restart")
        assert "Unknown action" in result

    @pytest.mark.asyncio
    async def test_fg_switch(self):
        mgr, _ = _install()
        with patch("agentmux.session_manager.get_provider", return_value=_QuestionProvider()):
            await server.route("do something")
        sid = mgr.get_status()[0].id
        result = await server.session_control("foreground", sid)
        assert "foreground" in result

    @pytest.mark.asyncio
    async def test_bg_switch(self):
        mgr, _ = _install()
        with patch("agentmux.session_manager.get_provider", return_value=_QuestionProvider()):
            await server.route("do something")
        sid = mgr.get_status()[0].id
        result = await server.session_control("background", sid)
        assert "background" in result


# ---------------------------------------------------------------------------
# providers()
# ---------------------------------------------------------------------------


class TestProviders:

    @pytest.mark.asyncio
    async def test_lists_available_providers(self):
        result = await server.providers()
        assert "claude" in result


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------


class TestResources:

    @pytest.mark.asyncio
    async def test_list_sessions_empty(self):
        _install()
        result = await server.list_sessions()
        assert "No active sessions" in result

    @pytest.mark.asyncio
    async def test_session_output_not_found(self):
        _install()
        result = await server.session_output("zzzz")
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_session_output_with_data(self):
        mgr, _ = _install()
        with patch("agentmux.session_manager.get_provider", return_value=_QuestionProvider()):
            await server.route("do something")
        sid = mgr.get_status()[0].id
        result = await server.session_output(sid)
        assert sid in result
        assert "Which database" in result


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------


class TestRouteWithWorkingDir:
    """Verify that working_dir is passed through to the session."""

    @pytest.mark.asyncio
    async def test_working_dir_passed_to_session(self):
        mgr, _ = _install()
        with patch("agentmux.session_manager.get_provider", return_value=_CompletedProvider()):
            await server.route("fix bug", working_dir="/tmp/project")
        sessions = mgr.get_status()
        assert len(sessions) == 1
        sid = sessions[0].id
        session = mgr.get_session(sid)
        assert session.working_dir == "/tmp/project"


class TestRouteUnknownAction:
    """Mock parse to return an action not in (STATUS, KILL, EXECUTE)."""

    @pytest.mark.asyncio
    async def test_unknown_action_returns_error(self):
        _install()
        with patch(
            "agentmux.server.parse",
            return_value=ParsedCommand(provider="claude", action=RouteAction.FOREGROUND),
        ):
            result = await server.route("anything")
        assert "Unknown action" in result


class TestSessionControlKillExisting:
    """Kill a waiting session via session_control."""

    @pytest.mark.asyncio
    async def test_kill_waiting_session(self):
        mgr, _ = _install()
        with patch("agentmux.session_manager.get_provider", return_value=_QuestionProvider()):
            await server.route("help me decide")
        sessions = mgr.get_status()
        sid = sessions[0].id
        assert mgr.get_session(sid).status == SessionStatus.WAITING
        result = await server.session_control("kill", sid)
        assert "killed" in result


class TestSessionControlFgBgUnknown:
    """Test fg/bg with unknown session_id."""

    @pytest.mark.asyncio
    async def test_fg_unknown_session(self):
        _install()
        result = await server.session_control("fg", "zzzz")
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_bg_unknown_session(self):
        _install()
        result = await server.session_control("bg", "zzzz")
        assert "not found" in result


class TestRouteMultipleSessions:
    """Create two sessions and verify status shows both."""

    @pytest.mark.asyncio
    async def test_status_shows_both_sessions(self):
        mgr, _ = _install()
        with patch("agentmux.session_manager.get_provider", return_value=_QuestionProvider()):
            await server.route("first task")
            await server.route("second task")
        sessions = mgr.get_status()
        assert len(sessions) == 2
        result = await server.session_control("status")
        ids = [s.id for s in sessions]
        for sid in ids:
            assert sid in result


class TestSessionInputResumesAndCompletes:
    """Full Q&A loop: question -> send_input -> eventually completes."""

    @pytest.mark.asyncio
    async def test_full_qa_loop(self):
        mgr, _ = _install()
        # Step 1: create a waiting session
        with patch("agentmux.session_manager.get_provider", return_value=_QuestionProvider()):
            await server.route("help me decide")
        sessions = mgr.get_status()
        sid = sessions[0].id
        assert mgr.get_session(sid).status == SessionStatus.WAITING

        # Step 2: send input (provider returns a completed response)
        with patch("agentmux.session_manager.get_provider", return_value=_CompletedProvider()):
            result = await server.session_input(sid, "PostgreSQL")
        assert "Input sent" in result

        # Step 3: wait for the task to finish
        task = mgr._tasks.get(sid)
        if task and not task.done():
            await asyncio.wait_for(task, timeout=5.0)

        session = mgr.get_session(sid)
        assert session.status == SessionStatus.COMPLETED

        # Clean up
        task = mgr._tasks.get(sid)
        if task and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


class TestRouteWithAlias:
    """Test that aliases work through the route tool."""

    @pytest.mark.asyncio
    async def test_alias_resolves_to_provider(self):
        cfg = _config(aliases={"cc": "claude"})
        _install(config=cfg)
        with patch("agentmux.session_manager.get_provider", return_value=_CompletedProvider()):
            result = await server.route("cc: fix auth.py")
        assert "kaalisi_api" in result
        assert "kaalisi_android" in result
