"""Abstract base provider for AI coding agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from agentmux.models import StreamEvent


class BaseProvider(ABC):
    """Base class for agent providers."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    @abstractmethod
    def execute(
        self,
        prompt: str,
        working_dir: str,
        conversation_id: str = "",
    ) -> AsyncIterator[StreamEvent]:
        """Execute a prompt and yield stream events.

        Returns an async iterator of StreamEvents. The provider must manage
        the subprocess lifecycle internally.
        """
        ...

    @abstractmethod
    async def cancel(self, pid: int) -> None:
        """Cancel a running agent process by PID."""
        ...
