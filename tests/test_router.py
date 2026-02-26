"""Tests for the DSL router."""

from agentmux.models import AgentmuxConfig, RouteAction, SessionMode
from agentmux.router import parse


def _config(**kwargs):
    defaults = {
        "default_provider": "claude",
        "aliases": {"cc": "claude", "c": "claude"},
    }
    defaults.update(kwargs)
    return AgentmuxConfig(**defaults)


class TestNoPrefix:
    def test_plain_message_uses_default_provider(self):
        cmd = parse("fix the bug in auth.py", _config())
        assert cmd.provider == "claude"
        assert cmd.action == RouteAction.EXECUTE
        assert cmd.mode == SessionMode.BACKGROUND
        assert cmd.prompt == "fix the bug in auth.py"

    def test_empty_message(self):
        cmd = parse("", _config())
        assert cmd.provider == "claude"
        assert cmd.prompt == ""


class TestPrefixBackground:
    def test_provider_colon_prompt(self):
        cmd = parse("claude: fix auth.py", _config())
        assert cmd.provider == "claude"
        assert cmd.action == RouteAction.EXECUTE
        assert cmd.mode == SessionMode.BACKGROUND
        assert cmd.prompt == "fix auth.py"

    def test_provider_colon_no_space(self):
        cmd = parse("claude:fix auth.py", _config())
        assert cmd.provider == "claude"
        assert cmd.prompt == "fix auth.py"


class TestPrefixForeground:
    def test_front_mode(self):
        cmd = parse("claude:front fix auth.py", _config())
        assert cmd.provider == "claude"
        assert cmd.action == RouteAction.EXECUTE
        assert cmd.mode == SessionMode.FOREGROUND
        assert cmd.prompt == "fix auth.py"

    def test_fg_mode(self):
        cmd = parse("claude:fg fix auth.py", _config())
        assert cmd.mode == SessionMode.FOREGROUND
        assert cmd.prompt == "fix auth.py"


class TestStatusAction:
    def test_status(self):
        cmd = parse("claude:status", _config())
        assert cmd.provider == "claude"
        assert cmd.action == RouteAction.STATUS


class TestKillAction:
    def test_kill_with_session_id(self):
        cmd = parse("claude:kill a1b2", _config())
        assert cmd.provider == "claude"
        assert cmd.action == RouteAction.KILL
        assert cmd.session_id == "a1b2"

    def test_kill_without_session_id(self):
        cmd = parse("claude:kill", _config())
        assert cmd.action == RouteAction.KILL
        assert cmd.session_id == ""


class TestAliases:
    def test_cc_alias(self):
        cmd = parse("cc: fix auth.py", _config())
        assert cmd.provider == "claude"
        assert cmd.prompt == "fix auth.py"

    def test_c_alias(self):
        cmd = parse("c: fix auth.py", _config())
        assert cmd.provider == "claude"
        assert cmd.prompt == "fix auth.py"

    def test_unknown_provider(self):
        cmd = parse("codex: fix auth.py", _config())
        assert cmd.provider == "codex"
        assert cmd.prompt == "fix auth.py"
