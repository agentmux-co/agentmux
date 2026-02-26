"""Tests for CLI helper functions and edge cases."""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock, patch

import pytest
from click.testing import CliRunner

from agentmux.cli import _QUIT_COMMANDS, _handle_session_command, _read_user_input, main
from agentmux.models import (
    AgentmuxConfig,
    Session,
    SessionMode,
    SessionStatus,
)
from agentmux.session_manager import SessionManager


def _config(**kwargs):
    defaults = {
        "default_provider": "claude",
        "providers": {"claude": {"command": "echo", "skip_permissions": False}},
    }
    defaults.update(kwargs)
    return AgentmuxConfig(**defaults)


# ---------------------------------------------------------------------------
# _read_user_input
# ---------------------------------------------------------------------------


class TestReadUserInputSingleLine:
    def test_returns_stripped_text(self):
        with patch("builtins.input", side_effect=["  hello world  "]):
            result = _read_user_input("a1b2c3d4")
        assert result == "hello world"

    def test_prompt_contains_short_id(self):
        """The prompt passed to input() should start with [a1b2]>."""
        calls = []

        def _capture(prompt):
            calls.append(prompt)
            return "ok"

        with patch("builtins.input", side_effect=_capture):
            _read_user_input("a1b2c3d4")
        assert calls[0] == "[a1b2]> "


class TestReadUserInputEmpty:
    def test_empty_input_reprompts(self):
        """Empty lines are skipped; the function loops until non-empty."""
        with patch("builtins.input", side_effect=["", "   ", "hello"]):
            result = _read_user_input("abcd")
        assert result == "hello"


class TestReadUserInputContinuation:
    def test_backslash_joins_lines(self):
        with patch("builtins.input", side_effect=["line one\\", "line two"]):
            result = _read_user_input("abcd")
        assert result == "line one\nline two"

    def test_multiple_continuation_lines(self):
        with patch(
            "builtins.input",
            side_effect=["first\\", "second\\", "third"],
        ):
            result = _read_user_input("abcd")
        assert result == "first\nsecond\nthird"

    def test_continuation_prompt_uses_ellipsis(self):
        """After a backslash line, the prompt switches to '  ... '."""
        prompts = []

        def _capture(prompt):
            prompts.append(prompt)
            if len(prompts) == 1:
                return "hello\\"
            return "world"

        with patch("builtins.input", side_effect=_capture):
            _read_user_input("abcd")
        assert prompts[0] == "[abcd]> "
        assert prompts[1] == "  ... "


class TestReadUserInputEOF:
    def test_eof_propagates(self):
        with patch("builtins.input", side_effect=EOFError):
            with pytest.raises(EOFError):
                _read_user_input("abcd")


# ---------------------------------------------------------------------------
# _handle_session_command
# ---------------------------------------------------------------------------


def _make_session(session_id: str = "a1b2") -> Session:
    return Session(
        id=session_id,
        provider="claude",
        prompt="fix auth.py",
        mode=SessionMode.BACKGROUND,
    )


class TestHandleSessionCommandStatus:
    @pytest.mark.asyncio
    async def test_status_empty_sessions(self, capsys):
        manager = SessionManager(_config())
        session = _make_session()
        handled = await _handle_session_command("claude:status", manager, session)
        assert handled is True
        # "No active sessions" is printed to stderr via rich console
        captured = capsys.readouterr()
        assert "No active sessions" in captured.err

    @pytest.mark.asyncio
    async def test_status_with_sessions(self, capsys):
        manager = SessionManager(_config())
        session = _make_session("f00d")
        # Manually inject a session so get_status returns it
        manager._sessions["f00d"] = session
        handled = await _handle_session_command("claude:status", manager, session)
        assert handled is True
        captured = capsys.readouterr()
        assert "f00d" in captured.err
        assert "claude" in captured.err


