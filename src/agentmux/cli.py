"""CLI entry point for agentmux."""

from __future__ import annotations

import asyncio

import click

from agentmux.config import load_config
from agentmux.formatters.plain import format_session_list
from agentmux.router import parse
from agentmux.session_manager import SessionManager


@click.group()
@click.version_option(package_name="agentmux")
def main() -> None:
    """agentmux — MCP server multiplexing AI coding agents."""


@main.command()
@click.option("--config", "config_path", default=None, help="Path to config file.")
def serve(config_path: str | None) -> None:
    """Start the agentmux MCP server (stdio transport)."""
    from agentmux.server import serve as _serve

    _serve(config_path)


@main.command()
@click.argument("message")
@click.option("--working-dir", default="", help="Working directory for the agent.")
@click.option("--config", "config_path", default=None, help="Path to config file.")
def route(message: str, working_dir: str, config_path: str | None) -> None:
    """Route a message to an agent (standalone mode)."""
    config = load_config(config_path)
    cmd = parse(message, config)
    click.echo(f"Provider: {cmd.provider}")
    click.echo(f"Action:   {cmd.action.value}")
    click.echo(f"Mode:     {cmd.mode.value}")
    if cmd.prompt:
        click.echo(f"Prompt:   {cmd.prompt}")
    if cmd.session_id:
        click.echo(f"Session:  {cmd.session_id}")


@main.command()
@click.option("--config", "config_path", default=None, help="Path to config file.")
def sessions(config_path: str | None) -> None:
    """List active sessions."""
    config = load_config(config_path)
    manager = SessionManager(config)
    summaries = manager.get_status()
    click.echo(format_session_list(summaries))


@main.command()
@click.argument("session_id")
@click.option("--config", "config_path", default=None, help="Path to config file.")
def kill(session_id: str, config_path: str | None) -> None:
    """Kill an active session."""
    config = load_config(config_path)
    manager = SessionManager(config)

    async def _kill() -> None:
        await manager.kill(session_id)

    try:
        asyncio.run(_kill())
        click.echo(f"Session {session_id} killed.")
    except KeyError as e:
        click.echo(str(e), err=True)
        raise SystemExit(1) from None
