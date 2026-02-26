"""Tests for all formatters (plain, telegram, slack)."""

from agentmux.formatters import plain, slack, telegram
from agentmux.models import (
    Notification,
    NotificationType,
    Session,
    SessionMode,
    SessionStatus,
    SessionSummary,
)


def _summaries():
    return [
        SessionSummary(
            id="a1b2",
            provider="claude",
            status=SessionStatus.RUNNING,
            mode=SessionMode.BACKGROUND,
            prompt_preview="fix auth.py",
            created_at=1000.0,
        ),
        SessionSummary(
            id="c3d4",
            provider="ollama",
            status=SessionStatus.WAITING,
            mode=SessionMode.FOREGROUND,
            prompt_preview="refactor code",
            created_at=1001.0,
        ),
    ]


def _session():
    s = Session(id="a1b2", provider="claude", prompt="fix auth.py")
    s.output_lines = ["Line 1", "Line 2", "Line 3"]
    s.status = SessionStatus.RUNNING
    return s


def _notification():
    return Notification(
        type=NotificationType.SESSION_COMPLETED,
        session_id="a1b2",
        message="Session a1b2 completed.",
    )


class TestPlainFormatter:
    def test_empty_list(self):
        assert plain.format_session_list([]) == "No active sessions."

    def test_session_list(self):
        result = plain.format_session_list(_summaries())
        assert "a1b2" in result
        assert "claude" in result
        assert "running" in result

    def test_session_output(self):
        result = plain.format_session_output(_session())
        assert "Line 1" in result
        assert "a1b2" in result

    def test_session_output_empty(self):
        s = Session(id="x1y2", provider="claude", prompt="test")
        result = plain.format_session_output(s)
        assert "no output yet" in result


class TestTelegramFormatter:
    def test_empty_list(self):
        result = telegram.format_session_list([])
        assert "No active sessions" in result

    def test_session_list_html(self):
        result = telegram.format_session_list(_summaries())
        assert "<code>a1b2</code>" in result
        assert "<b>claude</b>" in result
        assert "🔄" in result
        assert "❓" in result

    def test_session_output_html(self):
        result = telegram.format_session_output(_session())
        assert "<pre>" in result
        assert "Line 1" in result

    def test_notification(self):
        result = telegram.format_notification(_notification())
        assert "✅" in result
        assert "a1b2" in result

    def test_html_escaping(self):
        s = Session(id="x1y2", provider="claude", prompt="<script>alert(1)</script>")
        s.output_lines = ["<b>bold</b>"]
        result = telegram.format_session_output(s)
        assert "&lt;b&gt;" in result


class TestSlackFormatter:
    def test_empty_list(self):
        result = slack.format_session_list([])
        assert "No active sessions" in result

    def test_session_list_mrkdwn(self):
        result = slack.format_session_list(_summaries())
        assert "`a1b2`" in result
        assert "*claude*" in result

    def test_session_output_code_block(self):
        result = slack.format_session_output(_session())
        assert "```" in result
        assert "Line 1" in result

    def test_notification(self):
        result = slack.format_notification(_notification())
        assert ":white_check_mark:" in result
        assert "a1b2" in result
