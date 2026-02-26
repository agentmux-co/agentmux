"""Slack mrkdwn formatter for session output."""

from __future__ import annotations

from agentmux.models import Notification, Session, SessionSummary


def format_session_list(summaries: list[SessionSummary]) -> str:
    """Format session summaries for Slack (mrkdwn)."""
    if not summaries:
        return "_No active sessions._"

    lines = ["*Sessions*\n"]
    for s in summaries:
        status_icon = {
            "running": ":arrows_counterclockwise:",
            "waiting": ":question:",
            "completed": ":white_check_mark:",
            "failed": ":x:",
            "cancelled": ":no_entry_sign:",
        }.get(s.status.value, ":white_square:")

        mode_tag = "FG" if s.mode.value == "fg" else "BG"
        lines.append(
            f"{status_icon} `{s.id}` [{mode_tag}] *{s.provider}*: {s.prompt_preview}"
        )

    return "\n".join(lines)


def format_session_output(session: Session, last_n: int = 15) -> str:
    """Format session output for Slack."""
    if not session.output_lines:
        return f"_Session `{session.id}`: no output yet._"

    lines = session.output_lines[-last_n:]
    header = f"*Session `{session.id}`* [{session.status.value}]\n"
    body = "\n".join(lines)
    return f"{header}```\n{body}\n```"


def format_notification(notification: Notification) -> str:
    """Format a notification for Slack."""
    icons = {
        "session_started": ":rocket:",
        "session_completed": ":white_check_mark:",
        "session_failed": ":x:",
        "session_cancelled": ":no_entry_sign:",
        "question_detected": ":question:",
        "question_timeout": ":alarm_clock:",
    }
    icon = icons.get(notification.type.value, ":loudspeaker:")
    return f"{icon} `{notification.session_id}` {notification.message}"
