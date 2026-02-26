"""Telegram Markdown formatter for session output."""

from __future__ import annotations

import html

from agentmux.models import Notification, Session, SessionSummary


def _escape(text: str) -> str:
    """Escape HTML special characters for Telegram HTML parse mode."""
    return html.escape(text)


def format_session_list(summaries: list[SessionSummary]) -> str:
    """Format session summaries for Telegram (HTML parse mode)."""
    if not summaries:
        return "<i>No active sessions.</i>"

    lines = ["<b>Sessions</b>\n"]
    for s in summaries:
        status_icon = {
            "running": "🔄",
            "waiting": "❓",
            "completed": "✅",
            "failed": "❌",
            "cancelled": "🚫",
        }.get(s.status.value, "⬜")

        mode_tag = "FG" if s.mode.value == "fg" else "BG"
        lines.append(
            f"{status_icon} <code>{s.id}</code> [{mode_tag}] "
            f"<b>{_escape(s.provider)}</b>: {_escape(s.prompt_preview)}"
        )

    return "\n".join(lines)


def format_session_output(session: Session, last_n: int = 15) -> str:
    """Format session output for Telegram."""
    if not session.output_lines:
        return f"<i>Session <code>{session.id}</code>: no output yet.</i>"

    lines = session.output_lines[-last_n:]
    header = (
        f"<b>Session <code>{session.id}</code></b> "
        f"[{session.status.value}]\n"
    )
    body = _escape("\n".join(lines))
    return f"{header}<pre>{body}</pre>"


def format_notification(notification: Notification) -> str:
    """Format a notification for Telegram."""
    icons = {
        "session_started": "🚀",
        "session_completed": "✅",
        "session_failed": "❌",
        "session_cancelled": "🚫",
        "question_detected": "❓",
        "question_timeout": "⏰",
    }
    icon = icons.get(notification.type.value, "📢")
    return f"{icon} <code>{notification.session_id}</code> {_escape(notification.message)}"
