"""Data models for agentmux."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class SessionMode(StrEnum):
    FOREGROUND = "fg"
    BACKGROUND = "bg"


class SessionStatus(StrEnum):
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RouteAction(StrEnum):
    EXECUTE = "execute"
    STATUS = "status"
    KILL = "kill"
    FOREGROUND = "foreground"
    BACKGROUND = "background"


@dataclass
class ParsedCommand:
    """Result of DSL parsing."""

    provider: str
    action: RouteAction = RouteAction.EXECUTE
    mode: SessionMode = SessionMode.BACKGROUND
    prompt: str = ""
    session_id: str = ""


@dataclass
class Session:
    """An active agent session."""

    id: str
    provider: str
    prompt: str
    mode: SessionMode = SessionMode.BACKGROUND
    status: SessionStatus = SessionStatus.RUNNING
    output_lines: list[str] = field(default_factory=list)
    conversation_id: str = ""
    pid: int | None = None
    created_at: float = field(default_factory=time.time)
    working_dir: str = field(default_factory=lambda: os.getcwd())


@dataclass
class StreamEvent:
    """A parsed event from stream-json output."""

    type: str
    raw: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    is_final: bool = False


@dataclass
class SessionSummary:
    """Lightweight session listing format."""

    id: str
    provider: str
    status: SessionStatus
    mode: SessionMode
    prompt_preview: str
    created_at: float


@dataclass
class AgentmuxConfig:
    """Top-level configuration."""

    default_provider: str = "claude"
    working_dir: str = field(default_factory=lambda: os.getcwd())
    providers: dict[str, dict[str, Any]] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
