"""Plain text formatters for session output."""

from __future__ import annotations

from agentmux.models import Session, SessionSummary


def format_session_list(summaries: list[SessionSummary]) -> str:
    """Format session summaries as an ASCII table."""
    if not summaries:
        return "No active sessions."

    header = f"{'ID':<6} {'Provider':<10} {'Status':<12} {'Mode':<4} {'Prompt'}"
    separator = "-" * 70
    lines = [header, separator]

    for s in summaries:
        lines.append(
            f"{s.id:<6} {s.provider:<10} {s.status.value:<12} {s.mode.value:<4} {s.prompt_preview}"
        )

    return "\n".join(lines)


def format_session_output(session: Session, last_n: int = 20) -> str:
    """Format the last N lines of session output."""
    if not session.output_lines:
        return f"Session {session.id}: no output yet."

    lines = session.output_lines[-last_n:]
    header = f"Session {session.id} [{session.status.value}] — last {len(lines)} lines:"
    return header + "\n" + "\n".join(lines)
