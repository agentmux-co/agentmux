"""Ollama provider — uses the Ollama HTTP API for local LLM inference."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import aiohttp

from agentmux.models import StreamEvent
from agentmux.providers.base import BaseProvider


class OllamaProvider(BaseProvider):
    """Provider that connects to a local Ollama instance via HTTP API."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self.base_url: str = self.config.get("base_url", "http://localhost:11434")
        self.model: str = self.config.get("model", "codellama")
        self.system_prompt: str = self.config.get(
            "system_prompt",
            "You are a helpful coding assistant. Respond concisely.",
        )

    async def execute(
        self,
        prompt: str,
        working_dir: str,
        conversation_id: str = "",
    ) -> AsyncIterator[StreamEvent]:
        """Send a prompt to Ollama and yield streamed responses."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "system": self.system_prompt,
            "stream": True,
        }

        if conversation_id:
            import contextlib

            with contextlib.suppress(json.JSONDecodeError, TypeError):
                payload["context"] = json.loads(conversation_id)

        async with aiohttp.ClientSession() as session, session.post(url, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    yield StreamEvent(
                        type="error",
                        text=f"Ollama error ({resp.status}): {text[:200]}",
                        is_final=True,
                    )
                    return

                async for raw_line in resp.content:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if not line:
                        continue

                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    response_text = data.get("response", "")
                    done = data.get("done", False)

                    if response_text:
                        yield StreamEvent(
                            type="text_delta",
                            raw=data,
                            text=response_text,
                        )

                    if done:
                        context = data.get("context")
                        final_text = ""
                        if context:
                            final_text = json.dumps(context)
                        yield StreamEvent(
                            type="result",
                            raw=data,
                            text=final_text,
                            is_final=True,
                        )

    async def cancel(self, pid: int) -> None:
        """Ollama API doesn't use PIDs; cancellation is handled by closing the connection."""