class TestHandleSessionCommandKill:
    @pytest.mark.asyncio
    async def test_kill_valid_session(self, capsys):
        manager = SessionManager(_config())
        session = _make_session("a1b2")
        manager._sessions["a1b2"] = session
        handled = await _handle_session_command("claude:kill a1b2", manager, session)
        assert handled is True
        captured = capsys.readouterr()
        assert "killed" in captured.err

    @pytest.mark.asyncio
    async def test_kill_no_id_prints_usage(self, capsys):
        manager = SessionManager(_config())
        session = _make_session()
        handled = await _handle_session_command("claude:kill", manager, session)
        assert handled is True
        captured = capsys.readouterr()
        assert "Usage" in captured.err

    @pytest.mark.asyncio
    async def test_kill_unknown_session(self, capsys):
        manager = SessionManager(_config())
        session = _make_session()
        handled = await _handle_session_command("claude:kill xxxx", manager, session)
        assert handled is True
        captured = capsys.readouterr()
        assert "not found" in captured.err


class TestHandleSessionCommandHelp:
    @pytest.mark.asyncio
    async def test_help_returns_true(self, capsys):
        manager = SessionManager(_config())
        session = _make_session()
        handled = await _handle_session_command("claude:help", manager, session)
        assert handled is True
        captured = capsys.readouterr()
        assert "In-session commands" in captured.err


class TestHandleSessionCommandUnknown:
    @pytest.mark.asyncio
    async def test_unknown_subcommand_returns_false(self):
        manager = SessionManager(_config())
        session = _make_session()
        handled = await _handle_session_command("claude:unknown", manager, session)
        assert handled is False

    @pytest.mark.asyncio
    async def test_not_a_command_returns_false(self):
        manager = SessionManager(_config())
        session = _make_session()
        handled = await _handle_session_command("not a command", manager, session)
        assert handled is False

    @pytest.mark.asyncio
    async def test_bare_claude_colon_returns_false(self):
        """'claude:' with nothing after the colon is an unknown command."""
        manager = SessionManager(_config())
        session = _make_session()
        handled = await _handle_session_command("claude:", manager, session)
        assert handled is False


# ---------------------------------------------------------------------------
# _QUIT_COMMANDS
# ---------------------------------------------------------------------------


class TestQuitCommands:
    def test_contains_expected_commands(self):
        assert ":q" in _QUIT_COMMANDS
        assert "quit" in _QUIT_COMMANDS
        assert "exit" in _QUIT_COMMANDS

    def test_is_frozenset(self):
        assert isinstance(_QUIT_COMMANDS, frozenset)

    def test_does_not_contain_random_string(self):
        assert "hello" not in _QUIT_COMMANDS


# ---------------------------------------------------------------------------
# Dry-run output via CliRunner
# ---------------------------------------------------------------------------


class TestDryRunRoute:
    def test_dry_run_execute(self):
        runner = CliRunner()
        result = runner.invoke(main, ["route", "--dry-run", "claude: fix auth.py"])
        assert result.exit_code == 0
        assert "Provider: claude" in result.output
        assert "Action:   execute" in result.output
        assert "Mode:     bg" in result.output
        assert "Prompt:   fix auth.py" in result.output

    def test_dry_run_status(self):
        runner = CliRunner()
        result = runner.invoke(main, ["route", "--dry-run", "claude:status"])
        assert result.exit_code == 0
        assert "Provider: claude" in result.output
        assert "Action:   status" in result.output

    def test_dry_run_kill(self):
        runner = CliRunner()
        result = runner.invoke(main, ["route", "--dry-run", "claude:kill abc1"])
        assert result.exit_code == 0
        assert "Provider: claude" in result.output
        assert "Action:   kill" in result.output
        assert "Session:  abc1" in result.output

    def test_dry_run_foreground_mode(self):
        runner = CliRunner()
        result = runner.invoke(main, ["route", "--dry-run", "claude:front fix tests"])
        assert result.exit_code == 0
        assert "Mode:     fg" in result.output
        assert "Prompt:   fix tests" in result.output
