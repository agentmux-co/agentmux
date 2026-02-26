"""Parse Claude Code stream-json NDJSON output into StreamEvents."""

from __future__ import annotations

import json

from agentmux.models import StreamEvent


def parse_line(line: str) -> StreamEvent | None:
    """Parse a single NDJSON line into a StreamEvent.

    Returns None for empty or unparseable lines.
    """
    line = line.strip()
    if not line:
        return None

    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    event_type = data.get("type", "unknown")

    if event_type == "stream_event":
        # Text delta from streaming
        text = ""
        inner = data.get("event", {})
        if isinstance(inner, dict):
            delta = inner.get("delta", {})
            if isinstance(delta, dict):
                text = delta.get("text", "")
        return StreamEvent(type="text_delta", raw=data, text=text)

    if event_type == "message":
        # Full message content
        text = ""
        content = data.get("content", [])
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text += block.get("text", "")
        return StreamEvent(type="message", raw=data, text=text)

    if event_type == "result":
        text = ""
        result = data.get("result", "")
        if isinstance(result, str):
            text = result
        elif isinstance(result, dict):
            text = result.get("text", "")
        return StreamEvent(type="result", raw=data, text=text, is_final=True)

    if event_type == "init":
        session_id = data.get("session_id", "")
        return StreamEvent(type="init", raw=data, text=str(session_id))

    if event_type in ("tool_use", "tool_result"):
        return StreamEvent(type=event_type, raw=data)

    return StreamEvent(type=event_type, raw=data)
