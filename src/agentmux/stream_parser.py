"""Parse Claude Code stream-json NDJSON output into StreamEvents."""

from __future__ import annotations

import json

from agentmux.models import StreamEvent


def parse_line(line: str) -> StreamEvent | None:
    """Parse a single NDJSON line into a StreamEvent.

    Returns None for empty or unparseable lines.

    Claude Code stream-json format (with --verbose):
      {"type":"system","subtype":"init","session_id":"...","tools":[...]}
      {"type":"assistant","message":{"content":[{"type":"text","text":"..."}]}}
      {"type":"result","subtype":"success","result":"...","is_error":false}
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

    # System init event: {"type":"system","subtype":"init","session_id":"..."}
    if event_type == "system" and data.get("subtype") == "init":
        session_id = data.get("session_id", "")
        return StreamEvent(type="init", raw=data, text=str(session_id))

    # Assistant message: {"type":"assistant","message":{"content":[{"type":"text","text":"..."}]}}
    if event_type == "assistant":
        text = ""
        message = data.get("message", {})
        if isinstance(message, dict):
            content = message.get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text += block.get("text", "")
        return StreamEvent(type="assistant", raw=data, text=text)

    # Content block delta (streaming): {"type":"content_block_delta","delta":{"text":"..."}}
    if event_type == "content_block_delta":
        text = ""
        delta = data.get("delta", {})
        if isinstance(delta, dict):
            text = delta.get("text", "")
        return StreamEvent(type="text_delta", raw=data, text=text)

    # Result event: {"type":"result","result":"...","is_error":false}
    if event_type == "result":
        text = ""
        result = data.get("result", "")
        if isinstance(result, str):
            text = result
        elif isinstance(result, dict):
            text = result.get("text", "")
        return StreamEvent(type="result", raw=data, text=text, is_final=True)

    # Tool use / tool result
    if event_type in ("tool_use", "tool_result"):
        return StreamEvent(type=event_type, raw=data)

    # Skip non-content events (rate_limit_event, etc.)
    return StreamEvent(type=event_type, raw=data)
