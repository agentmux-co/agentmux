"""CLI entry point for agentmux."""

from __future__ import annotations

import asyncio
import contextlib
import sys

import click
from rich.box import SIMPLE
from rich.console import Console
from rich.table import Table

from agentmux.config import load_config
from agentmux.formatters.plain import format_session_list
from agentmux.models import RouteAction, Session, SessionStatus
from agentmux.router import parse
from agentmux.session_manager import SessionManager

# stderr console for spinners, status messages, prompts
_err_console = Console(stderr=True)
# stdout console for Claude's "Claude:" prefix header
_out_console = Console()

_QUIT_COMMANDS = frozenset({":q", "quit", "exit"})


def _read_user_input(session_id: str) -> str:
    """Read user input with session ID prompt and backslash multiline support.

    - Prompt: [abcd]>
    - Trailing backslash continues on next line with `  ... ` prompt
    - Empty input re-prompts
    - Raises EOFError on Ctrl-D
    """
    short_id = session_id[:4]
    prompt = f"[{short_id}]> "
    continuation = "  ... "

    while True:
        parts: list[str] = []
        current_prompt = prompt

        while True:
            line = input(current_prompt)
            if line.endswith("\\"):
                parts.append(line[:-1])
                current_prompt = continuation
            else:
                parts.append(line)
                break

        text = "\n".join(parts).strip()
        if text:
            return text


