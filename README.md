# Parallels Pro MCP Server

[![CI](https://github.com/PopBot/parallels-pro-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/PopBot/parallels-pro-mcp-server/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python >=3.10](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/downloads/)

A Model Context Protocol (MCP) server for Parallels Desktop on macOS. It enables LLM agents—such as Claude Desktop, ChatGPT Codex, Cursor, and Antigravity—to discover, control, automate, and inspect Parallels virtual machines over standard MCP stdio.

[![Parallels Pro MCP Server MCP server – quality and maintenance score on Glama](https://glama.ai/mcp/servers/PopBot/parallels-pro-mcp-server/badges/card.svg)](https://glama.ai/mcp/servers/PopBot/parallels-pro-mcp-server)

## Highlights

- **Full Lifecycle Management**: Start, gracefully stop (ACPI), and suspend virtual machines.
- **Cross-Platform Guest Execution**: Execute commands inside Windows, Linux, or macOS guests with explicit argument vectors (`argv`), avoiding host shell injection risks.
- **Readiness Probing**: Automatically detects guest OS and polls until Parallels Tools and the guest execution layer respond.
- **Bi-Directional File Transfer**: Stream files and directories directly between host and guest over stdin/stdout tar archives without requiring network mounts or SMB credentials (`vm_copy_to_guest`, `vm_copy_from_guest`).
- **Dynamic Host Folder Sharing**: Mount and unmount host directories into guest VMs at runtime with read-only or read-write permissions (`vm_share_folder`, `vm_unshare_folder`).
- **Instant Sandboxing & Ephemeral Clones**: Spin up fast linked clones in seconds for disposable agent test environments, and permanently delete sandboxes with confirmation (`vm_clone`, `vm_delete`).
- **Headless Execution & Network Simulation**: Run VMs headlessly in the background, or simulate network degradation (edge, 3g, wifi, 100% packet loss, offline) for resilience testing (`vm_set_headless`, `vm_set_network_condition`).
- **Visual VM Inspection**: Capture real-time screenshots of the VM display buffer for multimodal AI analysis (`vm_screenshot`).
- **Synthetic Input & Hotkeys**: Send keyboard events and hotkey combinations (`Ctrl+Alt+Del`, `Win+R`, `Enter`, `Esc`) to interact with GUI dialogs and prompts (`vm_send_keys`).
- **Snapshot Lifecycle**: List, create, safely revert, and delete snapshots with mandatory confirmation flags (`confirm: true`).
- **Guest Automation Optimization**: Configure Windows Defender real-time scanning exclusions and set PowerShell execution policy to Bypass to eliminate `EPERM` file-locking issues during guest automation and builds (`vm_optimize_windows`).
- **Comprehensive Pre-Flight Diagnostics**: Inspect host CLI availability, Parallels Pro license tier, network adapters, and guest OS responsiveness (`vm_doctor`, `parallels-pro-mcp doctor`).
- **In-Band Release Notes & Changelog**: Inspect version updates, breaking changes, and recent features directly over MCP via the `vm_changelog` tool, the `parallels://changelog` MCP resource, or the CLI (`parallels-pro-mcp changelog`).

---

## Tool Reference

| Tool                       | Purpose                                                                   | Confirmation Required | Annotations    |
|----------------------------|---------------------------------------------------------------------------|-----------------------|----------------|
| `vm_list`                  | Discover registered VMs and power states                                  | No                    | Read-Only      |
| `vm_status`                | Inspect detailed VM status, OS, tools version, and uptime                 | No                    | Read-Only      |
| `vm_start`                 | Start a VM by name or UUID                                                | No                    | Power Change   |
| `vm_stop`                  | Request graceful ACPI shutdown (never force-kills)                        | No                    | Destructive    |
| `vm_suspend`               | Suspend VM and preserve guest memory                                      | No                    | Destructive    |
| `vm_wait_ready`            | Poll until the guest OS answers execution probes                          | No                    | Readiness      |
| `vm_exec`                  | Run an argv vector in the guest (supports custom `user`)                  | No (Privileged)       | Guest Command  |
| `vm_copy_to_guest`         | Stream files or directories from host into guest filesystem               | No                    | File Transfer  |
| `vm_copy_from_guest`       | Stream files or directories from guest onto host filesystem               | No                    | File Transfer  |
| `vm_share_folder`          | Mount a host directory into the guest (`rw` or `ro`)                      | No                    | State Mutating |
| `vm_unshare_folder`        | Remove a previously shared host directory                                 | No                    | State Mutating |
| `vm_clone`                 | Clone a VM (fast linked clone or deep copy)                               | No                    | State Mutating |
| `vm_delete`                | Permanently delete a VM and its disks                                     | `confirm: true`       | Destructive    |
| `vm_set_headless`          | Configure headless vs GUI window startup mode                             | No                    | State Mutating |
| `vm_set_network_condition` | Simulate degraded network profiles (3g, wifi, loss, off)                  | No                    | State Mutating |
| `vm_screenshot`            | Capture current VM screen to host PNG                                     | No                    | Read-Only      |
| `vm_send_keys`             | Send synthetic keystrokes or chords (e.g. `ctrl+alt+del`, `win+r`)        | No                    | Guest Command  |
| `vm_optimize_windows`      | Add Windows Defender exclusions and set PowerShell ExecutionPolicy Bypass | No                    | State Mutating |
| `vm_doctor`                | Pre-flight environment diagnostics for macOS host and guest OS            | No                    | Read-Only      |
| `vm_changelog`             | Read release notes and updates over MCP                                   | No                    | Read-Only      |
| `snapshot_list`            | List all snapshots for a VM                                               | No                    | Read-Only      |
| `snapshot_create`          | Create a snapshot with name and optional description                      | `confirm: true`       | State Mutating |
| `snapshot_revert`          | Revert VM state to a specified snapshot                                   | `confirm: true`       | State Mutating |
| `snapshot_delete`          | Permanently delete a snapshot to reclaim host disk space                  | `confirm: true`       | State Mutating |
 
---

## MCP Resources

In addition to tools, the server exposes dynamic MCP resources for context-aware agents:

| Resource URI | MIME Type | Description |
|---|---|---|
| `parallels://changelog` | `text/markdown` | Full release notes, version history, and recent updates from `CHANGELOG.md`. |

---

## Tool Usage & Cookbook

### 1. Instant Ephemeral Sandboxing
Create an isolated linked clone in seconds, run tests headlessly, and destroy it when finished:

```python
# Spin up an instant linked clone sharing the base disk
vm_clone(vm="Windows 11", name="Win11-Worker-1", linked=True)

# Run headlessly without displaying a GUI window on the desktop
vm_set_headless(vm="Win11-Worker-1", enabled=True)

# Boot and wait until guest tools are ready
vm_start(vm="Win11-Worker-1")
vm_wait_ready(vm="Win11-Worker-1", timeout_s=120)

# ... perform testing or build tasks ...

# Graceful stop and permanent teardown
vm_stop(vm="Win11-Worker-1")
vm_delete(vm="Win11-Worker-1", confirm=True)
```

### 2. Bi-Directional File Transfer
Stream files or entire directory trees between host and guest over stdin/stdout tar archives without needing network mounts or SMB credentials:

```python
# Push local build artifact into the guest Windows Temp folder
vm_copy_to_guest(
    vm="Windows 11",
    host_path="./dist/myapp.exe",
    guest_path=r"C:\Temp\myapp.exe"
)

# Pull test logs or crash dumps back onto the host
vm_copy_from_guest(
    vm="Windows 11",
    guest_path=r"C:\Temp\test-results",
    host_path="./reports/test-results"
)
```

### 3. Dynamic Host Folder Sharing
Mount local host directories directly into the VM at runtime:

```python
# Share a host repository with read-only protection
vm_share_folder(
    vm="Windows 11",
    name="source_code",
    host_path="~/projects/myapp",
    mode="ro"
)

# Unmount the share when done
vm_unshare_folder(vm="Windows 11", name="source_code")
```

### 4. GUI Interaction & Screen Analysis
Interact with native GUI dialogs, installers, or Windows UAC prompts:

```python
# Capture what is currently on the VM screen
vm_screenshot(vm="Windows 11")

# Press Win+R to open the Run dialog
vm_send_keys(vm="Windows 11", combination="win+r")

# Type a command and press Enter
vm_send_keys(vm="Windows 11", text="notepad.exe", keys=["enter"])

# Dismiss a modal with Escape
vm_send_keys(vm="Windows 11", keys=["esc"])
```

### 5. Network Simulation & Resilience Testing
Simulate poor connections or complete offline states:

```python
# Throttle bandwidth and latency to emulate a 3G mobile link
vm_set_network_condition(vm="Windows 11", profile="3g")

# Simulate a network blackout (100% packet loss)
vm_set_network_condition(vm="Windows 11", profile="100-percent-loss")

# Restore normal network conditions
vm_set_network_condition(vm="Windows 11", profile="off")
```

### 6. Snapshot Baselines
Create rollback points before mutating system state:

```python
# List snapshots
snapshot_list(vm="Windows 11")

# Create a checkpoint
snapshot_create(
    vm="Windows 11",
    name="clean-state",
    description="Clean baseline before test execution",
    confirm=True
)

# Revert back to the checkpoint
snapshot_revert(vm="Windows 11", snapshot="clean-state", confirm=True)

# Delete snapshot to reclaim host disk space
snapshot_delete(vm="Windows 11", snapshot="clean-state", confirm=True)
```

### 7. Environment Pre-Flight & Guest Health (`vm_doctor`)
Run host and guest diagnostics to verify licensing, CLI availability, and runtime readiness:

```python
# Run pre-flight health check on host and Windows guest
report = vm_doctor(vm="Windows 11")
for check in report.host_checks + report.guest_checks:
    print(f"[{check.status}] {check.name}: {check.detail}")
```

### 8. Windows Guest Automation Optimization (`vm_optimize_windows`)
Configure Windows Defender real-time scanning exclusions and set PowerShell ExecutionPolicy to Bypass to eliminate `EPERM` file-locking during builds:

```python
# Optimize Windows guest for fast builds and testing
vm_optimize_windows(
    vm="Windows 11",
    exclusion_paths=[r"C:\Temp", r"C:\workspace"],
    exclusion_processes=["node.exe", "npm.cmd", "pnpm.cmd", "git.exe"]
)
```

### 9. Query Release Notes & Version Updates (`vm_changelog`)
Retrieve the changelog programmatically to check for newly supported features or breaking changes:

```python
# Read the latest release notes
latest_notes = vm_changelog(limit=1)
print(latest_notes)
```

---

## Prerequisites

1. **macOS** with [Parallels Desktop](https://www.parallels.com/) Pro or Business Edition installed.
   - *Note*: Parallels Desktop Pro or Business is required for the `prlctl` command-line utility and `prlctl exec` guest execution.
2. **Parallels Tools** installed inside each target guest VM.
3. **Python 3.10+** and [`uv`](https://docs.astral.sh/uv/) (recommended).

### Command-Line Interface & Environment Verification

Before connecting an MCP client, you can use the built-in CLI to run diagnostics, read release notes, or start the server:

```bash
# Run the pre-flight diagnostic doctor
uv run parallels-pro-mcp doctor
# (or via the standalone script: ./scripts/doctor.sh)

# Display recent release notes and version history
uv run parallels-pro-mcp changelog

# Check installed version
uv run parallels-pro-mcp --version

# Launch the MCP stdio server
uv run parallels-pro-mcp
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

| Variable                 | Description                                                        | Default                             |
|--------------------------|--------------------------------------------------------------------|-------------------------------------|
| `PARALLELS_DEFAULT_VM`   | Fallback VM name or UUID used when a tool argument is omitted      | None                                |
| `PARALLELS_ARTIFACT_DIR` | Host directory where captured screenshots and artifacts are stored | `~/.cache/parallels-pro-mcp-server` |
| `PARALLELS_MCP_DEBUG`    | Enable verbose debug logging to stderr (`1` or `true`)             | `0` (disabled)                      |

---

## Safe Operating Sequence for Agents

1. **Discover**: Call `vm_list` to see available VMs and states.
2. **Inspect**: Call `vm_status(vm="...")` to verify guest tools and power status.
3. **Optional Sandbox**: For risky or destructive test sessions, call `vm_clone(vm="...", name="agent-sandbox", linked=true)` to create a fast, isolated linked clone.
4. **Power Up**: If stopped, call `vm_start` followed by `vm_wait_ready` to ensure guest tools are responsive.
5. **Inspect Desktop**: Call `vm_screenshot` to visually check if dialogs or login prompts are blocking the session.
6. **Snapshot Baseline**: Call `snapshot_create(vm="...", name="clean-baseline", confirm=true)` before performing major tasks.
7. **Transfer & Execute**: Use `vm_copy_to_guest` to stage scripts, `vm_exec` with explicit argv arrays to run commands, and `vm_copy_from_guest` to retrieve build artifacts.
8. **Teardown**: Revert via `snapshot_revert` or destroy ephemeral sandboxes via `vm_delete(vm="agent-sandbox", confirm=true)`.

---

## Security Model

- **Automation Bridge**: This server delegates guest execution directly to `prlctl exec`.
- **Privilege & Shared Folders**: If your VM has Parallels Shared Folders enabled (e.g. `\\Mac\Home` on Windows or `/media/psf/` on Linux), guest commands can read and write to your host filesystem. Always run only on trusted virtual machines.
- **Explicit Argv Only**: `vm_exec` only accepts argument vectors (`list[str]`), preventing shell injection on the host.

---

## Development & Testing

```bash
# Clone the repository
git clone https://github.com/PopBot/parallels-pro-mcp-server.git
cd parallels-pro-mcp-server

# Install dependencies and sync environment
uv sync

# Run diagnostic doctor
uv run parallels-pro-mcp doctor

# Run test suite with test coverage reporting
uv run coverage run --source=parallels_mcp -m unittest discover -s tests
uv run coverage report -m
```

For instructions on semantic versioning, GitHub Releases, and PyPI distribution, see the [Releasing & Publishing Guide](docs/RELEASING.md).

---

## License

This project is licensed under the [MIT License](LICENSE).

---

Not affiliated with Parallels International GmbH.

Built with ♥️ as a collaboration between human and AI.
