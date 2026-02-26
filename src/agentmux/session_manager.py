"""Session manager — orchestrates agent sessions."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import AsyncIterator

from agentmux.models import (
    AgentmuxConfig,
    Session,
    SessionMode,
    SessionStatus,
    SessionSummary,
    StreamEvent,
)
from agentmux.providers import get_provider
from agentmux.question_detector import detect_question


def _gen_id() -> str:
    """Generate a 4-character hex session ID."""
    return secrets.token_hex(2)


class SessionManager:
    """Manages the lifecycle of agent sessions."""

    def __init__(self, config: AgentmuxConfig) -> None:
        self.config = config
        self._sessions: dict[str, Session] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._queues: dict[str, asyncio.Queue[StreamEvent]] = {}

    async def create(
        self,
        provider_name: str,
        prompt: str,
        mode: SessionMode = SessionMode.BACKGROUND,
        working_dir: str = "",
    ) -> Session:
        """Create and start a new agent session."""
        session_id = _gen_id()
        while session_id in self._sessions:
            session_id = _gen_id()

        session = Session(
            id=session_id,
            provider=provider_name,
            prompt=prompt,
            mode=mode,
            working_dir=working_dir or self.config.working_dir,
        )
        self._sessions[session_id] = session
        self._queues[session_id] = asyncio.Queue()

        task = asyncio.create_task(self._run_session(session))
        self._tasks[session_id] = task

        return session

    async def _run_session(self, session: Session) -> None:
        """Run a provider and accumulate output."""
        provider_config = self.config.providers.get(session.provider, {})
        provider = get_provider(session.provider, provider_config)

        try:
            async for event in provider.execute(
                prompt=session.prompt,
                working_dir=session.working_dir,
                conversation_id=session.conversation_id,
            ):
                if hasattr(provider, "last_pid") and provider.last_pid:
                    session.pid = provider.last_pid

                if event.text:
                    session.output_lines.append(event.text)

                if event.type == "init" and event.text:
                    session.conversation_id = event.text

                queue = self._queues.get(session.id)
                if queue:
                    await queue.put(event)

                if event.text and detect_question(event.text):
                    session.status = SessionStatus.WAITING

                if event.is_final:
                    session.status = SessionStatus.COMPLETED

            if session.status == SessionStatus.RUNNING:
                session.status = SessionStatus.COMPLETED
        except asyncio.CancelledError:
            session.status = SessionStatus.CANCELLED
        except Exception:
            session.status = SessionStatus.FAILED

    async def send_input(self, session_id: str, user_input: str) -> Session:
        """Answer a question by resuming the session with new input."""
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Session {session_id!r} not found")

        session.status = SessionStatus.RUNNING
        session.prompt = user_input

        old_task = self._tasks.get(session_id)
        if old_task and not old_task.done():
            old_task.cancel()

        task = asyncio.create_task(self._run_session(session))
        self._tasks[session_id] = task

        return session

    def to_foreground(self, session_id: str) -> Session:
        """Switch a session to foreground mode."""
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Session {session_id!r} not found")
        session.mode = SessionMode.FOREGROUND
        return session

    def to_background(self, session_id: str) -> Session:
        """Switch a session to background mode."""
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Session {session_id!r} not found")
        session.mode = SessionMode.BACKGROUND
        return session

    def get_status(self) -> list[SessionSummary]:
        """List all sessions as summaries."""
        summaries = []
        for s in self._sessions.values():
            summaries.append(
                SessionSummary(
                    id=s.id,
                    provider=s.provider,
                    status=s.status,
                    mode=s.mode,
                    prompt_preview=s.prompt[:60] + ("..." if len(s.prompt) > 60 else ""),
                    created_at=s.created_at,
                )
            )
        return summaries

    async def kill(self, session_id: str) -> None:
        """Kill a session by cancelling its task and terminating the process."""
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(f"Session {session_id!r} not found")

        task = self._tasks.get(session_id)
        if task and not task.done():
            task.cancel()

        if session.pid:
            provider_config = self.config.providers.get(session.provider, {})
            provider = get_provider(session.provider, provider_config)
            await provider.cancel(session.pid)

        session.status = SessionStatus.CANCELLED

    async def stream(self, session_id: str) -> AsyncIterator[StreamEvent]:
        """Yield stream events for a session."""
        queue = self._queues.get(session_id)
        if queue is None:
            raise KeyError(f"Session {session_id!r} not found")

        session = self._sessions.get(session_id)
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.5)
                yield event
                if event.is_final:
                    break
            except TimeoutError:
                if session and session.status in (
                    SessionStatus.COMPLETED,
                    SessionStatus.FAILED,
                    SessionStatus.CANCELLED,
                ):
                    break

    def get_session(self, session_id: str) -> Session | None:
        """Get a session by ID."""
        return self._sessions.get(session_id)
