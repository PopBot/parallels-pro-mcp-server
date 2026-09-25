# Parallels Pro MCP Server

[![CI](https://github.com/PopBot/parallels-pro-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/PopBot/parallels-pro-mcp-server/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python >=3.10](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)

A Model Context Protocol (MCP) server for Parallels Desktop on macOS. It enables LLM agents—such as Claude Desktop, ChatGPT Codex, Cursor, and Antigravity—to discover, control, automate, and inspect Parallels virtual machines over standard MCP stdio.

## Highlights

- **Full Lifecycle Management**: Start, gracefully stop (ACPI), and suspend virtual machines.
- **Cross-Platform Guest Execution**: Execute commands inside Windows, Linux, or macOS guests with explicit argument vectors (`argv`), avoiding host shell injection risks.
- **Readiness Probing**: Automatically detects guest OS and polls until Parallels Tools and the guest execution layer respond.
- **Visual VM Inspection**: Capture real-time screenshots of the VM display buffer for multimodal AI analysis (`vm_screenshot`).
- **Snapshot Safety**: List, create, and safely revert snapshots with mandatory confirmation flags (`confirm: true`).
- **Pre-flight Diagnostic Doctor**: Built-in environment and license validator (`parallels-pro-mcp doctor` and `scripts/doctor.sh`).

---

## Tool Reference

| Tool | Purpose | Confirmation Required | Annotations |
|---|---|---|---|
| `vm_list` | Discover registered VMs and power states | No | Read-Only |
| `vm_status` | Inspect detailed VM status, OS, tools version, and uptime | No | Read-Only |
| `vm_start` | Start a VM by name or UUID | No | Power Change |
| `vm_stop` | Request graceful ACPI shutdown (never force-kills) | No | Destructive |
| `vm_suspend` | Suspend VM and preserve guest memory | No | Destructive |
| `vm_wait_ready` | Poll until the guest OS answers execution probes | No | Readiness |
| `vm_exec` | Run an argv vector in the guest (supports custom `user`) | No (Privileged) | Guest Command |
| `vm_screenshot` | Capture current VM screen to host PNG | No | Read-Only |
| `snapshot_list` | List all snapshots for a VM | No | Read-Only |
| `snapshot_create` | Create a snapshot with name and optional description | `confirm: true` | State Mutating |
| `snapshot_revert` | Revert VM state to a specified snapshot | `confirm: true` | State Mutating |

---

## Prerequisites

1. **macOS** with [Parallels Desktop](https://www.parallels.com/) Pro or Business Edition installed.
   - *Note*: Parallels Desktop Pro or Business is required for the `prlctl` command-line utility and `prlctl exec` guest execution.
2. **Parallels Tools** installed inside each target guest VM.
3. **Python 3.10+** and [`uv`](https://docs.astral.sh/uv/) (recommended).

### Verify Your Environment

Before connecting an MCP client, run the pre-flight diagnostic:

```bash
# Using uv:
uv run parallels-pro-mcp doctor

# Or using the standalone script:
./scripts/doctor.sh
```

---

## Client Configuration

### Claude Desktop

Add the following to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "parallels-pro": {
      "command": "uvx",
      "args": ["parallels-pro-mcp-server"],
      "env": {
        "PARALLELS_DEFAULT_VM": "Windows 11",
        "PARALLELS_ARTIFACT_DIR": "~/.cache/parallels-mcp"
      }
    }
  }
}
```

Or when running from a local checkout:

```json
{
  "mcpServers": {
    "parallels-pro": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/parallels-pro-mcp-server",
        "parallels-pro-mcp"
      ]
    }
  }
}
```

### Codex / ChatGPT Desktop

In `~/.codex/config.toml`:

```toml
[mcp_servers.parallels-pro]
command = "uv"
args = ["run", "--project", "/path/to/parallels-pro-mcp-server", "parallels-pro-mcp"]
startup_timeout_sec = 30
tool_timeout_sec = 600

[mcp_servers.parallels-pro.env]
PARALLELS_DEFAULT_VM = "Windows 11"
PARALLELS_ARTIFACT_DIR = "~/.cache/parallels-mcp"
```

### Google Antigravity (Gemini CLI)

Add the server to `~/.gemini/config/mcp_config.json`:

```json
{
  "mcpServers": {
    "parallels-pro": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/path/to/parallels-pro-mcp-server",
        "parallels-pro-mcp"
      ],
      "env": {
        "PARALLELS_DEFAULT_VM": "Windows 11",
        "PARALLELS_ARTIFACT_DIR": "~/.cache/parallels-mcp"
      }
    }
  }
}
```

Or using `uvx`:

```json
{
  "mcpServers": {
    "parallels-pro": {
      "command": "uvx",
      "args": ["parallels-pro-mcp-server"]
    }
  }
}
```

---

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `PARALLELS_DEFAULT_VM` | Fallback VM name or UUID used when a tool argument is omitted | None |
| `PARALLELS_ARTIFACT_DIR` | Host directory where captured screenshots and artifacts are stored | `~/.cache/parallels-pro-mcp-server` |

---

## Safe Operating Sequence for Agents

1. **Discover**: Call `vm_list` to see available VMs and states.
2. **Inspect**: Call `vm_status(vm="...")` to verify guest tools and power status.
3. **Power Up**: If stopped, call `vm_start` followed by `vm_wait_ready` to ensure guest tools are responsive.
4. **Inspect Desktop**: Call `vm_screenshot` to visually check if dialogs or login prompts are blocking the session.
5. **Snapshot Baseline**: Call `snapshot_create(vm="...", name="clean-baseline", confirm=true)` before performing major tasks.
6. **Execute**: Use `vm_exec` with explicit argument arrays (e.g. `["cmd", "/c", "dir"]` or `["ls", "-la"]`).

---

## Security Model

- **Automation Bridge**: This server delegates guest execution directly to `prlctl exec`.
- **Privilege & Shared Folders**: If your VM has Parallels Shared Folders enabled (e.g. `\\Mac\Home` on Windows or `/media/psf/` on Linux), guest commands can read and write to your host filesystem. Always run only on trusted virtual machines.
- **Explicit Argv Only**: `vm_exec` only accepts argument vectors (`list[str]`), preventing shell injection on the host.

---

## Development & Testing

```bash
# Clone the repository
git clone https://github.com/your-username/parallels-pro-mcp-server.git
cd parallels-pro-mcp-server

# Install dependencies and sync environment
uv sync

# Run diagnostic doctor
uv run parallels-pro-mcp doctor

# Run test suite
uv run python -m unittest discover -s tests
```

---

## License

This project is licensed under the [MIT License](LICENSE).
