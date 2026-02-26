# agentmux

MCP server that multiplexes between messaging channels and AI coding agents.

Route prompts from any messaging interface (Telegram, Slack, CLI) to any AI coding agent (Claude Code, Codex, Ollama) through a unified DSL, with session management, background execution, and question detection.

## Features

- **DSL Routing** — Prefix-based syntax to target agents: `claude: fix auth.py`
- **Multi-Provider** — Claude Code, Ollama, Codex built-in + custom provider registration
- **Session Management** — Background/foreground execution with 4-char hex session IDs
- **Interactive CLI** — Rich-formatted output, spinners, session-aware prompt, in-session commands
- **MCP Server** — Tools and resources via the Model Context Protocol (synchronous streaming)
- **Question Detection** — Heuristic detection with configurable timeout for unanswered questions
- **Notifications** — Async callbacks for session events (started, completed, failed, question)
- **Stream Parsing** — Real-time parsing of Claude Code's stream-json NDJSON output
- **Channel Formatters** — Plain text, Telegram HTML, and Slack mrkdwn output formatters
- **Configuration** — YAML config with env var substitution and alias support

## Installation

```bash
pip install agentmux
```

### Development

```bash
git clone https://github.com/bdiallo/agentmux.git
cd agentmux
pip install -e ".[dev]"
```

## Quick Start

### As an MCP Server

Add to your Claude Code `.mcp.json`:

```json
{
  "mcpServers": {
    "agentmux": {
      "command": "agentmux",
      "args": ["serve"]
    }
  }
}
```

The `route` tool waits for the agent to finish and returns the full response — no polling needed. When the agent asks a question, the response includes instructions to call `session_input`.

### CLI Usage

```bash
# Start the MCP server (stdio transport)
agentmux serve

# Route a message interactively
agentmux route "claude: fix auth.py"

# Dry-run (parse only, no execution)
agentmux route --dry-run "claude:front fix auth.py"

# List sessions
agentmux sessions

# Kill a session
agentmux kill a1b2
```

### DSL Examples

```
claude: fix the login bug          # background, claude provider
claude:front refactor auth.py      # foreground mode
claude:status                      # list all sessions
claude:kill a1b2                   # kill session a1b2
fix the bug                        # uses default provider
cc: fix auth.py                    # alias → claude
ollama: explain this function      # use ollama provider
codex: add error handling          # use codex provider
```

## Architecture

```
                          agentmux
 Channels              ┌────────────────────┐              Providers
 ───────               │                    │              ─────────
                       │     ┌────────┐     │
  Telegram ──────────▶ │     │ Router │     │ ──────────▶  Claude Code
                       │     └───┬────┘     │
  Slack    ──────────▶ │         │          │ ──────────▶  Ollama
                       │    ┌────▼─────┐    │
  CLI      ──────────▶ │    │ Session  │    │ ──────────▶  Codex
                       │    │ Manager  │    │
  Claude Code ───────▶ │    └────┬─────┘    │ ──────────▶  (custom)
  (as MCP client)      │         │          │
                       │  ┌──────▼───────┐  │
                       │  │Notifications │  │     Formatters
                       │  └──────────────┘  │     ──────────
                       │                    │     Plain
                       └────────────────────┘     Telegram
                                                  Slack
```

## CLI Interactive Mode

When running `agentmux route`, the CLI provides an interactive experience:

```
Session a1b2 started (claude)

⠿ Claude is thinking...

Claude:

Here is the fix for auth.py...

[a1b2]> claude:status        # check sessions while in conversation
[a1b2]> first line\          # backslash for multiline input
  ...  second line
[a1b2]> :q                   # quit (with confirmation)
```

### In-Session Commands

| Command | Description |
|---------|-------------|
| `claude:status` | List all active sessions |
| `claude:kill <id>` | Kill a session by ID |
| `claude:help` | Show available commands |
| `:q` / `quit` / `exit` | Quit with confirmation prompt |

### Behavior

- **Spinner**: "Claude is thinking..." / "Claude is using Read..." on stderr
- **Concurrent input**: Type commands while Claude is working (interactive TTY)
- **Multiline**: End a line with `\` to continue on the next line
- **Ctrl-C**: Kills the current session and exits

## Providers

| Provider | Type | Description |
|----------|------|-------------|
| `claude` | CLI subprocess | Claude Code via `claude` CLI with stream-json |
| `ollama` | HTTP API | Local Ollama instance with streaming |
| `codex` | CLI subprocess | OpenAI Codex CLI |
| Custom | `register_provider()` | Register your own at runtime |

```python
from agentmux.providers import register_provider
from agentmux.providers.base import BaseProvider
from agentmux.models import StreamEvent

class MyProvider(BaseProvider):
    async def execute(self, prompt, working_dir, conversation_id=""):
        yield StreamEvent(type="text_delta", text="Hello!")
        yield StreamEvent(type="result", text="Done", is_final=True)

    async def cancel(self, pid):
        pass

