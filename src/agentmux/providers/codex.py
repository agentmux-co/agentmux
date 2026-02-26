"""Codex CLI provider — runs OpenAI's Codex CLI as a subprocess."""

from __future__ import annotations

import asyncio
import json
import signal
from collections.abc import AsyncIterator
from typing import Any

from agentmux.models import StreamEvent
from agentmux.providers.base import BaseProvider


class CodexProvider(BaseProvider):
    """Provider that shells out to the Codex CLI."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.command: str = self.config.get("command", "codex")
        self.approval_mode: str = self.config.get("approval_mode", "auto-edit")

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        conversation_id: str = "",
    ) -> AsyncIterator[StreamEvent]:
        """Run codex CLI and yield parsed stream events."""
        args = [
            self.command,
            "--approval-mode", self.approval_mode,
            "--quiet",
            prompt,
        ]

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )

        self._last_pid = process.pid

        assert process.stdout is not None
        buffer = ""
        async for raw_line in process.stdout:
            line = raw_line.decode("utf-8", errors="replace")
            buffer += line

            # Try to parse as JSON (codex may output structured data)
            stripped = line.strip()
            if stripped:
                try:
                    data = json.loads(stripped)
                    event_type = data.get("type", "text_delta")
                    yield StreamEvent(
                        type=event_type,
                        raw=data,
                        text=data.get("text", data.get("content", stripped)),
                    )
                    continue
                except json.JSONDecodeError:
                    pass

                # Plain text output
                yield StreamEvent(
                    type="text_delta",
                    raw={},
                    text=stripped,
                )

        await process.wait()
        yield StreamEvent(type="result", text=buffer[-500:] if buffer else "", is_final=True)

    @property
    def last_pid(self) -> int | None:
        return getattr(self, "_last_pid", None)

    async def cancel(self, pid: int) -> None:
        """Send SIGTERM to the codex process."""
        try:
            import os

            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
