# agentmux

MCP server that multiplexes between messaging channels and AI coding agents.

Route prompts from any messaging interface (Telegram, Slack, CLI) to any AI coding agent (Claude Code, Codex, Ollama) through a unified DSL, with session management, background execution, and question detection.

## Features

- **DSL Routing** — Prefix-based syntax to target agents: `claude: fix auth.py`
- **Session Management** — Background/foreground execution with 4-char hex session IDs
- **Stream Parsing** — Real-time parsing of Claude Code's stream-json output
- **Question Detection** — Heuristic detection of agent questions needing user input
- **MCP Protocol** — Expose tools and resources via the Model Context Protocol
- **Provider Architecture** — Pluggable provider system (Claude Code built-in, extensible)
- **Configuration** — YAML config with env var substitution and alias support

## Installation

```bash
pip install agentmux
```

### Development

```bash
git clone https://github.com/agentmux-co/agentmux.git
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

### CLI Usage

```bash
# Start the MCP server
agentmux serve

# Route a message (standalone)
agentmux route "claude: fix auth.py"

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
```

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌──────────────┐
│  Messaging   │     │   agentmux  │     │   Providers  │
│  Channels    │────▶│   MCP Server│────▶│              │
│              │     │             │     │  Claude Code │
│  Telegram    │     │  ┌────────┐ │     │  Codex       │
│  Slack       │     │  │ Router │ │     │  Ollama      │
│  CLI         │     │  └───┬────┘ │     │  ...         │
│  Claude Code │     │      │      │     └──────────────┘
└─────────────┘     │  ┌───▼────┐ │
                    │  │Session │ │
                    │  │Manager │ │
                    │  └────────┘ │
                    └─────────────┘
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
                             │                        │
                             ▼                        ▼
                        ┌─────────┐             ┌─────────┐
                        │completed│             │ running │
                        └─────────┘             └─────────┘

  kill at any point → cancelled
  error at any point → failed
```

## MCP Tools

| Tool | Parameters | Description |
|------|-----------|-------------|
| `route` | `message`, `working_dir` | Parse DSL and dispatch to agent |
| `session_input` | `session_id`, `user_input` | Answer an agent question |
| `session_control` | `action`, `session_id` | Control sessions (status/kill/fg/bg) |

## MCP Resources

| URI | Description |
|-----|-------------|
| `sessions://list` | List all active sessions |
| `sessions://{session_id}/output` | Get session output |

## Configuration

Create `agentmux.yaml` or `~/.config/agentmux/config.yaml`:

```yaml
default_provider: claude

providers:
  claude:
    command: claude
    args: ["-p"]
    skip_permissions: true

aliases:
  cc: claude
  c: claude
```

Environment variables are supported with `${VAR}` and `${VAR:-default}` syntax.

## Integration Examples

### With nanobot (Telegram)

```yaml
# nanobot config
tools:
  - name: agentmux
    command: agentmux serve
    transport: stdio
```

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

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src/

# Type check
mypy src/
```

## License

MIT
