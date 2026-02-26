"""Tests for the stream parser."""

import json

from agentmux.stream_parser import parse_line


class TestTextDelta:
    def test_stream_event_text_delta(self):
        line = json.dumps({
            "type": "stream_event",
            "event": {"delta": {"text": "Hello world"}},
        })
        event = parse_line(line)
        assert event is not None
        assert event.type == "text_delta"
        assert event.text == "Hello world"
        assert not event.is_final

    def test_stream_event_empty_delta(self):
        line = json.dumps({
            "type": "stream_event",
            "event": {"delta": {}},
        })
        event = parse_line(line)
        assert event is not None
        assert event.type == "text_delta"
        assert event.text == ""


class TestInit:
    def test_init_event(self):
        line = json.dumps({"type": "init", "session_id": "abc123"})
        event = parse_line(line)
        assert event is not None
        assert event.type == "init"
        assert event.text == "abc123"


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


class TestMessage:
    def test_message_with_text_content(self):
        line = json.dumps({
            "type": "message",
            "content": [{"type": "text", "text": "Hello"}],
        })
        event = parse_line(line)
        assert event is not None
        assert event.type == "message"
        assert event.text == "Hello"

    def test_message_multiple_text_blocks(self):
        line = json.dumps({
            "type": "message",
            "content": [
                {"type": "text", "text": "Hello "},
                {"type": "text", "text": "world"},
            ],
        })
        event = parse_line(line)
        assert event is not None
        assert event.text == "Hello world"


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
