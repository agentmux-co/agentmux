"""DSL router — parse prefix commands into structured actions."""

from __future__ import annotations

import re

from agentmux.models import AgentmuxConfig, ParsedCommand, RouteAction, SessionMode

_ROUTE_PATTERN = re.compile(
    r"^(?P<provider>\w+):(?P<rest>.*)$",
    re.DOTALL,
)


def parse(message: str, config: AgentmuxConfig) -> ParsedCommand:
    """Parse a DSL message into a ParsedCommand."""
    message = message.strip()

    match = _ROUTE_PATTERN.match(message)
    if not match:
        return ParsedCommand(
            provider=config.default_provider,
            action=RouteAction.EXECUTE,
            mode=SessionMode.BACKGROUND,
            prompt=message,
        )

    raw_provider = match.group("provider").lower()
    rest = match.group("rest").strip()

    provider = config.aliases.get(raw_provider, raw_provider)

    if not rest or rest == "status":
        if not rest:
            return ParsedCommand(
                provider=provider,
                action=RouteAction.EXECUTE,
                mode=SessionMode.BACKGROUND,
                prompt="",
            )
        return ParsedCommand(provider=provider, action=RouteAction.STATUS)

    if rest.startswith("kill "):
        session_id = rest[5:].strip()
        return ParsedCommand(
            provider=provider,
            action=RouteAction.KILL,
            session_id=session_id,
        )
    if rest == "kill":
        return ParsedCommand(provider=provider, action=RouteAction.KILL)

    if rest.startswith("front ") or rest.startswith("fg "):
        prompt = rest.split(" ", 1)[1].strip() if " " in rest else ""
        return ParsedCommand(
            provider=provider,
            action=RouteAction.EXECUTE,
            mode=SessionMode.FOREGROUND,
            prompt=prompt,
        )

    if rest.startswith("bg "):
        prompt = rest[3:].strip()
        return ParsedCommand(
            provider=provider,
            action=RouteAction.EXECUTE,
            mode=SessionMode.BACKGROUND,
            prompt=prompt,
        )

    return ParsedCommand(
        provider=provider,
        action=RouteAction.EXECUTE,
        mode=SessionMode.BACKGROUND,
        prompt=rest,
    )