async def _handle_session_command(
    cmd_text: str,
    manager: SessionManager,
    session: Session,
) -> bool:
    """Handle claude: prefixed in-session commands.

    Returns True if the command was handled, False if it should be sent to the agent.
    """
    if not cmd_text.startswith("claude:"):
        return False

    body = cmd_text[len("claude:") :].strip()
    parts = body.split(None, 1)
    command = parts[0] if parts else ""

    if command == "status":
        summaries = manager.get_status()
        if not summaries:
            _err_console.print("[dim]No active sessions.[/dim]")
        else:
            table = Table(box=SIMPLE)
            table.add_column("ID", style="cyan")
            table.add_column("Provider")
            table.add_column("Status")
            table.add_column("Mode")
            table.add_column("Prompt")
            for s in summaries:
                table.add_row(
                    s.id, s.provider, s.status.value, s.mode.value, s.prompt_preview
                )
            _err_console.print(table)
        return True

    if command == "kill":
        target_id = parts[1].strip() if len(parts) > 1 else ""
        if not target_id:
            _err_console.print("[red]Usage: claude:kill <session-id>[/red]")
            return True
        try:
            await manager.kill(target_id)
            _err_console.print(f"[green]Session {target_id} killed.[/green]")
        except KeyError:
            _err_console.print(f"[red]Session {target_id!r} not found.[/red]")
        return True

    if command == "help":
        _err_console.print()
        _err_console.print("[bold]In-session commands:[/bold]")
        _err_console.print("  [cyan]claude:status[/cyan]  — list all sessions")
        _err_console.print("  [cyan]claude:kill ID[/cyan] — kill a session by ID")
        _err_console.print("  [cyan]claude:help[/cyan]    — show this help")
        _err_console.print()
        _err_console.print("[bold]Quit:[/bold]")
        _err_console.print("  [cyan]:q[/cyan] / [cyan]quit[/cyan] / [cyan]exit[/cyan] — quit with confirmation")
        _err_console.print()
        _err_console.print("[dim]Tip: use \\\\ at end of line for multiline input.[/dim]")
        _err_console.print("[dim]Ctrl-C during thinking kills the session.[/dim]")
        _err_console.print()
        return True

    # Unknown claude: command — send to agent as-is
    return False


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
@click.option("--dry-run", is_flag=True, help="Parse only, do not execute.")
def route(message: str, working_dir: str, config_path: str | None, dry_run: bool) -> None:
    """Route a message to an agent and execute it."""
    config = load_config(config_path)
    cmd = parse(message, config)

    if dry_run:
        click.echo(f"Provider: {cmd.provider}")
        click.echo(f"Action:   {cmd.action.value}")
        click.echo(f"Mode:     {cmd.mode.value}")
        if cmd.prompt:
            click.echo(f"Prompt:   {cmd.prompt}")
        if cmd.session_id:
            click.echo(f"Session:  {cmd.session_id}")
        return

    manager = SessionManager(config)

    if cmd.action == RouteAction.STATUS:
        summaries = manager.get_status()
        click.echo(format_session_list(summaries))
        return

    if cmd.action == RouteAction.KILL:
        if not cmd.session_id:
            _err_console.print("[red]Error: session ID required. Usage: provider:kill <id>[/red]")
            raise SystemExit(1)
        asyncio.run(manager.kill(cmd.session_id))
        _err_console.print(f"[green]Session {cmd.session_id} killed.[/green]")
        return

    if cmd.action != RouteAction.EXECUTE:
        _err_console.print(f"[red]Unknown action: {cmd.action}[/red]")
        raise SystemExit(1)

    if not cmd.prompt:
        _err_console.print("[red]Error: no prompt provided.[/red]")
        raise SystemExit(1)

    async def _run() -> None:
        session = await manager.create(
            provider_name=cmd.provider,
            prompt=cmd.prompt,
            mode=cmd.mode,
            working_dir=working_dir or config.working_dir,
        )
        _err_console.print(
            f"[dim]Session[/dim] [cyan]{session.id}[/cyan] "
            f"[dim]started ({cmd.provider})[/dim]\n"
        )

        _CONTENT_TYPES = {"assistant", "text_delta"}
        _sentinel = object()
        interactive = sys.stdin.isatty()

        try:
            while True:
                printed_prefix = False
                first_text = True

                # Bridge stream events to a queue for concurrent waiting
                event_queue: asyncio.Queue[object] = asyncio.Queue()

                async def _pump_stream() -> None:
                    async for ev in manager.stream(session.id):
                        await event_queue.put(ev)
                    await event_queue.put(_sentinel)

                pump_task = asyncio.create_task(_pump_stream())

                # Interactive: static status + prompt for commands
                # Non-interactive: animated spinner (no one types)
                spinner = None
                input_task: asyncio.Task[str] | None = None

                if interactive:
                    _err_console.print(
                        "[dim]⠿ Claude is thinking...[/dim]"
                    )
                    input_task = asyncio.create_task(
                        asyncio.to_thread(_read_user_input, session.id)
                    )
                else:
                    spinner = _err_console.status(
                        "Claude is thinking...", spinner="dots"
                    )
                    spinner.start()

                try:
                    while True:
                        waiters: list[asyncio.Task[object]] = [
                            asyncio.create_task(event_queue.get())
                        ]
                        if input_task and not input_task.done():
                            waiters.append(input_task)  # type: ignore[arg-type]

                        done, _ = await asyncio.wait(
                            waiters, return_when=asyncio.FIRST_COMPLETED,
                        )

                        # Cancel un-finished queue.get() tasks (not input_task)
                        for t in waiters:
                            if t not in done and t is not input_task:
                                t.cancel()

                        for t in done:
                            if t is input_task:
                                try:
                                    user_cmd = t.result()
                                except EOFError:
                                    raise
                                except Exception:
                                    input_task = asyncio.create_task(
                                        asyncio.to_thread(
                                            _read_user_input, session.id
                                        )
                                    )
                                    continue

                                if await _handle_session_command(
                                    user_cmd, manager, session
                                ):
                                    input_task = asyncio.create_task(
                                        asyncio.to_thread(
                                            _read_user_input, session.id
                                        )
                                    )
                                else:
                                    # Not a recognized command during thinking
                                    _err_console.print(
                                        "[dim]Waiting for Claude...[/dim]"
                                    )
                                    input_task = asyncio.create_task(
                                        asyncio.to_thread(
                                            _read_user_input, session.id
                                        )
                                    )
                                continue

                            # Stream event
                            result = t.result()
                            if result is _sentinel:
                                break

                            event = result  # StreamEvent

                            if event.type == "tool_use" and not printed_prefix:
                                tool_name = ""
                                raw = event.raw
                                if isinstance(raw, dict):
                                    tool_name = raw.get("name", "")
                                    if not tool_name:
                                        tool_obj = raw.get("tool")
                                        if isinstance(tool_obj, dict):
                                            tool_name = tool_obj.get(
                                                "name", ""
                                            )
                                label = f" {tool_name}" if tool_name else ""
                                if spinner:
                                    spinner.update(
                                        f"Claude is using{label}..."
                                    )

                            elif (
                                event.type == "tool_result"
                                and not printed_prefix
                            ):
                                if spinner:
                                    spinner.update("Claude is thinking...")

                            elif event.text and event.type in _CONTENT_TYPES:
                                if not printed_prefix:
                                    if spinner:
                                        spinner.stop()
                                    # Newline to separate from concurrent
                                    # prompt (if any)
                                    sys.stdout.write("\n")
                                    _out_console.print(
                                        "[bold cyan]Claude:[/bold cyan]"
                                    )
                                    printed_prefix = True
                                if first_text:
                                    text = event.text.lstrip("\n")
                                    if text:
                                        sys.stdout.write("\n" + text)
                                    first_text = False
                                else:
                                    sys.stdout.write(event.text)
                                sys.stdout.flush()
                        else:
                            continue
                        break  # sentinel received
                finally:
                    if spinner:
                        spinner.stop()
                    pump_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await pump_task

                final = manager.get_session(session.id)
                end_status = final.status if final else SessionStatus.FAILED

                if end_status == SessionStatus.WAITING:
                    sys.stdout.write("\n\n")
                    sys.stdout.flush()
                    while True:
                        try:
                            user_input = await asyncio.to_thread(
                                _read_user_input, session.id
                            )
                        except EOFError:
                            raise

                        if user_input.lower() in _QUIT_COMMANDS:
                            try:
                                answer = await asyncio.to_thread(
                                    input, "Quit agentmux? [y/N]: "
                                )
                                if answer.strip().lower() == "y":
                                    await manager.kill(session.id)
                                    _err_console.print(
                                        f"[green]Session {session.id}"
                                        f" killed.[/green]"
                                    )
                                    return
                            except (EOFError, KeyboardInterrupt):
                                _err_console.print("\n[dim]Interrupted.[/dim]")
                                return
                            continue

                        if await _handle_session_command(
                            user_input, manager, session
                        ):
                            continue
                        break
                    await manager.send_input(session.id, user_input)
                    continue

                if end_status == SessionStatus.COMPLETED:
                    _err_console.print(
                        f"\n[dim]Session[/dim] [cyan]{session.id}[/cyan]"
                        f" [green]completed.[/green]"
                    )
                    break

                _err_console.print(
                    f"\n[dim]Session[/dim] [cyan]{session.id}[/cyan] "
                    f"[red]ended ({end_status.value}).[/red]"
                )
                raise SystemExit(1)
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):
                await manager.kill(session.id)
            raise

    try:
        asyncio.run(_run())
    except (KeyboardInterrupt, EOFError):
        _err_console.print("\n[dim]Interrupted.[/dim]")
        raise SystemExit(130)


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
        _err_console.print(f"[green]Session {session_id} killed.[/green]")
    except KeyError as e:
        _err_console.print(f"[red]{e}[/red]")
        raise SystemExit(1) from None
