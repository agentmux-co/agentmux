"""Tests for the stream parser."""

import json

from agentmux.stream_parser import parse_line


class TestSystemInit:
    def test_system_init_event(self):
        line = json.dumps({
            "type": "system",
            "subtype": "init",
            "session_id": "7bcd4845-c392-48b7-8566-8682d624c744",
            "tools": ["Bash", "Read"],
            "model": "claude-opus-4-6",
        })
        event = parse_line(line)
        assert event is not None
        assert event.type == "init"
        assert event.text == "7bcd4845-c392-48b7-8566-8682d624c744"

    def test_system_non_init_subtype(self):
        line = json.dumps({"type": "system", "subtype": "other"})
        event = parse_line(line)
        assert event is not None
        assert event.type == "system"


class TestAssistantMessage:
    def test_assistant_with_text_content(self):
        line = json.dumps({
            "type": "assistant",
            "message": {
                "content": [{"type": "text", "text": "Hello!"}],
            },
        })
        event = parse_line(line)
        assert event is not None
        assert event.type == "assistant"
        assert event.text == "Hello!"

    def test_assistant_multiple_text_blocks(self):
        line = json.dumps({
            "type": "assistant",
            "message": {
                "content": [
                    {"type": "text", "text": "Hello "},
                    {"type": "text", "text": "world"},
                ],
            },
        })
        event = parse_line(line)
        assert event is not None
        assert event.text == "Hello world"

    def test_assistant_empty_content(self):
        line = json.dumps({
            "type": "assistant",
            "message": {"content": []},
        })
        event = parse_line(line)
        assert event is not None
        assert event.type == "assistant"
        assert event.text == ""

    def test_assistant_no_message(self):
        line = json.dumps({"type": "assistant"})
        event = parse_line(line)
        assert event is not None
        assert event.text == ""


class TestContentBlockDelta:
    def test_content_block_delta_text(self):
        line = json.dumps({
            "type": "content_block_delta",
            "delta": {"text": "streaming chunk"},
        })
        event = parse_line(line)
        assert event is not None
        assert event.type == "text_delta"
        assert event.text == "streaming chunk"
        assert not event.is_final

    def test_content_block_delta_empty(self):
        line = json.dumps({
            "type": "content_block_delta",
            "delta": {},
        })
        event = parse_line(line)
        assert event is not None
        assert event.type == "text_delta"
        assert event.text == ""


class TestResult:
    def test_result_event_string(self):
        line = json.dumps({"type": "result", "result": "Done!"})
        event = parse_line(line)
        assert event is not None
        assert event.type == "result"
        assert event.text == "Done!"
        assert event.is_final

    def test_result_event_dict(self):
        line = json.dumps({"type": "result", "result": {"text": "Completed"}})
        event = parse_line(line)
        assert event is not None
        assert event.text == "Completed"
        assert event.is_final

    def test_full_result_event(self):
        line = json.dumps({
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "result": "Hello!",
            "duration_ms": 2753,
            "session_id": "abc-123",
        })
        event = parse_line(line)
        assert event is not None
        assert event.type == "result"
        assert event.text == "Hello!"
        assert event.is_final


class TestEdgeCases:
    def test_empty_line(self):
        assert parse_line("") is None
        assert parse_line("   ") is None

    def test_invalid_json(self):
        assert parse_line("not json") is None
        assert parse_line("{broken") is None

    def test_non_dict_json(self):
        assert parse_line("[1, 2, 3]") is None
        assert parse_line('"just a string"') is None

    def test_unknown_type(self):
        line = json.dumps({"type": "custom_event", "data": 42})
        event = parse_line(line)
        assert event is not None
        assert event.type == "custom_event"

    def test_tool_use(self):
        line = json.dumps({"type": "tool_use", "name": "read_file"})
        event = parse_line(line)
        assert event is not None
        assert event.type == "tool_use"

    def test_rate_limit_event_ignored(self):
        line = json.dumps({"type": "rate_limit_event", "rate_limit_info": {}})
        event = parse_line(line)
        assert event is not None
        assert event.type == "rate_limit_event"
        assert event.text == ""