register_provider("my_agent", MyProvider)
```

## DSL Reference

| Syntax | Action | Mode | Example |
|--------|--------|------|---------|
| `provider: prompt` | Execute | Background | `claude: fix auth.py` |
| `provider:front prompt` | Execute | Foreground | `claude:front fix auth` |
| `provider:fg prompt` | Execute | Foreground | `claude:fg fix auth` |
| `provider:bg prompt` | Execute | Background | `claude:bg fix auth` |
| `provider:status` | Status | — | `claude:status` |
| `provider:kill <id>` | Kill | — | `claude:kill a1b2` |
| `prompt` (no prefix) | Execute | Background | `fix the bug` |

## Session Lifecycle

```
 ┌─────────┐   execute   ┌─────────┐   question   ┌─────────┐
 │ created │────────────▶│ running │─────────────▶│ waiting │
 └─────────┘             └────┬────┘              └────┬────┘
                              │                        │
                          completes              user answers
                              │                   (send_input)
                              ▼                        │
                         ┌─────────┐              ┌────▼────┐
                         │completed│              │ running │──▶ completes
                         └─────────┘              └─────────┘

 kill at any point ──▶ cancelled
 error at any point ──▶ failed
 question timeout ──▶ cancelled (configurable, default 5 min)
```

## Notifications

The session manager emits notifications for key events:

| Event | Trigger |
|-------|---------|
| `session_started` | New session created |
| `session_completed` | Agent finished successfully |
| `session_failed` | Agent errored |
| `session_cancelled` | Session killed or timed out |
| `question_detected` | Agent is waiting for user input |
| `question_timeout` | Unanswered question exceeded timeout |

```python
from agentmux.session_manager import SessionManager

manager = SessionManager(config)

async def on_event(notification):
    print(f"[{notification.type}] {notification.message}")

manager.on_notify(on_event)

# Or use a queue
queue = manager.get_notifications_queue()
```

## MCP Tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `route` | `message`, `working_dir` | Parse DSL, dispatch to agent, return full response |
| `session_input` | `session_id`, `user_input` | Answer an agent's question |
| `session_control` | `action`, `session_id` | Control sessions (status/kill/fg/bg) |
| `providers` | — | List available providers |

The `route` tool streams the agent's output and returns it synchronously — the caller receives the complete response (or question + instructions) in a single call.

## MCP Resources

| URI | Description |
|-----|-------------|
| `sessions://list` | List all active sessions |
| `sessions://{session_id}/output` | Get session output |

## Channel Formatters

Format output for different messaging platforms:

```python
from agentmux.formatters import plain, telegram, slack

# Plain text (CLI, logs)
plain.format_session_list(summaries)
plain.format_session_output(session)

# Telegram (HTML parse mode)
telegram.format_session_list(summaries)
telegram.format_notification(notification)

# Slack (mrkdwn)
slack.format_session_list(summaries)
slack.format_notification(notification)
```

## Configuration

Create `agentmux.yaml` or `~/.config/agentmux/config.yaml`:

```yaml
default_provider: claude
question_timeout: 300  # seconds, 0 to disable
working_dir: /home/user/projects

providers:
  claude:
    command: claude
    args: ["-p"]
    skip_permissions: true

  ollama:
    base_url: http://localhost:11434
    model: codellama

  codex:
    command: codex
    approval_mode: auto-edit

aliases:
  cc: claude
  c: claude
  ol: ollama
  cx: codex
```

Environment variables are supported with `${VAR}` and `${VAR:-default}` syntax.

## Integration Examples

### With nanobot (Telegram)

In `~/.nanobot/config.json`:

```json
{
  "mcpServers": {
    "agentmux": {
      "command": "agentmux",
      "args": ["serve"]
    }
  }
}
```

The Telegram flow: user sends message → nanobot calls `route` tool → agentmux streams the agent's response → nanobot sends it back to the user. If the agent asks a question, the response includes `session_input` instructions for the follow-up.

### With Claude Code

```json
{
  "mcpServers": {
    "agentmux": {
      "command": "agentmux",
      "args": ["serve", "--config", "/path/to/config.yaml"]
    }
  }
}
```

## Project Structure

```
src/agentmux/
├── cli.py               # CLI entry point (route, serve, sessions, kill)
├── config.py            # YAML config loading with env var substitution
├── models.py            # Data models (Session, StreamEvent, Config, etc.)
├── router.py            # DSL parser (prefix:action prompt)
├── server.py            # MCP server (tools + resources)
├── session_manager.py   # Session lifecycle, streaming, notifications
├── stream_parser.py     # Claude Code NDJSON stream parser
├── question_detector.py # Heuristic question detection
├── providers/
│   ├── base.py          # BaseProvider ABC
│   ├── claude_code.py   # Claude Code CLI provider
│   ├── ollama.py        # Ollama HTTP provider
│   └── codex.py         # Codex CLI provider
└── formatters/
    ├── plain.py         # Plain text formatter
    ├── telegram.py      # Telegram HTML formatter
    └── slack.py         # Slack mrkdwn formatter
```

## Development

```bash
git clone https://github.com/bdiallo/agentmux.git
cd agentmux
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/ tests/

# Type check
mypy src/
```

### Tests

150 tests covering all modules:

| File | Coverage |
|------|----------|
| `test_cli.py` | CLI helpers, in-session commands, multiline input, dry-run |
| `test_server.py` | MCP tools (route, session_input, session_control), resources, edge cases |
| `test_session_manager.py` | Session lifecycle, question detection, send_input |
| `test_notifications.py` | Notification callbacks and queue |
| `test_router.py` | DSL parsing, aliases, actions |
| `test_stream_parser.py` | NDJSON parsing, event types, edge cases |
| `test_question_detector.py` | Question detection heuristics |
| `test_providers.py` | Provider registry, config |
| `test_formatters.py` | Plain, Telegram, Slack output formatting |
| `test_config.py` | Config loading, env var substitution |

## License

MIT
