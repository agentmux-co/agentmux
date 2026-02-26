"""MCP server for agentmux."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from agentmux.config import load_config
from agentmux.formatters.plain import format_session_list, format_session_output
from agentmux.models import AgentmuxConfig, RouteAction
from agentmux.router import parse
from agentmux.session_manager import SessionManager

_mcp = FastMCP("agentmux")
_manager: SessionManager | None = None
_config: AgentmuxConfig | None = None


def _get_manager() -> SessionManager:
    global _manager, _config
    if _manager is None:
        _config = load_config()
        _manager = SessionManager(_config)
    return _manager


def _get_config() -> AgentmuxConfig:
    global _config
    if _config is None:
        _config = load_config()
    return _config


@_mcp.tool()
async def route(message: str, working_dir: str = "") -> str:
    """Parse a DSL message and dispatch to the appropriate agent.

    Examples:
      - "claude: fix auth.py" → run fix auth.py with claude in background
      - "claude:front fix auth.py" → run in foreground
      - "claude:status" → list sessions
      - "fix the bug" → use default provider
    """
    config = _get_config()
    manager = _get_manager()
    cmd = parse(message, config)

    if cmd.action == RouteAction.STATUS:
        summaries = manager.get_status()
        return format_session_list(summaries)

    if cmd.action == RouteAction.KILL:
        if not cmd.session_id:
            return "Error: session ID required for kill. Usage: provider:kill <id>"
        try:
            await manager.kill(cmd.session_id)
            return f"Session {cmd.session_id} killed."
        except KeyError as e:
            return str(e)

    if cmd.action == RouteAction.EXECUTE:
        if not cmd.prompt:
            return "Error: no prompt provided."
        session = await manager.create(
            provider_name=cmd.provider,
            prompt=cmd.prompt,
            mode=cmd.mode,
            working_dir=working_dir or config.working_dir,
        )
        mode_label = "foreground" if cmd.mode.value == "fg" else "background"
        return (
            f"Session {session.id} started ({cmd.provider}, {mode_label}).\n"
            f"Prompt: {cmd.prompt[:80]}"
        )

    return f"Unknown action: {cmd.action}"


@_mcp.tool()
async def session_input(session_id: str, user_input: str) -> str:
    """Send user input to a session that is waiting for a response."""
    manager = _get_manager()
    try:
        session = await manager.send_input(session_id, user_input)
        return f"Input sent to session {session.id}. Status: {session.status.value}"
    except KeyError as e:
        return str(e)


@_mcp.tool()
async def session_control(action: str, session_id: str = "") -> str:
    """Control a session: status, kill, fg (foreground), bg (background)."""
    manager = _get_manager()

    if action == "status":
        summaries = manager.get_status()
        return format_session_list(summaries)

    if action == "kill":
        if not session_id:
            return "Error: session_id required for kill."
        try:
            await manager.kill(session_id)
            return f"Session {session_id} killed."
        except KeyError as e:
            return str(e)

    if action in ("fg", "foreground"):
        if not session_id:
            return "Error: session_id required."
        try:
            session = manager.to_foreground(session_id)
            return f"Session {session.id} switched to foreground."
        except KeyError as e:
            return str(e)

    if action in ("bg", "background"):
        if not session_id:
            return "Error: session_id required."
        try:
            session = manager.to_background(session_id)
            return f"Session {session.id} switched to background."
        except KeyError as e:
            return str(e)

    return f"Unknown action: {action!r}. Use: status, kill, fg, bg"


@_mcp.resource("sessions://list")
async def list_sessions() -> str:
    """List all active sessions."""
    manager = _get_manager()
    summaries = manager.get_status()
    return format_session_list(summaries)


@_mcp.resource("sessions://{session_id}/output")
async def session_output(session_id: str) -> str:
    """Get the output of a specific session."""
    manager = _get_manager()
    session = manager.get_session(session_id)
    if session is None:
        return f"Session {session_id!r} not found."
    return format_session_output(session)


def serve(config_path: str | None = None) -> None:
    """Initialize and run the MCP server."""
    global _manager, _config
    _config = load_config(config_path)
    _manager = SessionManager(_config)
    _mcp.run(transport="stdio")
