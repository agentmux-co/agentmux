"""Claude Code provider — runs `claude` CLI as a subprocess."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import AsyncIterator
from typing import Any

from agentmux.models import StreamEvent
from agentmux.providers.base import BaseProvider
from agentmux.stream_parser import parse_line


class ClaudeCodeProvider(BaseProvider):
    """Provider that shells out to the Claude Code CLI."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.command: str = self.config.get("command", "claude")
        self.skip_permissions: bool = self.config.get("skip_permissions", False)

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        conversation_id: str = "",
    ) -> AsyncIterator[StreamEvent]:
        """Run claude CLI and yield parsed stream events."""
        args = [self.command, "-p", prompt, "--output-format", "stream-json", "--verbose"]

        if self.skip_permissions:
            args.append("--dangerously-skip-permissions")

        if conversation_id:
            args.extend(["--resume", conversation_id])

        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )

        self._last_pid = process.pid

        assert process.stdout is not None
        async for raw_line in process.stdout:
            line = raw_line.decode("utf-8", errors="replace")
            event = parse_line(line)
            if event is not None:
                yield event

        await process.wait()

    @property
    def last_pid(self) -> int | None:
        return getattr(self, "_last_pid", None)

    async def cancel(self, pid: int) -> None:
        """Send SIGTERM to the claude process."""
        try:
            import os

            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
